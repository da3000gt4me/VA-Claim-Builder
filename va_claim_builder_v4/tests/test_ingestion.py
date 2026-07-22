from core.ingestion.categories import DocumentCategory
from core.ingestion.uploader import DocumentIngestor
from core.storage.project_db import ProjectDB

def test_draft_preserved_and_working_copy_created(tmp_path):
    source = tmp_path / "draft.txt"; source.write_text("draft nexus")
    db = ProjectDB(tmp_path / "db.sqlite")
    project = db.create_project("Test")
    result = DocumentIngestor(db, tmp_path / "project").ingest_path(project, source, DocumentCategory.DOCTOR_NEXUS_DRAFTS)
    assert result.original_path.exists()
    assert result.working_path and result.working_path.exists()
    assert result.original_path.read_text() == result.working_path.read_text()
