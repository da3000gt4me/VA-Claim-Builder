
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.jobs import JobManager
from core.ocr import OCRManager
from core.projects import ProjectInfo
from core.settings import SettingsManager
from core.timeline import TimelineManager

from .extractor import EXTRACTION_VERSION, LocalExtraction, LocalMedicalExtractor
from .manager import IntakeManager


@dataclass(slots=True)
class IntakeSummary:
    documents_processed: int = 0
    pages_processed: int = 0
    evidence_created: int = 0
    claims_matched: int = 0
    claim_suggestions_created: int = 0
    timeline_events_created: int = 0
    relationship_suggestions_created: int = 0
    statements_imported: int = 0
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class AutomatedIntakeOrchestrator:
    """Persistent local-first import-to-review pipeline."""

    STAGES = [
        ("extracting text", 10), ("classifying", 25), ("extracting evidence", 40),
        ("matching claims", 60), ("building timeline", 75), ("generating suggestions", 88),
        ("review required", 100),
    ]

    def __init__(self, project: ProjectInfo, *, app_settings: dict | None = None):
        self.project = project
        self.documents = DocumentManager(project)
        self.jobs = JobManager(project)
        self.ocr = OCRManager(project)
        self.claims = ClaimManager(project)
        self.evidence = EvidenceManager(project)
        self.timeline = TimelineManager(project)
        self.intake = IntakeManager(project)
        self.extractor = LocalMedicalExtractor()
        self.app_settings = {**SettingsManager.APP_DEFAULTS, **(app_settings or {})}

    def queue(self, document_ids):
        jobs = []
        for document_id in document_ids:
            document = self.documents.get(document_id)
            self.intake.ensure_document(document_id, document.sha256)
            self.intake.update_state(document_id, stage="queued", progress=0)
            jobs.append(self.jobs.create_unique("automated_intake", {"document_id": document_id}))
        return jobs

    def run_documents(self, document_ids, *, progress=None, cancelled=None, force=False):
        emit = progress or (lambda _percent, _message: None)
        is_cancelled = cancelled or (lambda: False)
        total = max(1, len(document_ids)); combined = IntakeSummary()
        for index, document_id in enumerate(document_ids):
            if is_cancelled():
                self.intake.update_state(document_id, stage="cancelled", progress=0, failure_reason="Cancelled")
                break
            summary = self.analyze_document(
                document_id, force=force, cancelled=is_cancelled,
                progress=lambda percent, message, i=index: emit(int(((i + percent / 100) / total) * 100), message),
            )
            for name in combined.__dataclass_fields__:
                value = getattr(summary, name)
                if isinstance(value, list): getattr(combined, name).extend(value)
                else: setattr(combined, name, getattr(combined, name) + value)
        return combined

    def analyze_document(self, document_id, *, progress=None, cancelled=None, force=False):
        emit = progress or (lambda _percent, _message: None)
        is_cancelled = cancelled or (lambda: False)
        document = self.documents.get(document_id)
        state = self.intake.ensure_document(document_id, document.sha256)
        if not force and state.stage in {"completed", "review required"} and state.source_checksum == document.sha256 and state.extraction_version == EXTRACTION_VERSION:
            return IntakeSummary()
        job = self.jobs.create_unique("automated_intake", {"document_id": document_id})
        self.jobs.update(job.job_id, status="running", message="Starting automatic intake")
        run_id = self.intake.create_run(document_id, document.sha256, EXTRACTION_VERSION, job.job_id)
        summary = IntakeSummary()
        try:
            self._stage(document_id, "extracting text", 10, emit, document.original_name)
            if is_cancelled(): raise InterruptedError("Cancelled")
            try:
                ocr = self.ocr.get(document_id)
            except KeyError:
                if document.stored_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"} and not self.app_settings["automatic_ocr"]:
                    raise ValueError("OCR is required for this image, but automatic OCR is disabled.")
                ocr = self.ocr.process(document_id, cancelled=is_cancelled)
            text = ocr.text_path.read_text(encoding="utf-8", errors="replace")
            summary.pages_processed = ocr.page_count
            if not text.strip() or len(re.sub(r"--- PAGE \d+ ---", "", text).strip()) < 5:
                raise ValueError("No text detected. OCR may be required or unavailable.")
            self._stage(document_id, "classifying", 25, emit, document.original_name)
            try:
                metadata = __import__("json").loads(ocr.metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
            extraction = self.extractor.extract(
                text, filename=document.original_name,
                acroform_fields=metadata.get("acroform_fields") or {},
            )
            self.intake.set_classification(
                document_id, extraction.document_type, extraction.document_type_confidence,
                extraction.form_revision,
                "acroform+local-rules" if metadata.get("acroform_fields") else "local-rules",
            )
            if is_cancelled(): raise InterruptedError("Cancelled")
            self._stage(document_id, "extracting evidence", 40, emit, document.original_name)
            claim_matches = self._match_claims(extraction)
            evidence_ids = self._create_evidence(document_id, extraction, claim_matches) if self.app_settings["create_evidence_suggestions"] else []
            summary.evidence_created = len(set(evidence_ids))
            self._stage(document_id, "matching claims", 60, emit, document.original_name)
            summary.claims_matched = len({claim_id for ids in claim_matches.values() for claim_id in ids})
            self._create_claim_drafts(document_id, extraction, claim_matches, evidence_ids)
            self._stage(document_id, "building timeline", 75, emit, document.original_name)
            summary.timeline_events_created = self._create_timeline(document_id, extraction, claim_matches, evidence_ids) if self.app_settings["create_timeline_suggestions"] else 0
            self._stage(document_id, "generating suggestions", 88, emit, document.original_name)
            counts = self._create_suggestions(document_id, extraction, claim_matches, evidence_ids)
            summary.claim_suggestions_created, summary.relationship_suggestions_created = counts
            if extraction.imported_statement:
                statement_claim = self._statement_claim(extraction)
                self.intake.import_statement(
                    document_id, extraction.document_type, extraction.imported_statement,
                    extraction.document_type_confidence,
                    statement_claim,
                )
                if extraction.document_type in {"provider_nexus_letter", "claimant_nexus_statement"} and statement_claim:
                    self._import_nexus(document_id, extraction, statement_claim)
                summary.statements_imported = 1
            self.intake.add_suggestion(
                "metadata", document_id, f"Extracted metadata for {document.original_name}",
                {
                    "providers": extraction.providers, "facilities": extraction.facilities,
                    "specialties": extraction.specialties, "dates": extraction.dates,
                    "diagnoses": extraction.diagnoses, "symptoms": extraction.symptoms,
                    "diagnosis_details": extraction.diagnosis_details,
                    "document_type": extraction.document_type,
                    "form_revision": extraction.form_revision,
                    "medications": extraction.medications, "procedures": extraction.procedures,
                    "imaging": extraction.imaging, "laboratory_testing": extraction.laboratory_testing,
                }, .8, EXTRACTION_VERSION,
            )
            for evidence_id in set(evidence_ids):
                record = self.evidence.get(evidence_id)
                self.intake.add_suggestion(
                    "evidence", document_id, record.title,
                    {"evidence_id": evidence_id, "summary": record.description, "source_document": document_id},
                    .75, EXTRACTION_VERSION, next(iter(record and [link.claim_id for link in self.evidence.claim_links_for_evidence(evidence_id)]), None),
                )
            for event in self.timeline.list():
                if event.document_id == document_id:
                    self.intake.add_suggestion(
                        "timeline", document_id, event.title,
                        {"event_id": event.event_id, "date": event.event_date, "source_document": document_id},
                        .72, EXTRACTION_VERSION,
                    )
            summary.documents_processed = 1
            result_counts = summary.to_dict()
            result_counts.pop("warnings"); result_counts.pop("failures")
            self.intake.update_state(
                document_id, stage="review required", progress=100, completed=True,
                extraction_version=EXTRACTION_VERSION, result_counts=result_counts, warnings=summary.warnings,
            )
            self.jobs.update(job.job_id, status="completed", progress=100, message="Automatic intake complete; review required")
            self.intake.finish_run(run_id, "completed", summary.to_dict())
            emit(100, f"Analysis complete: {document.original_name}")
            return summary
        except InterruptedError:
            self.intake.update_state(document_id, stage="cancelled", progress=0, failure_reason="Cancelled", extraction_version=EXTRACTION_VERSION)
            self.jobs.update(job.job_id, status="cancelled", message="Automatic intake cancelled")
            self.intake.finish_run(run_id, "cancelled", summary.to_dict(), "Cancelled")
            return summary
        except Exception as exc:
            message = self._safe_error(exc)
            summary.failures.append(message)
            self.intake.update_state(document_id, stage="failed", progress=0, failure_reason=message, extraction_version=EXTRACTION_VERSION)
            self.jobs.update(job.job_id, status="failed", message=message)
            self.intake.finish_run(run_id, "failed", summary.to_dict(), message)
            return summary

    def _stage(self, document_id, stage, percent, emit, name):
        self.intake.update_state(document_id, stage=stage, progress=percent, extraction_version=EXTRACTION_VERSION)
        emit(percent, f"{stage.title()}: {name}")

    def _match_claims(self, extraction):
        claims = self.claims.list_claims()
        matches = {}
        for diagnosis in extraction.diagnoses:
            tokens = self._tokens(diagnosis)
            ids = [claim.claim_id for claim in claims if tokens & self._tokens(claim.condition_name)]
            matches[diagnosis] = ids
        return matches

    def _create_evidence(self, document_id, extraction, matches):
        created = []
        groups = [
            ("diagnosis", extraction.diagnoses, "private medical record", "supportive"),
            ("symptom", extraction.symptoms, "private medical record", "neutral"),
            ("functional impact", extraction.functional_impacts + extraction.occupational_impacts, "lay statement", "neutral"),
            ("testing/imaging", extraction.imaging + extraction.laboratory_testing, "private medical record", "neutral"),
            ("treatment", extraction.medications + extraction.procedures, "private medical record", "neutral"),
            ("nexus indicator", extraction.nexus_statements, "medical opinion", "supportive"),
            ("potential contradiction", extraction.contradictory_statements, "private medical record", "contradictory"),
        ]
        for kind, values, evidence_type, strength in groups:
            for value in values:
                fingerprint = self.intake.fingerprint(document_id, kind, value)
                with sqlite3.connect(self.project.database_path) as connection:
                    existing = connection.execute(
                        "SELECT evidence_id FROM intake_evidence_sources WHERE fingerprint=?", (fingerprint,)
                    ).fetchone()
                if existing:
                    created.append(existing[0]); continue
                claim_ids = matches.get(value, [])
                if not claim_ids:
                    for diagnosis, ids in matches.items():
                        if self._tokens(diagnosis) & self._tokens(value): claim_ids.extend(ids)
                record = self.evidence.create(
                    f"Automated {kind}: {value[:80]}", description=value, evidence_type=evidence_type,
                    document_id=document_id, evidence_date=self._near_date(value, extraction.dates),
                    provider_source=(extraction.providers or extraction.facilities or [""])[0],
                    relevance_notes="Local deterministic extraction; verify against the cited source.",
                    strength_status=strength, review_status="unreviewed", claim_ids=set(claim_ids),
                )
                with sqlite3.connect(self.project.database_path) as connection:
                    connection.execute(
                        "INSERT INTO intake_evidence_sources VALUES(?,?,?,?,?)",
                        (record.evidence_id, document_id, fingerprint, self._page_for(value, extraction), EXTRACTION_VERSION),
                    )
                created.append(record.evidence_id)
        return created

    def _create_timeline(self, document_id, extraction, matches, evidence_ids):
        count = 0
        for item in extraction.timeline_entries:
            fingerprint = self.intake.fingerprint(document_id, "personal-timeline", item)
            with sqlite3.connect(self.project.database_path) as connection:
                if connection.execute("SELECT 1 FROM intake_timeline_sources WHERE fingerprint=?", (fingerprint,)).fetchone():
                    continue
            event = self.timeline.create(
                item["title"], event_date=item.get("event_date", ""), date_precision="exact",
                event_type=item.get("event_type", "other"), description=item.get("description", ""),
                document_id=document_id, evidence_id=evidence_ids[0] if evidence_ids else None,
                notes="Claimant-reported automated draft; not independently medically verified.",
                claim_ids={cid for ids in matches.values() for cid in ids},
            )
            with sqlite3.connect(self.project.database_path) as connection:
                connection.execute(
                    "INSERT INTO intake_timeline_sources VALUES(?,?,?,?)",
                    (event.event_id, document_id, fingerprint, EXTRACTION_VERSION),
                )
            count += 1
        dates = extraction.dates or [""]
        for index, date in enumerate(dates[:50]):
            excerpt = next((item for item in extraction.page_excerpts if date and date in item["text"]), None)
            description = excerpt["text"] if excerpt else "Extracted medical-record event; source review required."
            fingerprint = self.intake.fingerprint(document_id, date, description)
            with sqlite3.connect(self.project.database_path) as connection:
                if connection.execute("SELECT 1 FROM intake_timeline_sources WHERE fingerprint=?", (fingerprint,)).fetchone():
                    continue
            claim_ids = {cid for ids in matches.values() for cid in ids}
            event = self.timeline.create(
                f"Draft record event {date or index + 1}", event_date=date, date_precision="exact" if date else "unknown",
                event_type="diagnosis" if extraction.diagnoses else "treatment", description=description,
                provider_facility=", ".join((extraction.providers + extraction.facilities)[:2]),
                diagnosis="; ".join(extraction.diagnoses[:5]), symptoms=extraction.symptoms[:10],
                medications=extraction.medications[:10], testing_imaging="; ".join((extraction.imaging + extraction.laboratory_testing)[:5]),
                treatment="; ".join(extraction.procedures[:5]),
                functional_impact="; ".join((extraction.functional_impacts + extraction.occupational_impacts)[:5]),
                document_id=document_id, evidence_id=evidence_ids[0] if evidence_ids else None,
                notes="Automated local draft; not user-confirmed.", claim_ids=claim_ids,
            )
            with sqlite3.connect(self.project.database_path) as connection:
                connection.execute("INSERT INTO intake_timeline_sources VALUES(?,?,?,?)", (event.event_id, document_id, fingerprint, EXTRACTION_VERSION))
            count += 1
        return count

    def _create_suggestions(self, document_id, extraction, matches, evidence_ids):
        claim_count = relation_count = 0
        for item in extraction.claim_suggestions if self.app_settings["create_claim_suggestions"] else []:
            payload = {
                "proposed_condition_name": item["condition"],
                "condition": item["condition"], "secondary_to": item.get("secondary_to", ""),
                "description": item.get("description", ""), "service_event": item.get("service_event", ""),
                "theory": item.get("theory", ""), "prior_decision_date": item.get("prior_decision_date", ""),
                "source_page": item.get("source_page"), "extraction_method": item.get("extraction_method"),
                "field_references": item.get("field_references", {}),
                "supporting_text": item.get("supporting_text", ""),
                "possible_claim_type": "secondary" if item.get("secondary_to") else "direct",
                "linked_source_documents": [document_id], "linked_evidence_records": evidence_ids,
            }
            self.intake.add_suggestion(
                "claim", document_id, item["condition"], payload,
                float(item.get("confidence", .75)), EXTRACTION_VERSION,
            )
            claim_count += 1
        for diagnosis in extraction.diagnoses if self.app_settings["create_claim_suggestions"] else []:
            if matches.get(diagnosis):
                continue
            payload = {
                "proposed_condition_name": diagnosis, "normalized_condition_name": diagnosis.casefold(),
                "earliest_documented_date": min(extraction.dates, default=""),
                "most_recent_documented_date": max(extraction.dates, default=""),
                "supporting_diagnoses": [diagnosis], "supporting_symptoms": extraction.symptoms,
                "supporting_treatments": extraction.medications + extraction.procedures,
                "linked_source_documents": [document_id], "linked_evidence_records": evidence_ids,
                "possible_claim_type": "direct", "functional_impact_summary": extraction.functional_impacts,
                "explanation": "A diagnosis label was extracted locally. It is a review suggestion, not a confirmed claim.",
            }
            self.intake.add_suggestion("claim", document_id, diagnosis, payload, .78, EXTRACTION_VERSION)
            claim_count += 1
        relationships = extraction.relationship_statements + extraction.aggravation_statements
        for statement in relationships if self.app_settings["create_relationship_suggestions"] else []:
            payload = {
                "relationship_type": "aggravation" if statement in extraction.aggravation_statements else "possible secondary",
                "source_evidence": statement, "rationale": "Relationship language appears in the source text.",
                "contradictory_evidence": extraction.contradictory_statements,
                "missing_nexus_requirements": ["Qualified provider opinion may still be required."],
                "provider_opinion_needed": True,
            }
            self.intake.add_suggestion("relationship", document_id, statement[:100], payload, .62, EXTRACTION_VERSION)
            relation_count += 1
        for value in extraction.contradictory_statements:
            self.intake.add_suggestion("contradiction", document_id, value[:100], {"source_evidence": value}, .7, EXTRACTION_VERSION)
        if not extraction.diagnoses:
            self.intake.add_suggestion("gap", document_id, "No diagnosis label detected", {"recommended_action": "Review the document and confirm whether diagnosis evidence is present."}, .9, EXTRACTION_VERSION)
        return claim_count, relation_count

    def _statement_claim(self, extraction):
        condition = str(extraction.imported_statement.get("condition") or extraction.imported_statement.get("secondary_condition") or "")
        tokens = self._tokens(condition)
        if not tokens:
            return None
        return next(
            (claim.claim_id for claim in self.claims.list_claims() if tokens & self._tokens(claim.condition_name)),
            None,
        )

    def _import_nexus(self, document_id, extraction, claim_id):
        from core.nexus import NexusLetterManager
        manager = NexusLetterManager(self.project)
        if any(document_id in letter.document_ids for letter in manager.list()):
            return
        fields = extraction.imported_statement
        provider_authored = extraction.document_type == "provider_nexus_letter"
        manager.create(
            claim_id,
            f"Imported {'provider nexus letter' if provider_authored else 'claimant nexus argument'}",
            letter_type="imported_provider_opinion" if provider_authored else "claimant_argument",
            status="final" if provider_authored and fields.get("signed") else "draft",
            primary_theory="secondary" if fields.get("secondary_condition") else "direct",
            author_name=str(fields.get("author") or ""),
            author_credentials=str(fields.get("credentials") or ""),
            specialty=str(fields.get("specialty") or ""),
            content={
                "current_diagnosis": fields.get("condition", ""),
                "in_service_event": fields.get("event_or_exposure", ""),
                "nexus_opinion": fields.get("opinion_language", ""),
                "medical_rationale": fields.get("rationale", ""),
                "service_history": fields.get("continuity", ""),
                "limitations": (
                    "Imported claimant-authored argument; not an independent medical opinion."
                    if not provider_authored else "Imported from source; verify author, credentials, and signature."
                ),
                "signature_block": fields.get("signature", ""),
            },
            document_ids=(document_id,),
        )

    def _create_claim_drafts(self, document_id, extraction, matches, evidence_ids):
        for diagnosis, claim_ids in matches.items():
            for claim_id in claim_ids:
                details = [
                    item for item in extraction.diagnosis_details
                    if item["diagnosis"].casefold() == diagnosis.casefold()
                ]
                detail_text = diagnosis
                codes = [item["code"] for item in details if item.get("code")]
                providers = [item["provider"] for item in details if item.get("provider")]
                dates = [item["date"] for item in details if item.get("date")]
                if codes: detail_text += f" ({', '.join(dict.fromkeys(codes))})"
                if dates: detail_text += f"; documented {', '.join(dict.fromkeys(dates))}"
                if providers: detail_text += f"; provider(s): {', '.join(dict.fromkeys(providers))}"
                self.intake.add_claim_draft(claim_id, "current_diagnosis", detail_text, evidence_ids, EXTRACTION_VERSION)
                self.intake.add_suggestion(
                    "claim_field", document_id, f"Current diagnosis: {diagnosis}",
                    {
                        "field_name": "current_diagnosis", "proposed_value": detail_text,
                        "diagnosis_details": details, "source_document": document_id,
                        "source_evidence": evidence_ids,
                    },
                    .86, EXTRACTION_VERSION, claim_id,
                )
                if extraction.symptoms:
                    self.intake.add_claim_draft(claim_id, "symptoms", "; ".join(extraction.symptoms), evidence_ids, EXTRACTION_VERSION)
                summary = f"Records document {diagnosis}."
                if extraction.dates: summary += f" Documented dates include {', '.join(extraction.dates[:5])}."
                if extraction.functional_impacts: summary += " Reported functional impact: " + "; ".join(extraction.functional_impacts[:3])
                self.intake.add_claim_draft(claim_id, "description", summary, evidence_ids, EXTRACTION_VERSION)

    @staticmethod
    def _tokens(value):
        stop = {"the", "and", "of", "pain", "condition", "disorder"}
        return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 2 and token not in stop}

    @staticmethod
    def _near_date(_value, dates):
        return dates[0] if dates else ""

    @staticmethod
    def _page_for(value, extraction):
        item = next((item for item in extraction.page_excerpts if value in item["text"]), None)
        return item["page"] if item else None

    @staticmethod
    def _safe_error(exc):
        if "encrypted" in str(exc).casefold(): return "Encrypted PDF cannot be processed; unlock it and retry."
        if isinstance(exc, FileNotFoundError): return "The imported source file is missing."
        return str(exc)[:500] or type(exc).__name__
