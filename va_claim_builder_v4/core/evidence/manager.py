from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from core.projects import ProjectInfo
from core.projects.manager import EVIDENCE_SCHEMA, ProjectManager


EVIDENCE_TYPES = (
    "service treatment record", "private medical record", "va medical record",
    "medical opinion", "dbq", "lay statement", "service record", "examination",
    "decision", "correspondence", "other",
)
EVIDENCE_STRENGTHS = ("unreviewed", "supportive", "strong", "neutral", "weak", "contradictory")
REVIEW_STATUSES = ("unreviewed", "relevant", "not relevant", "needs clarification", "duplicate")
OCR_FILTERS = ("available", "pending", "failed", "no text", "not associated")


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
    review_status: str
    reviewer_notes: str
    duplicate_of_evidence_id: str | None
    created_at: str
    updated_at: str
    document_name: str | None = None
    document_type: str | None = None
    document_status: str | None = None
    ocr_status: str = "not associated"
    ocr_text_available: bool = False


@dataclass(frozen=True, slots=True)
class ClaimEvidenceLink:
    claim_id: str
    condition_name: str
    relevance_notes: str
    linked_at: str


class EvidenceManager:
    """Persistent evidence review catalog and claim-association service."""

    _FIELDS = (
        "title", "description", "evidence_type", "document_id", "evidence_date",
        "provider_source", "relevance_notes", "strength_status", "review_status",
        "reviewer_notes", "duplicate_of_evidence_id",
    )

    def __init__(self, project: ProjectInfo) -> None:
        self.project = project
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.project.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create(self, title: str, *, description: str = "", evidence_type: str = "other",
               document_id: str | None = None, evidence_date: str = "", provider_source: str = "",
               relevance_notes: str = "", strength_status: str = "unreviewed",
               review_status: str = "unreviewed", reviewer_notes: str = "",
               duplicate_of_evidence_id: str | None = None, claim_ids: Iterable[str] = (),
               claim_relevance_notes: dict[str, str] | None = None) -> Evidence:
        values = self._validated_values(locals())
        evidence_id = str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO evidence(evidence_id, {', '.join(self._FIELDS)}, created_at, updated_at) "
                f"VALUES ({', '.join('?' for _ in range(len(self._FIELDS) + 3))})",
                (evidence_id, *(values[field] for field in self._FIELDS), now, now),
            )
            self._replace_links(connection, evidence_id, claim_ids, claim_relevance_notes or {})
        return self.get(evidence_id)

    def get(self, evidence_id: str) -> Evidence:
        with self._connect() as connection:
            row = connection.execute(self._select_sql() + " WHERE e.evidence_id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return self._row(row)

    def update(self, evidence_id: str, *, claim_ids: Iterable[str] | None = None,
               claim_relevance_notes: dict[str, str] | None = None, **changes: object) -> Evidence:
        unknown = set(changes) - set(self._FIELDS)
        if unknown:
            raise ValueError(f"Unsupported evidence fields: {', '.join(sorted(unknown))}")
        current = self.get(evidence_id)
        values = {field: getattr(current, field) for field in self._FIELDS}
        values.update(changes)
        values = self._validated_values(values, evidence_id=evidence_id)
        with self._connect() as connection:
            assignments = ", ".join(f"{field} = ?" for field in self._FIELDS)
            connection.execute(
                f"UPDATE evidence SET {assignments}, updated_at = ? WHERE evidence_id = ?",
                (*(values[field] for field in self._FIELDS), _utc_now(), evidence_id),
            )
            if claim_ids is not None:
                self._replace_links(connection, evidence_id, claim_ids, claim_relevance_notes or {})
        return self.get(evidence_id)

    def delete(self, evidence_id: str) -> None:
        with self._connect() as connection:
            if connection.execute("DELETE FROM evidence WHERE evidence_id = ?", (evidence_id,)).rowcount == 0:
                raise KeyError(evidence_id)

    def list(self, *, evidence_type: str | None = None, claim_id: str | None = None,
             review_status: str | None = None, unlinked: bool = False,
             ocr_availability: str | None = None, search: str = "") -> list[Evidence]:
        clauses: list[str] = []
        params: list[str] = []
        if evidence_type:
            clauses.append("e.evidence_type = ?"); params.append(evidence_type)
        if review_status:
            clauses.append("e.review_status = ?"); params.append(review_status)
        if claim_id:
            clauses.append("EXISTS (SELECT 1 FROM claim_evidence ce WHERE ce.evidence_id=e.evidence_id AND ce.claim_id=?)")
            params.append(claim_id)
        if unlinked:
            clauses.append("NOT EXISTS (SELECT 1 FROM claim_evidence ce WHERE ce.evidence_id=e.evidence_id)")
        if ocr_availability:
            clauses.append(self._ocr_filter_clause(ocr_availability))
        term = search.strip()
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                self._select_sql() + where + " ORDER BY e.evidence_date DESC, e.created_at ASC, e.evidence_id ASC", params
            ).fetchall()
        records = [self._row(row) for row in rows]
        if term:
            lowered = term.casefold()
            records = [record for record in records if self._matches_search(record, lowered)]
        return records

    def search(self, query: str) -> list[Evidence]:
        return self.list(search=query)

    def link_claim(self, evidence_id: str, claim_id: str, relevance_notes: str = "") -> None:
        self.get(evidence_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO claim_evidence(claim_id, evidence_id, linked_at, relevance_notes) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(claim_id, evidence_id) DO UPDATE SET relevance_notes=excluded.relevance_notes",
                (claim_id, evidence_id, _utc_now(), relevance_notes.strip()),
            )

    def unlink_claim(self, evidence_id: str, claim_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM claim_evidence WHERE evidence_id = ? AND claim_id = ?", (evidence_id, claim_id))

    def evidence_for_claim(self, claim_id: str) -> list[Evidence]:
        return self.list(claim_id=claim_id)

    def claim_links_for_evidence(self, evidence_id: str) -> list[ClaimEvidenceLink]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT c.claim_id, c.condition_name, ce.relevance_notes, ce.linked_at "
                "FROM claims c JOIN claim_evidence ce ON ce.claim_id=c.claim_id "
                "WHERE ce.evidence_id=? ORDER BY c.sort_order, c.condition_name COLLATE NOCASE",
                (evidence_id,),
            ).fetchall()
        return [ClaimEvidenceLink(*map(str, row)) for row in rows]

    def claims_for_evidence(self, evidence_id: str) -> list[object]:
        from core.claims import ClaimInfo
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT c.claim_id, c.condition_name, c.claim_type, c.secondary_to, c.status, c.description, "
                "c.service_event, c.current_diagnosis, c.symptoms, c.notes, c.sort_order, c.created_at, c.updated_at "
                "FROM claims c JOIN claim_evidence ce ON ce.claim_id=c.claim_id WHERE ce.evidence_id=? "
                "ORDER BY c.sort_order, c.condition_name COLLATE NOCASE", (evidence_id,),
            ).fetchall()
        return [ClaimInfo(*row) for row in rows]

    def ocr_text(self, evidence_id: str) -> str | None:
        record = self.get(evidence_id)
        if not record.document_id or not record.ocr_text_available:
            return None
        with self._connect() as connection:
            row = connection.execute("SELECT text_path FROM ocr_results WHERE document_id=?", (record.document_id,)).fetchone()
        if not row:
            return None
        path = self.project.root / str(row[0])
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return text if text.strip() else None

    @staticmethod
    def _select_sql() -> str:
        return """SELECT e.evidence_id, e.title, e.description, e.evidence_type, e.document_id,
                         e.evidence_date, e.provider_source, e.relevance_notes, e.strength_status,
                         e.review_status, e.reviewer_notes, e.duplicate_of_evidence_id,
                         e.created_at, e.updated_at, d.original_name, d.mime_type, d.status,
                         CASE WHEN e.document_id IS NULL THEN 'not associated'
                              WHEN d.status IN ('ocr_failed', 'failed') THEN 'failed'
                              WHEN o.document_id IS NOT NULL AND o.character_count > 0 THEN 'available'
                              WHEN o.document_id IS NOT NULL THEN 'no text'
                              WHEN d.status = 'ocr_complete' THEN 'no text'
                              ELSE 'pending' END,
                         CASE WHEN o.document_id IS NOT NULL AND o.character_count > 0 THEN 1 ELSE 0 END
                  FROM evidence e LEFT JOIN documents d ON d.document_id=e.document_id
                  LEFT JOIN ocr_results o ON o.document_id=e.document_id"""

    @staticmethod
    def _row(row: tuple[object, ...]) -> Evidence:
        values = list(row)
        values[-1] = bool(values[-1])
        return Evidence(*values)

    def _validated_values(self, values: dict[str, object], evidence_id: str | None = None) -> dict[str, str | None]:
        normalized: dict[str, str | None] = {}
        nullable = {"document_id", "duplicate_of_evidence_id"}
        for field in self._FIELDS:
            value = values.get(field)
            normalized[field] = None if field in nullable and not value else str(value or "").strip()
        if not normalized["title"]:
            raise ValueError("Evidence title is required")
        if normalized["evidence_type"] not in EVIDENCE_TYPES:
            raise ValueError(f"Unsupported evidence type: {normalized['evidence_type']}")
        if normalized["strength_status"] not in EVIDENCE_STRENGTHS:
            raise ValueError(f"Unsupported evidence strength/status: {normalized['strength_status']}")
        if normalized["review_status"] not in REVIEW_STATUSES:
            raise ValueError(f"Unsupported review status: {normalized['review_status']}")
        duplicate_id = normalized["duplicate_of_evidence_id"]
        if duplicate_id and normalized["review_status"] != "duplicate":
            raise ValueError("A retained evidence reference requires Duplicate review status")
        if duplicate_id and duplicate_id == evidence_id:
            raise ValueError("Evidence cannot be a duplicate of itself")
        if duplicate_id:
            self.get(duplicate_id)
        return normalized

    def _replace_links(self, connection: sqlite3.Connection, evidence_id: str, claim_ids: Iterable[str], notes: dict[str, str]) -> None:
        unique_ids = tuple(dict.fromkeys(str(value) for value in claim_ids))
        existing = dict(connection.execute("SELECT claim_id, relevance_notes FROM claim_evidence WHERE evidence_id=?", (evidence_id,)))
        connection.execute("DELETE FROM claim_evidence WHERE evidence_id = ?", (evidence_id,))
        connection.executemany(
            "INSERT INTO claim_evidence(claim_id, evidence_id, linked_at, relevance_notes) VALUES (?, ?, ?, ?)",
            [(claim_id, evidence_id, _utc_now(), str(notes.get(claim_id, existing.get(claim_id, ""))).strip()) for claim_id in unique_ids],
        )

    @staticmethod
    def _ocr_filter_clause(value: str) -> str:
        clauses = {
            "available": "o.document_id IS NOT NULL AND o.character_count > 0",
            "no text": "e.document_id IS NOT NULL AND (o.document_id IS NOT NULL OR d.status='ocr_complete') AND COALESCE(o.character_count, 0)=0",
            "failed": "d.status IN ('ocr_failed', 'failed')",
            "pending": "e.document_id IS NOT NULL AND o.document_id IS NULL AND d.status NOT IN ('ocr_complete','ocr_failed','failed')",
            "not associated": "e.document_id IS NULL",
        }
        if value not in clauses:
            raise ValueError(f"Unsupported OCR availability: {value}")
        return clauses[value]

    def _matches_ocr(self, record: Evidence, term: str) -> bool:
        text = self.ocr_text(record.evidence_id) if record.ocr_text_available else None
        return bool(text and term in text.casefold())

    def _matches_search(self, record: Evidence, term: str) -> bool:
        if self._matches_fields(record, term) or self._matches_ocr(record, term):
            return True
        return any(term in link.relevance_notes.casefold() for link in self.claim_links_for_evidence(record.evidence_id))

    @staticmethod
    def _matches_fields(record: Evidence, term: str) -> bool:
        return any(term in str(value or "").casefold() for value in (
            record.title, record.description, record.provider_source, record.relevance_notes,
            record.reviewer_notes, record.document_name,
        ))

    def _ensure_schema(self) -> None:
        from core.claims import ClaimManager
        from core.documents import DocumentManager
        from core.ocr import OCRManager
        ClaimManager(self.project); DocumentManager(self.project); OCRManager(self.project)
        with self._connect() as connection:
            connection.executescript(EVIDENCE_SCHEMA)
            ProjectManager._add_column(connection, "evidence", "review_status", "TEXT NOT NULL DEFAULT 'unreviewed'")
            ProjectManager._add_column(connection, "evidence", "reviewer_notes", "TEXT NOT NULL DEFAULT ''")
            ProjectManager._add_column(connection, "evidence", "duplicate_of_evidence_id", "TEXT REFERENCES evidence(evidence_id) ON DELETE SET NULL")
            ProjectManager._add_column(connection, "claim_evidence", "relevance_notes", "TEXT NOT NULL DEFAULT ''")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_evidence_review_status ON evidence(review_status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_evidence_duplicate ON evidence(duplicate_of_evidence_id)")
