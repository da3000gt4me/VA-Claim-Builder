from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from core.jobs import JobManager
from core.maintenance import MaintenanceError, ProjectMaintenance
from core.projects import AppPaths, ProjectManager
from core.projects.manager import SCHEMA_VERSION
from core.settings import AISettings, SettingsManager
from core.version import BUILD_VERSION, DISPLAY_VERSION


def paths(root: Path) -> AppPaths:
    return AppPaths(root=root).ensure()


def project(tmp_path: Path):
    manager = ProjectManager(paths(tmp_path / "app"))
    return manager, manager.create_project("Synthetic RC Project")


def test_authoritative_release_version() -> None:
    assert DISPLAY_VERSION.startswith("4.2.0 RC")
    assert BUILD_VERSION.startswith("4.2.0rc")
    assert SCHEMA_VERSION == 11


def test_backup_manifest_checksums_and_restore(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    source = opened.root / "uploads" / "record.txt"
    source.write_bytes(b"synthetic non-medical fixture")
    maintenance = ProjectMaintenance(opened, manager)
    archive = maintenance.create_backup(tmp_path / "exports")
    manifest = maintenance.validate_backup(archive)
    assert manifest["project_id"] == opened.project_id
    assert any(item["path"] == "uploads/record.txt" for item in manifest["files"])
    restored = maintenance.restore(archive, tmp_path / "restored")
    assert restored.project_id == opened.project_id
    assert (restored.root / "uploads" / "record.txt").read_bytes() == source.read_bytes()


def test_backup_can_exclude_large_sources(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    (opened.root / "uploads" / "large.bin").write_bytes(b"x" * 128)
    maintenance = ProjectMaintenance(opened, manager)
    archive = maintenance.create_backup(tmp_path / "exports", include_sources=False)
    manifest = maintenance.validate_backup(archive)
    assert manifest["include_sources"] is False
    assert not any(item["path"].startswith("uploads/") for item in manifest["files"])


def test_backup_corruption_is_rejected(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    archive = ProjectMaintenance(opened, manager).create_backup(tmp_path / "exports")
    archive.write_bytes(archive.read_bytes()[:80])
    with pytest.raises(MaintenanceError, match="corrupted"):
        ProjectMaintenance(opened, manager).validate_backup(archive)


def test_archive_path_traversal_is_rejected(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    archive = tmp_path / "unsafe.zip"
    manifest = {"format": "va-claim-builder-backup-v1", "files": [{"path": "../escape", "sha256": "0"}]}
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape", "bad")
        handle.writestr("backup-manifest.json", json.dumps(manifest))
    with pytest.raises(MaintenanceError, match="unsafe"):
        ProjectMaintenance(opened, manager).validate_backup(archive)


def test_restore_requires_explicit_overwrite(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    maintenance = ProjectMaintenance(opened, manager)
    archive = maintenance.create_backup(tmp_path / "exports")
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(MaintenanceError, match="explicit overwrite"):
        maintenance.restore(archive, target)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_validation_and_safe_repair(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    (opened.root / "reports").rmdir()
    (opened.root / "temp" / "stale.tmp").write_text("partial", encoding="utf-8")
    maintenance = ProjectMaintenance(opened, manager)
    issues = maintenance.validate_project()
    assert {issue["code"] for issue in issues} >= {"missing_folder", "stale_temp"}
    maintenance.repair_safe()
    assert (opened.root / "reports").is_dir()
    assert not (opened.root / "temp" / "stale.tmp").exists()


def test_diagnostics_are_sanitized(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    secret = "PRIVATE-MEDICAL-TEXT-API-KEY"
    (opened.root / "uploads" / "secret.txt").write_text(secret, encoding="utf-8")
    output = ProjectMaintenance(opened, manager).export_diagnostics(tmp_path / "diagnostics.json")
    text = output.read_text(encoding="utf-8")
    assert secret not in text
    assert BUILD_VERSION in text


def test_migration_failure_restores_original_database(tmp_path: Path, monkeypatch) -> None:
    manager, opened = project(tmp_path)
    with sqlite3.connect(opened.database_path) as connection:
        connection.execute("UPDATE schema_metadata SET value='9' WHERE key='schema_version'")
        connection.execute("CREATE TABLE preservation(value TEXT)")
        connection.execute("INSERT INTO preservation VALUES('keep-me')")
        connection.commit()

    def fail(path):
        with sqlite3.connect(path) as connection:
            connection.execute("DELETE FROM preservation")
            connection.commit()
        raise RuntimeError("simulated migration interruption")

    monkeypatch.setattr(manager, "_migrate_database", fail)
    with pytest.raises(RuntimeError):
        manager.open_project(opened.root)
    with sqlite3.connect(opened.database_path) as connection:
        assert connection.execute("SELECT value FROM preservation").fetchone() == ("keep-me",)
    assert list(manager.paths.backups.glob("migration-*.db"))


def test_invalid_future_schema_is_rejected(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    with sqlite3.connect(opened.database_path) as connection:
        connection.execute("UPDATE schema_metadata SET value='999' WHERE key='schema_version'")
        connection.commit()
    with pytest.raises(ValueError, match="newer"):
        manager.open_project(opened.root)


def test_job_duplicate_prevention_pagination_and_recovery(tmp_path: Path) -> None:
    _, opened = project(tmp_path)
    jobs = JobManager(opened)
    first = jobs.create_unique("backup", {"scope": opened.project_id})
    assert jobs.create_unique("backup", {"scope": opened.project_id}).job_id == first.job_id
    jobs.update(first.job_id, status="running")
    assert jobs.recover_interrupted() == 1
    assert jobs.get(first.job_id).status == "interrupted"
    assert jobs.list(limit=1, offset=0, status="interrupted")[0].job_id == first.job_id


def test_settings_recover_and_export_without_credentials(tmp_path: Path) -> None:
    manager = SettingsManager(paths(tmp_path / "settings"))
    manager.paths.settings_file.write_text("not-json", encoding="utf-8")
    assert manager.load_app_settings()["backup_retention"] == 10
    manager.save_ai_settings(AISettings(openai_api_key="secret-openai", xai_api_key="secret-xai", local_only=True))
    exported = manager.export_settings(tmp_path / "settings-export.json")
    text = exported.read_text(encoding="utf-8")
    assert "secret-openai" not in text and "secret-xai" not in text
    assert json.loads(text)["ai"]["local_only"] is True


def test_backup_retention_never_removes_only_valid_backup(tmp_path: Path) -> None:
    manager, opened = project(tmp_path)
    maintenance = ProjectMaintenance(opened, manager)
    archive = maintenance.create_backup(tmp_path / "exports", retention=0)
    assert archive.exists()


def test_release_build_configuration_is_complete() -> None:
    root = Path(__file__).resolve().parents[1]
    assert "desktop_app.py" in (root / "packaging" / "VAClaimBuilder.spec").read_text(encoding="utf-8")
    for name in ("build_macos.sh", "build_linux.sh", "build_windows.bat", "build_portable.sh"):
        assert (root / "scripts" / name).is_file()
    for name in ("QUICK_START.md", "INSTALLATION.md", "BACKUP_RESTORE.md", "PRIVACY_DATA_HANDLING.md", "TROUBLESHOOTING.md", "RELEASE_NOTES_4.2.0_RC1.md"):
        assert (root / "docs" / name).is_file()
