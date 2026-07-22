from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.projects import ProjectInfo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class JobInfo:
    job_id: str
    job_type: str
    status: str
    progress: int
    message: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str


class JobManager:
    """Persistent project-scoped background job registry."""

    def __init__(self, project: ProjectInfo) -> None:
        self.project = project
        self._ensure_schema()

    def create(self, job_type: str, payload: dict[str, Any] | None = None) -> JobInfo:
        job_id = str(uuid.uuid4())
        now = _utc_now()
        with sqlite3.connect(self.project.database_path) as connection:
            connection.execute(
                """
                INSERT INTO jobs(job_id, job_type, status, progress, message, payload_json, created_at, updated_at)
                VALUES(?, ?, 'queued', 0, 'Queued', ?, ?, ?)
                """,
                (job_id, job_type, json.dumps(payload or {}), now, now),
            )
            connection.commit()
        return self.get(job_id)

    def create_unique(self, job_type: str, payload: dict[str, Any] | None = None) -> JobInfo:
        """Return an equivalent active job instead of scheduling a duplicate."""
        encoded = json.dumps(payload or {}, sort_keys=True)
        with sqlite3.connect(self.project.database_path) as connection:
            row = connection.execute(
                "SELECT job_id FROM jobs WHERE job_type=? AND payload_json=? "
                "AND status IN ('queued','running','cancelling') ORDER BY created_at LIMIT 1",
                (job_type, encoded),
            ).fetchone()
        return self.get(row[0]) if row else self.create(job_type, payload)

    def update(self, job_id: str, *, status: str | None = None, progress: int | None = None, message: str | None = None) -> JobInfo:
        current = self.get(job_id)
        new_progress = current.progress if progress is None else max(0, min(100, int(progress)))
        with sqlite3.connect(self.project.database_path) as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, progress = ?, message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status or current.status,
                    new_progress,
                    current.message if message is None else message,
                    _utc_now(),
                    job_id,
                ),
            )
            connection.commit()
        return self.get(job_id)

    def get(self, job_id: str) -> JobInfo:
        with sqlite3.connect(self.project.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._from_row(row)

    def list(self, limit: int = 100, *, offset: int = 0, status: str = "") -> list[JobInfo]:
        with sqlite3.connect(self.project.database_path) as connection:
            connection.row_factory = sqlite3.Row
            if status:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, max(1, int(limit)), max(0, int(offset))),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (max(1, int(limit)), max(0, int(offset))),
                ).fetchall()
        return [self._from_row(row) for row in rows]

    def recover_interrupted(self) -> int:
        with sqlite3.connect(self.project.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'interrupted', message = 'Application closed before completion', updated_at = ?
                WHERE status IN ('queued', 'running', 'cancelling')
                """,
                (_utc_now(),),
            )
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_analyses'"
            ).fetchone()
            if table:
                connection.execute(
                    "UPDATE evidence_analyses SET status='failed', "
                    "error_message='Application closed before analysis completed', completed_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
            timeline_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='timeline_extractions'"
            ).fetchone()
            if timeline_table:
                connection.execute(
                    "UPDATE timeline_extractions SET status='failed', "
                    "error_message='Application closed before extraction completed', completed_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
            nexus_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nexus_generations'"
            ).fetchone()
            if nexus_table:
                connection.execute(
                    "UPDATE nexus_generations SET status='failed', "
                    "error_message='Application closed before generation completed', completed_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
            dbq_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dbq_generations'"
            ).fetchone()
            if dbq_table:
                connection.execute(
                    "UPDATE dbq_generations SET status='failed', "
                    "error_message='Application closed before DBQ preparation completed', completed_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
            rating_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rating_strategies'"
            ).fetchone()
            if rating_table:
                connection.execute(
                    "UPDATE rating_strategies SET status='failed', "
                    "error_message='Application closed before rating analysis completed', updated_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
            optimizer_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='optimizer_assessments'"
            ).fetchone()
            if optimizer_table:
                connection.execute(
                    "UPDATE optimizer_assessments SET status='failed', "
                    "error_message='Application closed before optimization completed', updated_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
            submission_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='submission_exports'"
            ).fetchone()
            if submission_table:
                connection.execute(
                    "UPDATE submission_exports SET status='failed', "
                    "error_message='Application closed before package generation completed', completed_at=? "
                    "WHERE status='pending' AND job_id IN (SELECT job_id FROM jobs WHERE status='interrupted')",
                    (_utc_now(),),
                )
                connection.execute(
                    "UPDATE submission_packages SET status='failed',updated_at=? WHERE package_id IN "
                    "(SELECT package_id FROM submission_exports WHERE status='failed' AND job_id IN "
                    "(SELECT job_id FROM jobs WHERE status='interrupted'))",
                    (_utc_now(),),
                )
            connection.commit()
            return cursor.rowcount

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.project.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_updated ON jobs(status, updated_at DESC)"
            )
            connection.commit()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> JobInfo:
        return JobInfo(
            job_id=row["job_id"],
            job_type=row["job_type"],
            status=row["status"],
            progress=int(row["progress"]),
            message=row["message"],
            payload=json.loads(row["payload_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
