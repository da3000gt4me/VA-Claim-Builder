from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.ai.types import AIResponse
from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceAnalysisError, EvidenceAnalysisService, EvidenceManager
from core.jobs import JobManager
from core.ocr import OCRManager
from core.projects import AppPaths, ProjectManager
from core.settings import AISettings, SettingsManager
from workers import EvidenceAnalysisWorker


def _paths(tmp_path: Path) -> AppPaths:
    root = tmp_path / "app"
    return AppPaths(root=root, projects=root / "Projects", logs=root / "Logs",
                    backups=root / "Backups", settings_file=root / "settings.json").ensure()


def _project(tmp_path: Path):
    paths = _paths(tmp_path)
    return ProjectManager(paths).create_project("AI Evidence"), paths


def _payload(claim_id: str = "") -> dict:
    return {
        "summary": "The record documents a treated back condition.",
        "diagnoses_or_conditions": ["Lumbar strain"],
        "symptoms_and_functional_limitations": ["Limited bending"],
        "treatment_testing_medications": ["Physical therapy"],
        "dates_and_providers": ["2025-01-02 — Dr. Rivera"],
        "in_service_events_or_exposures": ["Reported lifting injury"],
        "nexus_supporting_statements": ["Symptoms continued after service"],
        "aggravation_evidence": [],
        "secondary_service_connection_evidence": [],
        "favorable_evidence": ["Consistent treatment history"],
        "unfavorable_or_contradictory_evidence": [],
        "missing_information_or_clarification_needs": ["Exact onset date"],
        "recommended_claim_associations": ([{
            "claim_id": claim_id, "claim_name": "Back condition", "reason": "Directly discusses the back"
        }] if claim_id else []),
        "confidence": "high",
    }


class FakeRouter:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload; self.error = error; self.requests = []

    def generate_with(self, provider, request):
        self.requests.append((provider, request))
        if self.error: raise self.error
        return AIResponse(provider=provider, model="fake-model", text=json.dumps(self.payload), parsed=self.payload)

    def generate(self, request):
        return self.generate_with("xai" if getattr(self, "use_xai", False) else "openai", request)


def _service(project, paths, router, settings: AISettings | None = None):
    manager = SettingsManager(paths); manager.save_ai_settings(settings or AISettings(openai_api_key="test-key"))
    return EvidenceAnalysisService(project, settings_manager=manager, router_factory=lambda _settings: router)


def test_analysis_migration_is_idempotent_and_has_history_metadata(tmp_path: Path) -> None:
    project, paths = _project(tmp_path)
    ProjectManager(paths).open_project(project.root); ProjectManager(paths).open_project(project.root)
    with sqlite3.connect(project.database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence_analyses)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(evidence_analyses)")}
        version = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    assert {"analysis_id", "evidence_id", "job_id", "status", "provider", "model", "analysis_version",
            "result_json", "error_message", "redaction_applied", "created_at", "completed_at"} <= columns
    assert {"idx_evidence_analyses_evidence", "idx_evidence_analyses_status", "idx_evidence_analyses_job"} <= indexes
    assert version == ("7",)


def test_structured_result_persistence_history_and_reopen(tmp_path: Path) -> None:
    project, paths = _project(tmp_path); claim = ClaimManager(project).create("Back condition")
    evidence = EvidenceManager(project).create("Orthopedic report", description="Ongoing pain", claim_ids=[claim.claim_id])
    router = FakeRouter(_payload(claim.claim_id)); service = _service(project, paths, router)
    first = service.analyze(evidence.evidence_id); second = service.analyze(evidence.evidence_id)
    assert first.status == "completed" and first.result and first.result.confidence == "high"
    assert first.provider == "openai" and first.model == "fake-model" and first.analysis_version == "1.0"
    assert first.redaction_applied is True
    assert [item.analysis_id for item in service.history(evidence.evidence_id)] == [second.analysis_id, first.analysis_id]
    reopened = ProjectManager(paths).open_project(project.root)
    assert EvidenceAnalysisService(reopened, settings_manager=SettingsManager(paths),
                                   router_factory=lambda _settings: router).get(first.analysis_id).result.summary.startswith("The record")


