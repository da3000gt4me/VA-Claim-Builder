from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from core.projects import ProjectInfo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


CLAIM_TYPES = ("direct", "secondary", "aggravation", "presumptive", "increase", "other")
CLAIM_STATUSES = ("draft", "developing", "ready", "submitted", "decided")


@dataclass(frozen=True, slots=True)
class ClaimInfo:
    claim_id: str
    condition_name: str
    claim_type: str
    secondary_to: str
    status: str
    description: str
    service_event: str
    current_diagnosis: str
    symptoms: str
    notes: str
    sort_order: int
    created_at: str
    updated_at: str


class ClaimManager:
    """Persistent CRUD manager for a project's claimed conditions."""

    def __init__(self, project: ProjectInfo) -> None:
        self.project = project
        self._ensure_schema()

    def create(
        self,
        condition_name: str,
        *,
        claim_type: str = "direct",
        secondary_to: str = "",
        status: str = "draft",
        description: str = "",
        service_event: str = "",
        current_diagnosis: str = "",
        symptoms: str = "",
        notes: str = "",
    ) -> ClaimInfo:
        name = condition_name.strip()
        if not name:
            raise ValueError("Condition name is required")
        self._validate(claim_type, status)
        now = _utc_now()
        claim_id = str(uuid.uuid4())
        with sqlite3.connect(self.project.database_path) as connection:
            next_order = connection.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM claims"
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO claims(
                    claim_id, condition_name, claim_type, secondary_to, status,
                    description, service_event, current_diagnosis, symptoms, notes,
                    sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id, name, claim_type, secondary_to.strip(), status,
                    description.strip(), service_event.strip(), current_diagnosis.strip(),
                    symptoms.strip(), notes.strip(), int(next_order), now, now,
                ),
            )
            connection.commit()
        return self.get(claim_id)

    def update(self, claim_id: str, **changes: object) -> ClaimInfo:
        allowed = {
            "condition_name", "claim_type", "secondary_to", "status", "description",
            "service_event", "current_diagnosis", "symptoms", "notes", "sort_order",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported claim fields: {', '.join(sorted(unknown))}")
        current = self.get(claim_id)
        values = {field: getattr(current, field) for field in allowed}
        values.update(changes)
        values["condition_name"] = str(values["condition_name"]).strip()
        if not values["condition_name"]:
            raise ValueError("Condition name is required")
        values["claim_type"] = str(values["claim_type"])
        values["status"] = str(values["status"])
        self._validate(values["claim_type"], values["status"])
        for field in allowed - {"sort_order"}:
            values[field] = str(values[field]).strip()
        values["sort_order"] = int(values["sort_order"])
        assignments = ", ".join(f"{field} = ?" for field in sorted(allowed))
        params = [values[field] for field in sorted(allowed)] + [_utc_now(), claim_id]
        with sqlite3.connect(self.project.database_path) as connection:
            connection.execute(
                f"UPDATE claims SET {assignments}, updated_at = ? WHERE claim_id = ?",
                params,
            )
            connection.commit()
        return self.get(claim_id)

    def get(self, claim_id: str) -> ClaimInfo:
        with sqlite3.connect(self.project.database_path) as connection:
            row = connection.execute(
                """
                SELECT claim_id, condition_name, claim_type, secondary_to, status,
                       description, service_event, current_diagnosis, symptoms, notes,
                       sort_order, created_at, updated_at
                FROM claims WHERE claim_id = ?
                """,
                (claim_id,),
            ).fetchone()
        if row is None:
            raise KeyError(claim_id)
        return ClaimInfo(*row)

    def list_claims(self) -> list[ClaimInfo]:
        with sqlite3.connect(self.project.database_path) as connection:
            rows = connection.execute(
                """
                SELECT claim_id, condition_name, claim_type, secondary_to, status,
                       description, service_event, current_diagnosis, symptoms, notes,
                       sort_order, created_at, updated_at
                FROM claims ORDER BY sort_order, condition_name COLLATE NOCASE
                """
            ).fetchall()
        return [ClaimInfo(*row) for row in rows]

    def delete(self, claim_id: str) -> None:
        with sqlite3.connect(self.project.database_path) as connection:
            cursor = connection.execute("DELETE FROM claims WHERE claim_id = ?", (claim_id,))
            if cursor.rowcount == 0:
                raise KeyError(claim_id)
            connection.commit()
        self.normalize_sort_order()

    def move(self, claim_id: str, offset: int) -> None:
        claims = self.list_claims()
        index = next((i for i, claim in enumerate(claims) if claim.claim_id == claim_id), None)
        if index is None:
            raise KeyError(claim_id)
        target = max(0, min(len(claims) - 1, index + offset))
        if target == index:
            return
        claims[index], claims[target] = claims[target], claims[index]
        with sqlite3.connect(self.project.database_path) as connection:
            connection.executemany(
                "UPDATE claims SET sort_order = ?, updated_at = ? WHERE claim_id = ?",
                [(position, _utc_now(), claim.claim_id) for position, claim in enumerate(claims)],
            )
            connection.commit()

    def normalize_sort_order(self) -> None:
        claims = self.list_claims()
        with sqlite3.connect(self.project.database_path) as connection:
            connection.executemany(
                "UPDATE claims SET sort_order = ? WHERE claim_id = ?",
                [(position, claim.claim_id) for position, claim in enumerate(claims)],
            )
            connection.commit()

    @staticmethod
    def _validate(claim_type: str, status: str) -> None:
        if claim_type not in CLAIM_TYPES:
            raise ValueError(f"Unsupported claim type: {claim_type}")
        if status not in CLAIM_STATUSES:
            raise ValueError(f"Unsupported claim status: {status}")

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.project.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    condition_name TEXT NOT NULL,
                    claim_type TEXT NOT NULL,
                    secondary_to TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    description TEXT NOT NULL DEFAULT '',
                    service_event TEXT NOT NULL DEFAULT '',
                    current_diagnosis TEXT NOT NULL DEFAULT '',
                    symptoms TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
                CREATE INDEX IF NOT EXISTS idx_claims_order ON claims(sort_order);
                """
            )
            connection.commit()
