from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.projects import AppPaths, ProjectManager


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        home=tmp_path,
        projects=tmp_path / "Projects",
        logs=tmp_path / "Logs",
        backups=tmp_path / "Backups",
        settings_file=tmp_path / "settings.json",
    ).ensure()


def test_create_project_initializes_manifest_database_and_folders(tmp_path: Path) -> None:
    manager = ProjectManager(_paths(tmp_path))
    project = manager.create_project("Nick Claim")

    assert project.manifest_path.exists()
    assert project.database_path.exists()
    manifest = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "Nick Claim"
    for folder in manifest["folders"]:
        assert (project.root / folder).is_dir()

    with sqlite3.connect(project.database_path) as connection:
        version = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    assert version == ("8",)


def test_open_project_restores_missing_required_folder(tmp_path: Path) -> None:
    manager = ProjectManager(_paths(tmp_path))
    project = manager.create_project("Restore Test")
    (project.root / "reports").rmdir()

    reopened = manager.open_project(project.root)
    assert (reopened.root / "reports").is_dir()


def test_recent_and_last_opened_projects_persist(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = ProjectManager(paths)
    created = manager.create_project("Recent Test")

    other_manager = ProjectManager(paths)
    assert other_manager.list_recent_projects()[0]["project_id"] == created.project_id
    assert other_manager.last_opened_project().project_id == created.project_id
