from __future__ import annotations

from typing import Any

from core.analysis.evidence_autofill import EvidenceAutofillService
from core.analysis.semantic_evidence import SemanticEvidenceAnalyzer
from core.claims.form995_parser import Form995ClaimParser
from core.ingestion.categories import DocumentCategory
from core.ingestion.processing_pipeline import ProcessingPipeline
from core.retrieval.hybrid_search import ClaimRetriever, lexical_score
from core.timeline.auto_populator import HistoricalTimelineAutoPopulator


class BulkProjectAnalysis:
    """Upload-first, all-claims processing workflow."""

    def __init__(self, db):
        self.db = db

    def detect_claims_from_form995(self, project_id: str) -> dict[str, Any]:
        pages = [
            p for p in self.db.list_chunks(project_id)
            if p.get("category") == DocumentCategory.FORM_995.value
        ]
        return Form995ClaimParser().add_missing_claims(self.db, project_id, pages)

    def _link_relevant_pages(self, project_id: str, max_pages_per_claim: int = 80) -> dict[str, int]:
        claims = self.db.list_claims(project_id)
        pages = self.db.list_chunks(project_id)
        linked: dict[str, int] = {}
        for claim in claims:
            ranked = []
            query = f"{claim['condition_name']} {claim.get('theory','')} diagnosis symptoms onset treatment functional impairment nexus"
            for page in pages:
                score = lexical_score(query, page.get("text", ""))
                # Keep explicitly claim-linked pages and pages with an affirmative lexical tie.
                explicit = claim["id"] in (page.get("linked_claim_ids") or "").split(",")
                if explicit or score > 0:
                    ranked.append((1.0 if explicit else score, page))
            ranked.sort(key=lambda item: (item[0], item[1].get("ocr_confidence") or 0), reverse=True)
            count = 0
            for score, page in ranked[:max_pages_per_claim]:
                relevance = "explicit_document_link" if score >= 1 else "bulk_retrieval"
                self.db.link_page_claim(page["id"], claim["id"], relevance)
                count += 1
            linked[claim["id"]] = count
        return linked

    def run_ocr_and_retrieval_all(self, project_id: str) -> dict[str, Any]:
        documents = self.db.list_documents(project_id)
        unprocessed = [d for d in documents if d.get("extraction_status") != "complete"]
        pipeline = ProcessingPipeline(self.db)
        processed, errors = [], []
        # Process 995s first so their claims are available before page linking.
        ordered = sorted(unprocessed, key=lambda d: d.get("category") != DocumentCategory.FORM_995.value)
        for document in ordered:
            try:
                processed.append(pipeline.process_document(project_id, document))
            except Exception as exc:  # surfaced in UI, never silently swallowed
                errors.append({"document_id": document["id"], "document_name": document.get("original_name"), "error": str(exc)})
        claim_detection = self.detect_claims_from_form995(project_id)
        linked = self._link_relevant_pages(project_id)
        retrieval: dict[str, list[dict[str, Any]]] = {}
        retriever = ClaimRetriever(self.db)
        current_claims = self.db.list_claims(project_id)
        for claim in current_claims:
            retrieval[claim["id"]] = retriever.retrieve(project_id, claim["id"], limit=40)
        proposals = HistoricalTimelineAutoPopulator().propose(
            current_claims, self.db.list_annotations_enriched(project_id), self.db.list_chunks(project_id)
        )
        timeline_added = self.db.add_timeline_events_if_new(project_id, proposals)
        return {
            "processed": processed,
            "errors": errors,
            "claim_detection": claim_detection,
            "linked_pages": linked,
            "retrieval": retrieval,
            "timeline_proposed": len(proposals),
            "timeline_added": timeline_added,
        }

    def run_semantic_all(self, project_id: str, threshold: float = 0.72, auto_populate: bool = True) -> dict[str, Any]:
        analyzer = SemanticEvidenceAnalyzer()
        results: dict[str, Any] = {}
        total_candidates = total_created = total_skipped = 0
        for claim in self.db.list_claims(project_id):
            chunks = self.db.list_chunks(project_id, claim_id=claim["id"])
            candidates = analyzer.analyze_chunks(claim, chunks)
            item = {"claim": claim, "candidates": candidates}
            total_candidates += len(candidates)
            if auto_populate:
                fill = EvidenceAutofillService(self.db).populate(project_id, candidates, threshold)
                item["autofill"] = fill
                total_created += fill["created"]
                total_skipped += fill["skipped"]
            results[claim["id"]] = item
        return {
            "by_claim": results,
            "total_claims": len(results),
            "total_candidates": total_candidates,
            "created": total_created,
            "skipped": total_skipped,
        }
