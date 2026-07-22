from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.projects import ProjectInfo
from core.projects.manager import EVIDENCE_ANALYSIS_SCHEMA
from core.security.redaction import redact_identifiers
from core.settings import AISettings, SettingsManager

from .manager import EvidenceManager


ANALYSIS_VERSION = "1.0"
ANALYSIS_STATUSES = ("pending", "completed", "failed", "cancelled")
RESULT_FIELDS = (
    "summary", "diagnoses_or_conditions", "symptoms_and_functional_limitations",
    "treatment_testing_medications", "dates_and_providers", "in_service_events_or_exposures",
    "nexus_supporting_statements", "aggravation_evidence", "secondary_service_connection_evidence",
    "favorable_evidence", "unfavorable_or_contradictory_evidence",
    "missing_information_or_clarification_needs", "recommended_claim_associations", "confidence",
)
LIST_FIELDS = RESULT_FIELDS[1:-1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceAnalysisError(RuntimeError):
    pass


class AnalysisCancelled(EvidenceAnalysisError):
    pass


@dataclass(frozen=True, slots=True)
class StructuredEvidenceAnalysis:
    summary: str
    diagnoses_or_conditions: list[str] = field(default_factory=list)
    symptoms_and_functional_limitations: list[str] = field(default_factory=list)
    treatment_testing_medications: list[str] = field(default_factory=list)
    dates_and_providers: list[str] = field(default_factory=list)
    in_service_events_or_exposures: list[str] = field(default_factory=list)
    nexus_supporting_statements: list[str] = field(default_factory=list)
    aggravation_evidence: list[str] = field(default_factory=list)
    secondary_service_connection_evidence: list[str] = field(default_factory=list)
    favorable_evidence: list[str] = field(default_factory=list)
    unfavorable_or_contradictory_evidence: list[str] = field(default_factory=list)
    missing_information_or_clarification_needs: list[str] = field(default_factory=list)
    recommended_claim_associations: list[dict[str, str]] = field(default_factory=list)
    confidence: str = "low"

    @classmethod
    def from_payload(cls, payload: object) -> StructuredEvidenceAnalysis:
        if not isinstance(payload, dict):
            raise EvidenceAnalysisError("AI provider returned a malformed analysis response")
        missing = [name for name in RESULT_FIELDS if name not in payload]
        if missing:
            raise EvidenceAnalysisError("AI provider response is missing required structured fields")
        if not isinstance(payload["summary"], str) or not payload["summary"].strip():
            raise EvidenceAnalysisError("AI provider response has an invalid summary")
        normalized: dict[str, Any] = {"summary": payload["summary"].strip()}
        for name in LIST_FIELDS:
            value = payload[name]
            if not isinstance(value, list):
                raise EvidenceAnalysisError(f"AI provider response has an invalid {name} section")
            if name == "recommended_claim_associations":
                recommendations = []
                for item in value:
                    if not isinstance(item, dict) or not isinstance(item.get("claim_id", ""), str):
                        raise EvidenceAnalysisError("AI provider returned malformed claim recommendations")
                    recommendations.append({
                        "claim_id": item.get("claim_id", "").strip(),
                        "claim_name": str(item.get("claim_name", "")).strip(),
                        "reason": str(item.get("reason", "")).strip(),
                    })
                normalized[name] = recommendations
            else:
                if not all(isinstance(item, str) for item in value):
                    raise EvidenceAnalysisError(f"AI provider response has an invalid {name} section")
                normalized[name] = [item.strip() for item in value if item.strip()]
        confidence = str(payload["confidence"]).strip().lower()
        if confidence not in {"low", "medium", "high"}:
            raise EvidenceAnalysisError("AI provider response has an invalid confidence level")
        normalized["confidence"] = confidence
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in RESULT_FIELDS}


@dataclass(frozen=True, slots=True)
class EvidenceAnalysisRecord:
    analysis_id: str
    evidence_id: str
    job_id: str | None
    status: str
    provider: str
    model: str
    analysis_version: str
    result: StructuredEvidenceAnalysis | None
    error_message: str
    redaction_applied: bool
    created_at: str
    completed_at: str | None


