from __future__ import annotations

import sqlite3
import json
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
    return AppPaths(root=root, projects=root / "Projects", logs=root / "Logs",
                    backups=root / "Backups", settings_file=root / "settings.json").ensure()


def _project(tmp_path: Path):
    return ProjectManager(_paths(tmp_path)).create_project("Increment 7.2")


def test_increment72_migration_fields_and_link_metadata_are_idempotent(tmp_path: Path) -> None:
    paths = _paths(tmp_path); root = paths.projects / "increment-71-project"; root.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    (root / "manifest.json").write_text(json.dumps({
        "project_id": "legacy-71", "name": "Increment 7.1", "schema_version": 2,
        "created_at": now, "updated_at": now, "folders": [],
    }), encoding="utf-8")
    with sqlite3.connect(root / "project.db") as connection:
        connection.executescript("""
            CREATE TABLE schema_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_metadata VALUES('schema_version', '2');
            CREATE TABLE evidence (
                evidence_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                evidence_type TEXT NOT NULL DEFAULT 'other', document_id TEXT, evidence_date TEXT NOT NULL DEFAULT '',
                provider_source TEXT NOT NULL DEFAULT '', relevance_notes TEXT NOT NULL DEFAULT '',
                strength_status TEXT NOT NULL DEFAULT 'unreviewed', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE claim_evidence (
                claim_id TEXT NOT NULL, evidence_id TEXT NOT NULL, linked_at TEXT NOT NULL,
                PRIMARY KEY(claim_id, evidence_id)
            );
            INSERT INTO evidence VALUES('old-evidence', 'Preserved title', '', 'other', NULL, '', '', '', 'unreviewed', 'old', 'old');
        """)
    projects = ProjectManager(paths)
    project = projects.open_project(root); projects.open_project(root)
    with sqlite3.connect(project.database_path) as connection:
        evidence_columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence)")}
        link_columns = {row[1] for row in connection.execute("PRAGMA table_info(claim_evidence)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(evidence)")}
    assert {"review_status", "reviewer_notes", "duplicate_of_evidence_id"} <= evidence_columns
    assert "relevance_notes" in link_columns
    assert {"idx_evidence_review_status", "idx_evidence_duplicate"} <= indexes
    assert EvidenceManager(project).get("old-evidence").title == "Preserved title"


def test_review_status_notes_and_duplicate_reference_persist(tmp_path: Path) -> None:
    project = _project(tmp_path); manager = EvidenceManager(project)
    retained = manager.create("Retained medical record", review_status="relevant")
    duplicate = manager.create("Second copy", review_status="duplicate", reviewer_notes="Same visit",
                               duplicate_of_evidence_id=retained.evidence_id)
    reopened = ProjectManager(_paths(tmp_path)).open_project(project.root)
    record = EvidenceManager(reopened).get(duplicate.evidence_id)
    assert (record.review_status, record.reviewer_notes, record.duplicate_of_evidence_id) == (
        "duplicate", "Same visit", retained.evidence_id,
    )
    with pytest.raises(ValueError):
        manager.update(retained.evidence_id, review_status="duplicate", duplicate_of_evidence_id=retained.evidence_id)
    manager.delete(retained.evidence_id)
    assert manager.get(duplicate.evidence_id).duplicate_of_evidence_id is None


def test_claim_specific_relevance_notes_update_without_duplicate_links(tmp_path: Path) -> None:
    project = _project(tmp_path); claims = ClaimManager(project); manager = EvidenceManager(project)
    migraines = claims.create("Migraines"); tinnitus = claims.create("Tinnitus")
    record = manager.create("Specialist opinion", claim_ids=[migraines.claim_id],
                            claim_relevance_notes={migraines.claim_id: "Establishes frequency"})
    manager.link_claim(record.evidence_id, migraines.claim_id, "Updated frequency rationale")
    manager.link_claim(record.evidence_id, tinnitus.claim_id, "Addresses medication side effects")
    links = manager.claim_links_for_evidence(record.evidence_id)
    assert [(link.condition_name, link.relevance_notes) for link in links] == [
        ("Migraines", "Updated frequency rationale"), ("Tinnitus", "Addresses medication side effects")
    ]
    manager.update(record.evidence_id, claim_ids=[migraines.claim_id],
                   claim_relevance_notes={migraines.claim_id: "Claim-specific note persists"})
    assert manager.claim_links_for_evidence(record.evidence_id)[0].relevance_notes == "Claim-specific note persists"


def test_filters_search_ocr_text_and_stable_sorting(tmp_path: Path) -> None:
    project = _project(tmp_path); claims = ClaimManager(project); manager = EvidenceManager(project)
    claim = claims.create("Back condition")
    source = tmp_path / "orthopedic.txt"; source.write_text("Lumbar radiculopathy confirmed", encoding="utf-8")
    document, created = DocumentManager(project).import_file(source); assert created
    first = manager.create("Orthopedic report", evidence_type="private medical record", document_id=document.document_id,
                           review_status="relevant", claim_ids=[claim.claim_id],
                           claim_relevance_notes={claim.claim_id: "Shows chronic limitation"})
    second = manager.create("Unlinked statement", evidence_type="lay statement", review_status="needs clarification")
    assert [item.evidence_id for item in manager.list(review_status="relevant")] == [first.evidence_id]
    assert [item.evidence_id for item in manager.list(evidence_type="lay statement", unlinked=True)] == [second.evidence_id]
    assert [item.evidence_id for item in manager.list(claim_id=claim.claim_id)] == [first.evidence_id]
    assert [item.evidence_id for item in manager.search("chronic limitation")] == [first.evidence_id]
    assert manager.list(ocr_availability="pending")[0].evidence_id == first.evidence_id
    OCRManager(project).process(document.document_id)
    assert manager.list(ocr_availability="available")[0].evidence_id == first.evidence_id
    assert [item.evidence_id for item in manager.search("radiculopathy")] == [first.evidence_id]
    assert [item.evidence_id for item in manager.list()] == [first.evidence_id, second.evidence_id]
    assert len(DocumentManager(project).list_documents()) == 1
