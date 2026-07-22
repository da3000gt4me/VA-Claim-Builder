from __future__ import annotations

from pathlib import Path

from core.jobs import JobManager
from core.projects import ProjectManager
from core.projects.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    root = tmp_path / "home"
    return AppPaths(
        root=root,
        projects=root / "Projects",
        logs=root / "Logs",
        backups=root / "Backups",
        settings_file=root / "settings.json",
    ).ensure()


def test_jobs_persist_and_update(tmp_path: Path) -> None:
    project = ProjectManager(_paths(tmp_path)).create_project("Job Test")
    jobs = JobManager(project)
    job = jobs.create("document_import", {"files": ["a.pdf"]})

    assert job.status == "queued"
    assert job.progress == 0
    updated = jobs.update(job.job_id, status="running", progress=40, message="Working")
    assert updated.status == "running"
    assert updated.progress == 40
    assert JobManager(project).get(job.job_id).message == "Working"


def test_recover_interrupted_jobs(tmp_path: Path) -> None:
    project = ProjectManager(_paths(tmp_path)).create_project("Recovery Test")
    jobs = JobManager(project)
    job = jobs.create("ocr")
    jobs.update(job.job_id, status="running", progress=20)

    assert jobs.recover_interrupted() == 1
    recovered = jobs.get(job.job_id)
    assert recovered.status == "interrupted"
    assert recovered.progress == 20


def test_progress_is_clamped(tmp_path: Path) -> None:
    project = ProjectManager(_paths(tmp_path)).create_project("Clamp Test")
    jobs = JobManager(project)
    job = jobs.create("test")

    assert jobs.update(job.job_id, progress=150).progress == 100
    assert jobs.update(job.job_id, progress=-5).progress == 0