class EvidenceAnalysisService:
    """Provider-neutral, privacy-aware evidence analyzer with immutable history."""

    def __init__(self, project: ProjectInfo, *, settings_manager: SettingsManager | None = None,
                 router_factory: Callable[[AISettings], Any] | None = None) -> None:
        self.project = project
        self.evidence = EvidenceManager(project)
        self.settings_manager = settings_manager or SettingsManager()
        self.router_factory = router_factory or self._default_router
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.project.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_pending(self, evidence_id: str, *, job_id: str | None = None) -> EvidenceAnalysisRecord:
        self.evidence.get(evidence_id)
        settings = self.settings_manager.load_ai_settings()
        provider = settings.provider
        model = settings.model_openai if provider == "openai" else settings.model_xai if provider == "xai" else ""
        analysis_id = str(uuid.uuid4()); now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO evidence_analyses(analysis_id,evidence_id,job_id,status,provider,model,analysis_version,"
                "result_json,error_message,redaction_applied,created_at,completed_at) "
                "VALUES(?,?,?,'pending',?,?,?,NULL,'',0,?,NULL)",
                (analysis_id, evidence_id, job_id, provider, model, ANALYSIS_VERSION, now),
            )
        return self.get(analysis_id)

    def analyze(self, evidence_id: str, *, job_id: str | None = None, analysis_id: str | None = None,
                cancelled: Callable[[], bool] | None = None) -> EvidenceAnalysisRecord:
        is_cancelled = cancelled or (lambda: False)
        record = self.get(analysis_id) if analysis_id else self.create_pending(evidence_id, job_id=job_id)
        settings = self.settings_manager.load_ai_settings()
        if is_cancelled():
            return self._finish(record.analysis_id, "cancelled", error_message="Analysis cancelled")
        if settings.local_only:
            message = "AI evidence analysis is unavailable while local-only mode is enabled"
            self._finish(record.analysis_id, "failed", error_message=message)
            raise EvidenceAnalysisError(message)
        if settings.provider not in {"openai", "xai"}:
            message = f"AI provider is unavailable: {settings.provider or 'not configured'}"
            self._finish(record.analysis_id, "failed", error_message=message)
            raise EvidenceAnalysisError(message)
        credentials = {"openai": settings.openai_api_key, "xai": settings.xai_api_key}
        usable_providers = [settings.provider]
        if settings.fallback_provider in {"openai", "xai"} and settings.fallback_provider != settings.provider:
            usable_providers.append(settings.fallback_provider)
        if not any(credentials.get(provider) for provider in usable_providers):
            message = "AI provider credentials are not configured"
            self._finish(record.analysis_id, "failed", error_message=message)
            raise EvidenceAnalysisError(message)
        redaction_applied = bool(settings.redact_before_cloud)
        try:
            prompt = self._build_prompt(evidence_id)
            if redaction_applied:
                prompt, _counts = redact_identifiers(prompt)
            request = AIRequest(
                task="evidence_analysis",
                system_prompt=self._system_prompt(),
                user_prompt=prompt,
                json_schema=self._json_schema(),
                temperature=0.0,
                metadata={"evidence_id": evidence_id, "analysis_version": ANALYSIS_VERSION},
            )
            router = self.router_factory(settings)
            response = router.generate(request)
            if is_cancelled():
                return self._finish(record.analysis_id, "cancelled", provider=response.provider,
                                    model=response.model, redaction_applied=redaction_applied,
                                    error_message="Analysis cancelled")
            result = StructuredEvidenceAnalysis.from_payload(response.parsed)
            result = self._validated_recommendations(result)
            return self._finish(record.analysis_id, "completed", provider=response.provider,
                                model=response.model, redaction_applied=redaction_applied, result=result)
        except AnalysisCancelled:
            return self._finish(record.analysis_id, "cancelled", redaction_applied=redaction_applied,
                                error_message="Analysis cancelled")
        except Exception as exc:
            message = self._safe_error(exc, settings)
            self._finish(record.analysis_id, "failed", redaction_applied=redaction_applied, error_message=message)
            if isinstance(exc, EvidenceAnalysisError):
                raise
            raise EvidenceAnalysisError(message) from exc

    def cancel_pending(self, analysis_id: str) -> EvidenceAnalysisRecord:
        record = self.get(analysis_id)
        if record.status != "pending":
            return record
        return self._finish(analysis_id, "cancelled", error_message="Analysis cancelled")

    def get(self, analysis_id: str) -> EvidenceAnalysisRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evidence_analyses WHERE analysis_id=?", (analysis_id,)).fetchone()
        if row is None:
            raise KeyError(analysis_id)
        return self._from_row(row)

    def history(self, evidence_id: str) -> list[EvidenceAnalysisRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence_analyses WHERE evidence_id=? ORDER BY created_at DESC, analysis_id DESC",
                (evidence_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def latest(self, evidence_id: str) -> EvidenceAnalysisRecord | None:
        history = self.history(evidence_id)
        return history[0] if history else None

    def _build_prompt(self, evidence_id: str) -> str:
        evidence = self.evidence.get(evidence_id)
        links = self.evidence.claim_links_for_evidence(evidence_id)
        ocr_text = self.evidence.ocr_text(evidence_id) or ""
        payload = {
            "evidence": {
                "title": evidence.title, "description": evidence.description,
                "type": evidence.evidence_type, "date": evidence.evidence_date,
                "provider_or_source": evidence.provider_source,
                "general_relevance_notes": evidence.relevance_notes,
                "reviewer_notes": evidence.reviewer_notes,
            },
            "linked_claims": [
                {"claim_id": link.claim_id, "claim_name": link.condition_name,
                 "claim_specific_relevance_notes": link.relevance_notes} for link in links
            ],
            "available_project_claims": [
                {"claim_id": claim.claim_id, "claim_name": claim.condition_name}
                for claim in self.evidence_for_all_claims()
            ],
            "ocr_text": ocr_text,
        }
        return "Analyze this evidence and return only the required JSON structure:\n" + json.dumps(payload, ensure_ascii=False)

    def evidence_for_all_claims(self) -> list[Any]:
        from core.claims import ClaimManager
        return ClaimManager(self.project).list_claims()

    def _validated_recommendations(self, result: StructuredEvidenceAnalysis) -> StructuredEvidenceAnalysis:
        claims = {claim.claim_id: claim.condition_name for claim in self.evidence_for_all_claims()}
        payload = result.to_dict()
        payload["recommended_claim_associations"] = [
            {"claim_id": item["claim_id"], "claim_name": claims[item["claim_id"]], "reason": item["reason"]}
            for item in result.recommended_claim_associations if item["claim_id"] in claims
        ]
        return StructuredEvidenceAnalysis.from_payload(payload)

    def _finish(self, analysis_id: str, status: str, *, provider: str | None = None,
                model: str | None = None, redaction_applied: bool = False,
                result: StructuredEvidenceAnalysis | None = None, error_message: str = "") -> EvidenceAnalysisRecord:
        if status not in ANALYSIS_STATUSES:
            raise ValueError(status)
        current = self.get(analysis_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE evidence_analyses SET status=?,provider=?,model=?,result_json=?,error_message=?,"
                "redaction_applied=?,completed_at=? WHERE analysis_id=?",
                (status, provider or current.provider, model or current.model,
                 json.dumps(result.to_dict()) if result else None, error_message,
                 int(redaction_applied), _utc_now() if status != "pending" else None, analysis_id),
            )
        return self.get(analysis_id)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an evidence review assistant. Extract only facts supported by the supplied record. "
            "Do not make medical diagnoses or legal determinations. The analysis is advisory. "
            "Return valid JSON matching every requested field; use empty lists when unsupported."
        )

    @staticmethod
    def _json_schema() -> dict[str, Any]:
        properties: dict[str, Any] = {name: {"type": "array", "items": {"type": "string"}} for name in LIST_FIELDS}
        properties["summary"] = {"type": "string"}
        properties["recommended_claim_associations"] = {
            "type": "array", "items": {"type": "object", "properties": {
                "claim_id": {"type": "string"}, "claim_name": {"type": "string"}, "reason": {"type": "string"},
            }, "required": ["claim_id", "claim_name", "reason"]},
        }
        properties["confidence"] = {"type": "string", "enum": ["low", "medium", "high"]}
        return {"type": "object", "properties": properties, "required": list(RESULT_FIELDS)}

    @staticmethod
    def _safe_error(exc: Exception, settings: AISettings) -> str:
        if isinstance(exc, EvidenceAnalysisError):
            message = str(exc)
        elif isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
            message = "AI provider timed out"
        else:
            message = f"AI provider failed: {type(exc).__name__}"
        for secret in (settings.openai_api_key, settings.xai_api_key):
            if secret:
                message = message.replace(secret, "[REDACTED_SECRET]")
        return message[:500]

    def _default_router(self, settings: AISettings) -> AIRouter:
        self.settings_manager.apply_to_environment(settings)
        return AIRouter(primary=settings.provider, fallback=settings.fallback_provider or None)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(EVIDENCE_ANALYSIS_SCHEMA)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> EvidenceAnalysisRecord:
        payload = json.loads(row["result_json"]) if row["result_json"] else None
        return EvidenceAnalysisRecord(
            analysis_id=row["analysis_id"], evidence_id=row["evidence_id"], job_id=row["job_id"],
            status=row["status"], provider=row["provider"], model=row["model"],
            analysis_version=row["analysis_version"],
            result=StructuredEvidenceAnalysis.from_payload(payload) if payload else None,
            error_message=row["error_message"], redaction_applied=bool(row["redaction_applied"]),
            created_at=row["created_at"], completed_at=row["completed_at"],
        )
