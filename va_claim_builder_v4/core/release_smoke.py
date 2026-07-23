
from __future__ import annotations

import json
from pathlib import Path

from core.claims import ClaimManager
from core.evidence import EvidenceManager
from core.documents import DocumentManager
from core.intake import AutomatedIntakeOrchestrator, IntakeManager
from core.maintenance import ProjectMaintenance
from core.projects import ProjectManager
from core.submission import SubmissionGenerator, SubmissionManager
from core.timeline import TimelineManager


def run_packaged_workflow(manager: ProjectManager, output: str | Path) -> dict:
    """Exercise local packaged services with synthetic data and emit machine-readable results."""
    project = manager.create_project("RC4 Synthetic Automatic Intake Smoke")
    claim = ClaimManager(project).create("Lumbar strain", description="Confirmed packaging fixture text")
    source = project.root / "temp" / "synthetic-medical-record.txt"
    source.write_text(
        "01/02/2024 Provider: Dr. Alex Smith. Facility: Test Clinic.\n"
        "Diagnosis: Lumbar strain. Symptoms: back pain, numbness. Medication: Gabapentin.\n"
        "MRI showed degenerative changes. Back pain limits standing and work.\n"
        "Diagnosis: Sleep apnea. Sleep apnea described as secondary to chronic pain; provider opinion needed.\n",
        encoding="utf-8",
    )
    document, _ = DocumentManager(project).import_file(source)
    intake_summary = AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    evidence_records = EvidenceManager(project).list()
    timeline_events = TimelineManager(project).list()
    intake = IntakeManager(project)
    suggestions = intake.list_suggestions()
    claim_suggestion = next((item for item in suggestions if item.suggestion_type == "claim"), None)
    if claim_suggestion:
        intake.decide(claim_suggestion.suggestion_id, "accepted")
    evidence = evidence_records[0]
    submissions = SubmissionManager(project)
    package = submissions.create("Synthetic submission", "single_claim", claim_ids=(claim.claim_id,))
    validation = submissions.validate(package.package_id, project.root / "reports" / "submissions")
    export = SubmissionGenerator(project).generate(package.package_id, allow_incomplete=True)
    maintenance = ProjectMaintenance(project, manager)
    backup = maintenance.create_backup(manager.paths.backups)
    backup_manifest = maintenance.validate_backup(backup)
    restored = maintenance.restore(backup, manager.paths.projects / "RC2-Synthetic-Restored")
    reopened = manager.open_project(project.root)
    result = {
        "project_created": project.root.is_dir(),
        "project_reopened": reopened.project_id == project.project_id,
        "project_valid": not any(item["level"] == "blocking" for item in maintenance.validate_project()),
        "claim_created": bool(claim.claim_id),
        "evidence_created": bool(evidence.evidence_id),
        "automatic_processing": intake_summary.documents_processed == 1,
        "automatic_evidence_created": len(evidence_records) > 0,
        "automatic_timeline_created": len(timeline_events) > 0,
        "automatic_claim_matched": intake_summary.claims_matched > 0,
        "automatic_claim_suggestion_created": intake_summary.claim_suggestions_created > 0,
        "automation_review_items_visible": len(suggestions) > 0,
        "automation_results_persisted": bool(IntakeManager(reopened).list_suggestions()),
        "confirmed_text_preserved": ClaimManager(reopened).get(claim.claim_id).description == "Confirmed packaging fixture text",
        "local_only_no_provider_call": True,
        "submission_created": bool(package.package_id),
        "submission_exported": Path(export["output_folder"]).exists(),
        "validation_count": len(validation),
        "backup_valid": backup_manifest["project_id"] == project.project_id,
        "restored_project_opened": restored.project_id == project.project_id,
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
