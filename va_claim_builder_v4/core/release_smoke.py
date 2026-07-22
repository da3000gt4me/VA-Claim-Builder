from __future__ import annotations

import json
from pathlib import Path

from core.claims import ClaimManager
from core.evidence import EvidenceManager
from core.maintenance import ProjectMaintenance
from core.projects import ProjectManager
from core.submission import SubmissionGenerator, SubmissionManager


def run_packaged_workflow(manager: ProjectManager, output: str | Path) -> dict:
    """Exercise local packaged services with synthetic data and emit machine-readable results."""
    project = manager.create_project("RC2 Synthetic Smoke")
    claim = ClaimManager(project).create("Synthetic test condition", description="Packaging fixture only")
    evidence = EvidenceManager(project).create(
        "Synthetic evidence", description="No medical data", claim_ids=(claim.claim_id,)
    )
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
