
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.intake import AutomatedIntakeOrchestrator, IntakeManager, LocalMedicalExtractor
from core.intake.extractor import EXTRACTION_VERSION
from core.projects import ProjectManager
from core.timeline import TimelineManager


SYNTHETIC_RECORD = """--- PAGE 1 ---
01/02/2024 Provider: Dr. Alex Smith. Facility: North Test Clinic.
Diagnosis: Lumbar strain.
Symptoms: low back pain, left leg numbness.
Medication: Gabapentin.
MRI showed lumbar degenerative changes.
The back condition limits prolonged standing and interferes with warehouse work.
--- PAGE 2 ---
March 5, 2024 Provider: Dr. Jordan Lee. Specialty: Sleep Medicine.
Diagnosis: Sleep apnea.
Symptoms: daytime fatigue.
Sleep apnea is described as secondary to chronic pain medication use; a provider opinion is still needed.
The patient denies weakness. Symptoms have been chronic since 2022 and are worsened by prolonged activity.
"""


@pytest.fixture()
def project(tmp_path):
    return ProjectManager(home=tmp_path / "app").create_project("RC4 Synthetic")


def import_synthetic(project, tmp_path, text=SYNTHETIC_RECORD):
    source = tmp_path / "synthetic-record.txt"
    source.write_text(text, encoding="utf-8")
    document, created = DocumentManager(project).import_file(source)
    assert created
    return document


def test_local_extraction_covers_medical_metadata_without_provider_calls():
    result = LocalMedicalExtractor().extract(SYNTHETIC_RECORD)
    assert {"2024-01-02", "2024-03-05"} <= set(result.dates)
    assert any("Alex Smith" in item for item in result.providers)
    assert "Lumbar strain" in result.diagnoses
    assert "Sleep apnea" in result.diagnoses
    assert "Gabapentin" in result.medications
    assert result.imaging and result.functional_impacts and result.occupational_impacts
    assert result.relationship_statements and result.aggravation_statements


def test_import_without_analysis_remains_imported(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    assert document.status == "imported"
    state = IntakeManager(project).state(document.document_id)
    assert state.stage == "imported"
    assert state.progress == 0


def test_import_can_queue_analysis(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    orchestrator = AutomatedIntakeOrchestrator(project)
    jobs = orchestrator.queue([document.document_id])
    assert jobs[0].status == "queued"
    assert IntakeManager(project).state(document.document_id).stage == "queued"


def test_end_to_end_local_intake_persists_reviewable_results(project, tmp_path, monkeypatch):
    monkeypatch.setenv("VCB_LOCAL_ONLY", "true")
    existing = ClaimManager(project).create("Lumbar strain", description="Confirmed user text")
    document = import_synthetic(project, tmp_path)
    summary = AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    assert summary.failures == []
    assert summary.evidence_created >= 5
    assert summary.timeline_events_created >= 2
    assert summary.claims_matched == 1
    assert summary.claim_suggestions_created >= 1
    assert summary.relationship_suggestions_created >= 1
    assert ClaimManager(project).get(existing.claim_id).description == "Confirmed user text"
    assert IntakeManager(project).claim_drafts(existing.claim_id)
    assert all(item.review_status == "unreviewed" for item in EvidenceManager(project).list())
    assert all("not user-confirmed" in item.notes for item in TimelineManager(project).list())
    state = IntakeManager(project).state(document.document_id)
    assert state.stage == "review required"
    assert state.extraction_version == EXTRACTION_VERSION
    assert state.processing_scope == "local"

    reopened = ProjectManager(home=tmp_path / "app").open_project(project.root)
    assert len(EvidenceManager(reopened).list()) == len(EvidenceManager(project).list())
    assert len(TimelineManager(reopened).list()) == len(TimelineManager(project).list())
    assert IntakeManager(reopened).list_suggestions(status="pending")


def test_reanalysis_deduplicates_and_preserves_rejection(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    orchestrator = AutomatedIntakeOrchestrator(project)
    orchestrator.analyze_document(document.document_id)
    intake = IntakeManager(project)
    suggestion = intake.list_suggestions(status="pending")[0]
    intake.decide(suggestion.suggestion_id, "rejected")
    before = (len(EvidenceManager(project).list()), len(TimelineManager(project).list()), len(intake.list_suggestions()))
    orchestrator.analyze_document(document.document_id, force=True)
    after = (len(EvidenceManager(project).list()), len(TimelineManager(project).list()), len(intake.list_suggestions()))
    assert before == after
    assert intake.get_suggestion(suggestion.suggestion_id).status == "rejected"


def test_accepting_claim_suggestion_requires_explicit_user_decision(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    intake = IntakeManager(project)
    suggestion = next(item for item in intake.list_suggestions(status="pending", suggestion_type="claim"))
    assert not ClaimManager(project).list_claims()
    accepted = intake.decide(suggestion.suggestion_id, "accepted")
    assert accepted.claim_id
    assert ClaimManager(project).get(accepted.claim_id).condition_name == suggestion.payload["proposed_condition_name"]


def test_cancellation_and_recovery_are_visible(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    orchestrator = AutomatedIntakeOrchestrator(project)
    orchestrator.queue([document.document_id])
    orchestrator.run_documents([document.document_id], cancelled=lambda: True)
    assert IntakeManager(project).state(document.document_id).stage == "cancelled"
    intake = IntakeManager(project)
    intake.update_state(document.document_id, stage="extracting evidence", progress=40)
    assert intake.recover_interrupted() == 1
    state = intake.state(document.document_id)
    assert state.stage == "needs reanalysis"
    assert "interrupted" in state.failure_reason.casefold()


def test_failed_stage_retains_plain_language_error(project, tmp_path):
    document = import_synthetic(project, tmp_path, " ")
    summary = AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    assert summary.failures
    state = IntakeManager(project).state(document.document_id)
    assert state.stage == "failed"
    assert "No text detected" in state.failure_reason
    assert state.retry_eligible


def test_no_cloud_calls_or_raw_text_in_job_messages(project, tmp_path, monkeypatch):
    document = import_synthetic(project, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    with sqlite3.connect(project.database_path) as connection:
        messages = "\n".join(row[0] for row in connection.execute("SELECT message FROM jobs"))
    assert "Lumbar strain" not in messages
    assert "Gabapentin" not in messages
    assert not os.environ.get("OPENAI_API_KEY")
    assert not os.environ.get("XAI_API_KEY")


def test_review_items_include_evidence_timeline_relationships_and_gaps(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    types = {item.suggestion_type for item in IntakeManager(project).list_suggestions()}
    assert {"claim", "relationship", "evidence", "timeline"} <= types


def test_source_traceability(project, tmp_path):
    document = import_synthetic(project, tmp_path)
    AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    assert all(item.document_id == document.document_id for item in EvidenceManager(project).list())
    assert all(item.document_id == document.document_id for item in TimelineManager(project).list())
    report = {
        "documents": [state.document_id for state in IntakeManager(project).list_states()],
        "suggestions": [item.document_id for item in IntakeManager(project).list_suggestions()],
    }
    assert set(report["documents"] + report["suggestions"]) == {document.document_id}
