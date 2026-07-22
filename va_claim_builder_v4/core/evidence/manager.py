from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from core.projects import ProjectInfo
from core.projects.manager import EVIDENCE_SCHEMA


EVIDENCE_TYPES = (
    "service treatment record",
    "private medical record",
    "va medical record",
    "medical opinion",
    "dbq",
    "lay statement",
    "service record",
    "examination",
    "decision",
    "correspondence",
    "other",
)
EVIDENCE_STRENGTHS = ("unreviewed", "supportive", "strong", "neutral", "weak", "contradictory")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    title: str
    description: str
    evidence_type: str
    document_id: str | None
    evidence_date: str
    provider_source: str
    relevance_notes: str
    strength_status: str
    created_at: str
    updated_at: str
    document_name: str | None = None
    document_status: str | None = None
    ocr_status: str = "not associated"


class EvidenceManager:
    """Persistent evidence catalog and claim-link service for one project."""

    _FIELDS = (
        "title", "description", "evidence_type", "document_id", "evidence_date",
        "provider_source", "relevance_notes", "strength_status",
    )

    def __init__(self, project: ProjectInfo) -> None:
        self.project = project
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.project.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create(
        self,
        title: str,
        *,
        description: str = "",
        evidence_type: str = "other",
        document_id: str | None = None,
        evidence_date: str = "",
        provider_source: str = "",
        relevance_notes: str = "",
        strength_status: str = "unreviewed",
        claim_ids: Iterable[str] = (),
    ) -> Evidence:
        values = self._validated_values({
            "title": title, "description": description, "evidence_type": evidence_type,
            "document_id": document_id, "evidence_date": evidence_date,
            "provider_source": provider_source, "relevance_notes": relevance_notes,
            "strength_status": strength_status,
        })
        evidence_id = str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO evidence(
                    evidence_id, title, description, evidence_type, document_id,
                    evidence_date, provider_source, relevance_notes, strength_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (evidence_id, *(values[field] for field in self._FIELDS), now, now),
            )
            self._replace_links(connection, evidence_id, claim_ids)
        return self.get(evidence_id)

    def get(self, evidence_id: str) -> Evidence:
        with self._connect() as connection:
            row = connection.execute(self._select_sql() + " WHERE e.evidence_id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return Evidence(*row)

    def update(self, evidence_id: str, *, claim_ids: Iterable[str] | None = None, **changes: object) -> Evidence:
        unknown = set(changes) - set(self._FIELDS)
        if unknown:
            raise ValueError(f"Unsupported evidence fields: {', '.join(sorted(unknown))}")
        current = self.get(evidence_id)
        values = {field: getattr(current, field) for field in self._FIELDS}
        values.update(changes)
        values = self._validated_values(values)
        assignments = ", ".join(f"{field} = ?" for field in self._FIELDS)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE evidence SET {assignments}, updated_at = ? WHERE evidence_id = ?",
                (*(values[field] for field in self._FIELDS), _utc_now(), evidence_id),
            )
            if claim_ids is not None:
                self._replace_links(connection, evidence_id, claim_ids)
        return self.get(evidence_id)

    def delete(self, evidence_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM evidence WHERE evidence_id = ?", (evidence_id,))
            if cursor.rowcount == 0:
                raise KeyError(evidence_id)

    def list(
        self,
        *,
        evidence_type: str | None = None,
        claim_id: str | None = None,
        search: str = "",
    ) -> list[Evidence]:
        clauses: list[str] = []
        params: list[str] = []
        if evidence_type:
            clauses.append("e.evidence_type = ?")
            params.append(evidence_type)
        if claim_id:
            clauses.append("EXISTS (SELECT 1 FROM claim_evidence ce WHERE ce.evidence_id=e.evidence_id AND ce.claim_id=?)")
            params.append(claim_id)
        term = search.strip()
        if term:
            clauses.append("(e.title LIKE ? OR e.description LIKE ? OR e.provider_source LIKE ? OR e.relevance_notes LIKE ? OR COALESCE(d.original_name, '') LIKE ?)")
            params.extend([f"%{term}%"] * 5)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                self._select_sql() + where + " ORDER BY e.evidence_date DESC, e.updated_at DESC, e.title COLLATE NOCASE",
                params,
            ).fetchall()
        return [Evidence(*row) for row in rows]

    def search(self, query: str) -> list[Evidence]:
        return self.list(search=query)

    def link_claim(self, evidence_id: str, claim_id: str) -> None:
        self.get(evidence_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO claim_evidence(claim_id, evidence_id, linked_at) VALUES (?, ?, ?)",
                (claim_id, evidence_id, _utc_now()),
            )

    def unlink_claim(self, evidence_id: str, claim_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM claim_evidence WHERE evidence_id = ? AND claim_id = ?",
                (evidence_id, claim_id),
            )

    def evidence_for_claim(self, claim_id: str) -> list[Evidence]:
        return self.list(claim_id=claim_id)

    def claims_for_evidence(self, evidence_id: str) -> list[object]:
        from core.claims import ClaimInfo
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT c.claim_id, c.condition_name, c.claim_type, c.secondary_to, c.status,
                          c.description, c.service_event, c.current_diagnosis, c.symptoms, c.notes,
                          c.sort_order, c.created_at, c.updated_at
                   FROM claims c JOIN claim_evidence ce ON ce.claim_id=c.claim_id
                   WHERE ce.evidence_id=? ORDER BY c.sort_order, c.condition_name COLLATE NOCASE""",
                (evidence_id,),
            ).fetchall()
        return [ClaimInfo(*row) for row in rows]

    @staticmethod
    def _select_sql() -> str:
        return """SELECT e.evidence_id, e.title, e.description, e.evidence_type,
                         e.document_id, e.evidence_date, e.provider_source,
                         e.relevance_notes, e.strength_status, e.created_at, e.updated_at,
                         d.original_name, d.status,
                         CASE WHEN e.document_id IS NULL THEN 'not associated'
                              WHEN o.document_id IS NOT NULL THEN 'available'
                              ELSE 'pending' END
                  FROM evidence e
                  LEFT JOIN documents d ON d.document_id=e.document_id
                  LEFT JOIN ocr_results o ON o.document_id=e.document_id"""

    def _validated_values(self, values: dict[str, object]) -> dict[str, str | None]:
        normalized: dict[str, str | None] = {}
        for field in self._FIELDS:
            value = values.get(field)
            normalized[field] = None if field == "document_id" and not value else str(value or "").strip()
        if not normalized["title"]:
            raise ValueError("Evidence title is required")
        if normalized["evidence_type"] not in EVIDENCE_TYPES:
            raise ValueError(f"Unsupported evidence type: {normalized['evidence_type']}")
        if normalized["strength_status"] not in EVIDENCE_STRENGTHS:
            raise ValueError(f"Unsupported evidence strength/status: {normalized['strength_status']}")
        return normalized

    def _replace_links(self, connection: sqlite3.Connection, evidence_id: str, claim_ids: Iterable[str]) -> None:
        unique_ids = tuple(dict.fromkeys(str(value) for value in claim_ids))
        connection.execute("DELETE FROM claim_evidence WHERE evidence_id = ?", (evidence_id,))
        connection.executemany(
            "INSERT INTO claim_evidence(claim_id, evidence_id, linked_at) VALUES (?, ?, ?)",
            [(claim_id, evidence_id, _utc_now()) for claim_id in unique_ids],
        )

    def _ensure_schema(self) -> None:
        # Evidence can be the first workspace opened in an upgraded project.
        # Ensure referenced tables exist before the first query or write.
        from core.claims import ClaimManager
        from core.documents import DocumentManager
        from core.ocr import OCRManager
        ClaimManager(self.project)
        DocumentManager(self.project)
        OCRManager(self.project)
        with self._connect() as connection:
            connection.executescript(EVIDENCE_SCHEMA)
