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

    def list(self, limit: int = 100) -> list[JobInfo]:
        with sqlite3.connect(self.project.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)
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
