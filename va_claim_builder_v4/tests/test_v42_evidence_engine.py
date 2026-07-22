from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.ocr import OCRManager
from core.projects import AppPaths, ProjectManager


def _paths(tmp_path: Path) -> AppPaths:
    root = tmp_path / "app-data"
    return AppPaths(
        root=root,
        projects=root / "Projects",
        logs=root / "Logs",
        backups=root / "Backups",
        settings_file=root / "settings.json",
    ).ensure()


def _project(tmp_path: Path):
    return ProjectManager(_paths(tmp_path)).create_project("Evidence Engine")


def test_evidence_migration_is_present_and_idempotent(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = ProjectManager(paths)
    project = manager.create_project("Migration")
    manager.open_project(project.root)
    manager.open_project(project.root)

    with sqlite3.connect(project.database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        evidence_fks = connection.execute("PRAGMA foreign_key_list(evidence)").fetchall()
        link_fks = connection.execute("PRAGMA foreign_key_list(claim_evidence)").fetchall()
        version = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()

    assert {"evidence", "claim_evidence"}.issubset(tables)
    assert {"idx_evidence_type", "idx_evidence_document", "idx_claim_evidence_claim"}.issubset(indexes)
    assert any(row[2] == "documents" and row[6] == "SET NULL" for row in evidence_fks)
    assert {row[2] for row in link_fks} == {"claims", "evidence"}
    assert version == ("2",)


def test_evidence_crud_filter_and_search(tmp_path: Path) -> None:
    manager = EvidenceManager(_project(tmp_path))
    first = manager.create(
        "Audiology nexus opinion",
        description="Links tinnitus to hazardous noise exposure",
        evidence_type="medical opinion",
        evidence_date="2025-03-12",
        provider_source="Dr. Rivera",
        relevance_notes="Supports nexus",
        strength_status="strong",
    )
    manager.create("Personal statement", evidence_type="lay statement", provider_source="Veteran")

    assert manager.get(first.evidence_id).provider_source == "Dr. Rivera"
    assert [item.evidence_id for item in manager.list(evidence_type="medical opinion")] == [first.evidence_id]
    assert [item.evidence_id for item in manager.search("hazardous")] == [first.evidence_id]
    updated = manager.update(first.evidence_id, title="Updated audiology opinion", strength_status="supportive")
    assert updated.title == "Updated audiology opinion"
    assert updated.strength_status == "supportive"

    manager.delete(first.evidence_id)
    with pytest.raises(KeyError):
        manager.get(first.evidence_id)
    with pytest.raises(ValueError):
        manager.create("")


def test_claim_evidence_many_to_many_links_and_cascades(tmp_path: Path) -> None:
    project = _project(tmp_path)
    claims = ClaimManager(project)
    evidence = EvidenceManager(project)
    tinnitus = claims.create("Tinnitus")
    hearing_loss = claims.create("Hearing loss")
    opinion = evidence.create("Audiology opinion", claim_ids=[tinnitus.claim_id, hearing_loss.claim_id])
    statement = evidence.create("Buddy statement")

    evidence.link_claim(statement.evidence_id, tinnitus.claim_id)
    evidence.link_claim(statement.evidence_id, tinnitus.claim_id)
    assert {item.evidence_id for item in evidence.evidence_for_claim(tinnitus.claim_id)} == {
        opinion.evidence_id, statement.evidence_id,
    }
    assert {claim.claim_id for claim in evidence.claims_for_evidence(opinion.evidence_id)} == {
        tinnitus.claim_id, hearing_loss.claim_id,
    }

    evidence.unlink_claim(opinion.evidence_id, tinnitus.claim_id)
    assert [claim.claim_id for claim in evidence.claims_for_evidence(opinion.evidence_id)] == [hearing_loss.claim_id]
    claims.delete(hearing_loss.claim_id)
    assert evidence.claims_for_evidence(opinion.evidence_id) == []


def test_document_reference_and_ocr_status_do_not_duplicate_source(tmp_path: Path) -> None:
    project = _project(tmp_path)
    source = tmp_path / "record.txt"
    source.write_text("Medical evidence", encoding="utf-8")
    document, _ = DocumentManager(project).import_file(source)
    evidence = EvidenceManager(project)
    record = evidence.create("Treatment record", document_id=document.document_id)

    assert record.document_name == "record.txt"
    assert record.ocr_status == "pending"
    assert len(DocumentManager(project).list_documents()) == 1
    OCRManager(project).process(document.document_id)
    assert evidence.get(record.evidence_id).ocr_status == "available"

    DocumentManager(project).remove(document.document_id)
    preserved = evidence.get(record.evidence_id)
    assert preserved.document_id is None
    assert preserved.ocr_status == "not associated"


def test_evidence_persists_across_project_reopen(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    projects = ProjectManager(paths)
    project = projects.create_project("Persistence")
    claim = ClaimManager(project).create("Migraines")
    record = EvidenceManager(project).create("Headache log", claim_ids=[claim.claim_id])

    reopened = projects.open_project(project.root)
    reopened_manager = EvidenceManager(reopened)
    assert reopened_manager.get(record.evidence_id).title == "Headache log"
    assert reopened_manager.evidence_for_claim(claim.claim_id)[0].evidence_id == record.evidence_id


def test_pre_migration_project_is_upgraded_without_data_loss(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    root = paths.projects / "legacy-v42"
    root.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "project_id": "legacy-project", "name": "Legacy V4.2", "schema_version": 1,
        "created_at": now, "updated_at": now, "folders": ["uploads", "ocr"],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with sqlite3.connect(root / "project.db") as connection:
        connection.executescript(
            """CREATE TABLE schema_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
               INSERT INTO schema_metadata VALUES('schema_version', '1');
               CREATE TABLE project_metadata(project_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
               INSERT INTO project_metadata VALUES('legacy-project', 'Legacy V4.2', 'old-created', 'old-updated');"""
        )

    project = ProjectManager(paths).open_project(root)
    created = EvidenceManager(project).create("Legacy-compatible evidence")

    assert EvidenceManager(project).get(created.evidence_id).title == "Legacy-compatible evidence"
    with sqlite3.connect(project.database_path) as connection:
        metadata = connection.execute("SELECT name, created_at FROM project_metadata").fetchone()
    assert metadata == ("Legacy V4.2", "old-created")
    assert json.loads((root / "manifest.json").read_text(encoding="utf-8"))["schema_version"] == 2
