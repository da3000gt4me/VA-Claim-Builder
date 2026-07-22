from __future__ import annotations

from pathlib import Path

from core.documents import DocumentManager
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


def test_import_copies_and_catalogs_document(tmp_path: Path) -> None:
    project = ProjectManager(_paths(tmp_path)).create_project("Evidence")
    source = tmp_path / "medical-record.txt"
    source.write_text("service treatment record", encoding="utf-8")

    manager = DocumentManager(project)
    document, created = manager.import_file(source)

    assert created is True
    assert document.original_name == "medical-record.txt"
    assert document.stored_path.is_file()
    assert document.stored_path.read_text(encoding="utf-8") == "service treatment record"
    assert manager.list_documents() == [document]


def test_duplicate_content_is_not_imported_twice(tmp_path: Path) -> None:
    project = ProjectManager(_paths(tmp_path)).create_project("Evidence")
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")

    manager = DocumentManager(project)
    original, first_created = manager.import_file(first)
    duplicate, second_created = manager.import_file(second)

    assert first_created is True
    assert second_created is False
    assert duplicate.document_id == original.document_id
    assert len(manager.list_documents()) == 1


def test_remove_deletes_catalog_record_and_stored_file(tmp_path: Path) -> None:
    project = ProjectManager(_paths(tmp_path)).create_project("Evidence")
    source = tmp_path / "statement.txt"
    source.write_text("lay statement", encoding="utf-8")

    manager = DocumentManager(project)
    document, _ = manager.import_file(source)
    manager.remove(document.document_id)

    assert manager.list_documents() == []
    assert not document.stored_path.exists()
