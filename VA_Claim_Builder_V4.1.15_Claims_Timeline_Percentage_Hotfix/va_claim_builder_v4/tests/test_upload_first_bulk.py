from pathlib import Path

from core.claims.form995_parser import Form995ClaimParser
from core.storage.project_db import ProjectDB
from core.workflow.bulk_analysis import BulkProjectAnalysis


def test_form995_parser_extracts_issues_and_skips_form_noise():
    pages = [{
        "page": 1,
        "text": """
        SECTION III: ISSUE(S) FOR SUPPLEMENTAL CLAIM
        1. Migraine headaches
        2. Chronic allergic rhinitis
        3. Irritable bowel syndrome (IBS)
        SECTION IV: NEW AND RELEVANT EVIDENCE
        Please list the evidence you want VA to review.
        """,
    }]
    parsed = Form995ClaimParser().parse_pages(pages)
    names = [x.condition_name for x in parsed]
    assert "Migraine headaches" in names
    assert "Chronic allergic rhinitis" in names
    assert "Irritable bowel syndrome (IBS)" in names
    assert not any("Please list" in x for x in names)


def test_add_missing_claims_is_idempotent(tmp_path: Path):
    db = ProjectDB(tmp_path / "project.db")
    project_id = db.create_project("test")
    pages = [{"page": 1, "text": "ISSUES: 1. Tinnitus\n2. Migraine headaches\nSECTION IV"}]
    first = Form995ClaimParser().add_missing_claims(db, project_id, pages)
    second = Form995ClaimParser().add_missing_claims(db, project_id, pages)
    assert len(first["added"]) == 2
    assert len(second["added"]) == 0
    assert len(db.list_claims(project_id)) == 2


def test_bulk_semantic_runs_every_claim(tmp_path: Path):
    db = ProjectDB(tmp_path / "project.db")
    project_id = db.create_project("test")
    migraine = db.add_claim(project_id, "Migraine headaches", "direct")
    tinnitus = db.add_claim(project_id, "Tinnitus", "direct")
    doc_id = db.add_document({
        "project_id": project_id,
        "category": "03_medical_records",
        "original_name": "record.txt",
        "original_path": str(tmp_path / "record.txt"),
        "sha256": "x" * 64,
        "extraction_status": "complete",
    })
    pg = db.upsert_document_page(project_id, doc_id, 1,
        "Assessment: migraine headaches are chronic and severe. Assessment: tinnitus is persistent.",
        "text", 0.99, False, [])
    db.link_page_claim(pg, migraine)
    db.link_page_claim(pg, tinnitus)
    result = BulkProjectAnalysis(db).run_semantic_all(project_id, auto_populate=False)
    assert result["total_claims"] == 2
    assert set(result["by_claim"]) == {migraine, tinnitus}