def test_provider_failure_and_malformed_response_are_persisted_safely(tmp_path: Path) -> None:
    project, paths = _project(tmp_path); evidence = EvidenceManager(project).create("Record")
    failing = _service(project, paths, FakeRouter(error=TimeoutError("raw medical text test-key")))
    with pytest.raises(EvidenceAnalysisError, match="timed out"):
        failing.analyze(evidence.evidence_id)
    failed = failing.latest(evidence.evidence_id)
    assert failed and failed.status == "failed" and "test-key" not in failed.error_message
    assert b"test-key" not in project.database_path.read_bytes()

    malformed = _service(project, paths, FakeRouter({"summary": "Incomplete"}))
    with pytest.raises(EvidenceAnalysisError, match="missing required"):
        malformed.analyze(evidence.evidence_id)
    assert malformed.latest(evidence.evidence_id).status == "failed"


def test_local_only_and_missing_credentials_never_call_provider(tmp_path: Path) -> None:
    project, paths = _project(tmp_path); evidence = EvidenceManager(project).create("Record")
    router = FakeRouter(_payload())
    local = _service(project, paths, router, AISettings(local_only=True, openai_api_key="configured"))
    with pytest.raises(EvidenceAnalysisError, match="local-only"):
        local.analyze(evidence.evidence_id)
    assert router.requests == [] and local.latest(evidence.evidence_id).status == "failed"

    missing = _service(project, paths, router, AISettings(openai_api_key=""))
    with pytest.raises(EvidenceAnalysisError, match="credentials"):
        missing.analyze(evidence.evidence_id)
    assert router.requests == []


def test_redaction_is_applied_before_cloud_submission(tmp_path: Path) -> None:
    project, paths = _project(tmp_path)
    claim = ClaimManager(project).create("Back condition")
    source = tmp_path / "record.txt"; source.write_text("Clinical OCR content", encoding="utf-8")
    document, _created = DocumentManager(project).import_file(source); OCRManager(project).process(document.document_id)
    evidence = EvidenceManager(project).create(
        "Record", description="SSN 123-45-6789, vet@example.com", document_id=document.document_id,
        claim_ids=[claim.claim_id], claim_relevance_notes={claim.claim_id: "Supports limitation"},
    )
    router = FakeRouter(_payload()); service = _service(project, paths, router)
    completed = service.analyze(evidence.evidence_id)
    prompt = router.requests[0][1].user_prompt
    assert "123-45-6789" not in prompt and "vet@example.com" not in prompt
    assert "[REDACTED_SSN]" in prompt and completed.redaction_applied is True
    assert "Clinical OCR content" in prompt and "Supports limitation" in prompt

    unredacted_router = FakeRouter(_payload())
    unredacted = _service(project, paths, unredacted_router,
                          AISettings(openai_api_key="key", redact_before_cloud=False))
    result = unredacted.analyze(evidence.evidence_id)
    assert "123-45-6789" in unredacted_router.requests[0][1].user_prompt
    assert result.redaction_applied is False


def test_xai_uses_current_provider_abstraction(tmp_path: Path) -> None:
    project, paths = _project(tmp_path); evidence = EvidenceManager(project).create("Record")
    router = FakeRouter(_payload()); router.use_xai = True
    service = _service(project, paths, router, AISettings(provider="xai", xai_api_key="xai-key", model_xai="grok-test"))
    result = service.analyze(evidence.evidence_id)
    assert router.requests[0][0] == "xai"
    assert result.provider == "xai" and result.model == "fake-model"


def test_cancellation_and_background_job_integration(tmp_path: Path) -> None:
    project, paths = _project(tmp_path); evidence = EvidenceManager(project).create("Record")
    router = FakeRouter(_payload()); service = _service(project, paths, router)
    cancelled = service.analyze(evidence.evidence_id, cancelled=lambda: True)
    assert cancelled.status == "cancelled" and router.requests == []

    factory = lambda _project: service
    worker = EvidenceAnalysisWorker(project, [evidence.evidence_id], service_factory=factory)
    worker.run()
    job = JobManager(project).get(worker.job.job_id)
    assert job.status == "completed" and job.progress == 100
    assert service.latest(evidence.evidence_id).job_id == worker.job.job_id

    cancelled_worker = EvidenceAnalysisWorker(project, [evidence.evidence_id], service_factory=factory)
    cancelled_worker.cancel(); cancelled_worker.run()
    assert JobManager(project).get(cancelled_worker.job.job_id).status == "cancelled"

    interrupted_job = JobManager(project).create("evidence_analysis", {"evidence_ids": [evidence.evidence_id]})
    JobManager(project).update(interrupted_job.job_id, status="running")
    pending = service.create_pending(evidence.evidence_id, job_id=interrupted_job.job_id)
    assert JobManager(project).recover_interrupted() == 1
    assert service.get(pending.analysis_id).status == "failed"
