
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.projects import ProjectInfo


def _now():
    return datetime.now(timezone.utc).isoformat()


INTAKE_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_processing (
 document_id TEXT PRIMARY KEY, stage TEXT NOT NULL DEFAULT 'imported', progress INTEGER NOT NULL DEFAULT 0,
 started_at TEXT, completed_at TEXT, failure_reason TEXT NOT NULL DEFAULT '', retry_eligible INTEGER NOT NULL DEFAULT 1,
 source_checksum TEXT NOT NULL, extraction_version TEXT NOT NULL DEFAULT '', method TEXT NOT NULL DEFAULT 'local',
 processing_scope TEXT NOT NULL DEFAULT 'local', result_counts_json TEXT NOT NULL DEFAULT '{}',
 warning_count INTEGER NOT NULL DEFAULT 0, warnings_json TEXT NOT NULL DEFAULT '[]',
 stale INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS intake_runs (
 run_id TEXT PRIMARY KEY, job_id TEXT, document_id TEXT NOT NULL, status TEXT NOT NULL,
 extraction_version TEXT NOT NULL, source_checksum TEXT NOT NULL, started_at TEXT NOT NULL,
 completed_at TEXT, summary_json TEXT NOT NULL DEFAULT '{}', error_message TEXT NOT NULL DEFAULT '',
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS intake_suggestions (
 suggestion_id TEXT PRIMARY KEY, suggestion_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 document_id TEXT NOT NULL, claim_id TEXT, fingerprint TEXT NOT NULL, title TEXT NOT NULL,
 payload_json TEXT NOT NULL, confidence REAL NOT NULL, extraction_method TEXT NOT NULL DEFAULT 'local-rules',
 extraction_version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(document_id,suggestion_type,fingerprint),
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS claim_draft_fields (
 draft_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, field_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 generated_text TEXT NOT NULL, source_ids_json TEXT NOT NULL DEFAULT '[]', fingerprint TEXT NOT NULL,
 extraction_version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(claim_id,field_name,fingerprint), FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS intake_evidence_sources (
 evidence_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
 page_number INTEGER, extraction_version TEXT NOT NULL,
 FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS intake_timeline_sources (
 event_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
 extraction_version TEXT NOT NULL,
 FOREIGN KEY(event_id) REFERENCES medical_timeline_events(event_id) ON DELETE CASCADE,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_classifications (
 document_id TEXT PRIMARY KEY, document_type TEXT NOT NULL, revision TEXT NOT NULL DEFAULT '',
 confidence REAL NOT NULL DEFAULT 0, extraction_method TEXT NOT NULL DEFAULT 'local-rules',
 user_override TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS imported_statements (
 statement_id TEXT PRIMARY KEY, document_id TEXT NOT NULL UNIQUE, statement_type TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', claim_id TEXT, fields_json TEXT NOT NULL,
 source_page INTEGER NOT NULL DEFAULT 1, extraction_method TEXT NOT NULL DEFAULT 'local-rules',
 confidence REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_suggestion_review ON intake_suggestions(status,suggestion_type,created_at);
CREATE INDEX IF NOT EXISTS idx_intake_run_document ON intake_runs(document_id,started_at DESC);
CREATE INDEX IF NOT EXISTS idx_imported_statement_review ON imported_statements(statement_type,status,created_at);
"""


@dataclass(frozen=True, slots=True)
class ProcessingState:
    document_id: str; stage: str; progress: int; started_at: str | None; completed_at: str | None
    failure_reason: str; retry_eligible: bool; source_checksum: str; extraction_version: str
    method: str; processing_scope: str; result_counts: dict[str, int]; warning_count: int
    warnings: list[str]; stale: bool; updated_at: str


@dataclass(frozen=True, slots=True)
class Suggestion:
    suggestion_id: str; suggestion_type: str; status: str; document_id: str; claim_id: str | None
    fingerprint: str; title: str; payload: dict[str, Any]; confidence: float
    extraction_method: str; extraction_version: str; created_at: str; updated_at: str


class IntakeManager:
    def __init__(self, project: ProjectInfo):
        self.project = project
        with self._connect() as connection:
            connection.executescript(INTAKE_SCHEMA)

    def _connect(self):
        connection = sqlite3.connect(self.project.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def ensure_document(self, document_id, checksum):
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO document_processing(document_id,source_checksum,updated_at) VALUES(?,?,?)",
                (document_id, checksum, _now()),
            )
        return self.state(document_id)

    def update_state(self, document_id, *, stage, progress, failure_reason="", completed=False,
                     extraction_version="", method="local-rules", result_counts=None, warnings=None):
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE document_processing SET stage=?,progress=?,started_at=COALESCE(started_at,?),
                completed_at=?,failure_reason=?,retry_eligible=?,extraction_version=?,method=?,
                processing_scope=?,result_counts_json=?,warning_count=?,warnings_json=?,stale=0,updated_at=?
                WHERE document_id=?""",
                (stage, max(0, min(100, int(progress))), now, now if completed else None,
                 failure_reason[:500], int(stage not in {"completed", "cancelled"}), extraction_version,
                 method, "local", json.dumps(result_counts or {}), len(warnings or []),
                 json.dumps(warnings or []), now, document_id),
            )
            connection.execute("UPDATE documents SET status=? WHERE document_id=?", (stage, document_id))
        return self.state(document_id)

    def state(self, document_id):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM document_processing WHERE document_id=?", (document_id,)).fetchone()
        if row is None:
            raise KeyError(document_id)
        return ProcessingState(
            row["document_id"], row["stage"], row["progress"], row["started_at"], row["completed_at"],
            row["failure_reason"], bool(row["retry_eligible"]), row["source_checksum"], row["extraction_version"],
            row["method"], row["processing_scope"], json.loads(row["result_counts_json"]),
            row["warning_count"], json.loads(row["warnings_json"]), bool(row["stale"]), row["updated_at"],
        )

    def list_states(self):
        with self._connect() as connection:
            ids = [row[0] for row in connection.execute("SELECT document_id FROM document_processing ORDER BY updated_at DESC")]
        return [self.state(document_id) for document_id in ids]

    def create_run(self, document_id, checksum, version, job_id=None):
        run_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intake_runs(run_id,job_id,document_id,status,extraction_version,source_checksum,started_at) VALUES(?,?,?,'running',?,?,?)",
                (run_id, job_id, document_id, version, checksum, _now()),
            )
        return run_id

    def finish_run(self, run_id, status, summary=None, error=""):
        with self._connect() as connection:
            connection.execute(
                "UPDATE intake_runs SET status=?,completed_at=?,summary_json=?,error_message=? WHERE run_id=?",
                (status, _now(), json.dumps(summary or {}), error[:500], run_id),
            )

    def add_suggestion(self, suggestion_type, document_id, title, payload, confidence, version, claim_id=None):
        fingerprint = self.fingerprint(suggestion_type, document_id, title, payload)
        suggestion_id = str(uuid.uuid4()); now = _now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT suggestion_id,status FROM intake_suggestions WHERE document_id=? AND suggestion_type=? AND fingerprint=?",
                (document_id, suggestion_type, fingerprint),
            ).fetchone()
            if existing:
                # Preserve every user decision across reanalysis.
                if existing["status"] == "pending":
                    connection.execute(
                        "UPDATE intake_suggestions SET payload_json=?,confidence=?,extraction_version=?,updated_at=? WHERE suggestion_id=?",
                        (json.dumps(payload), confidence, version, now, existing["suggestion_id"]),
                    )
                return self.get_suggestion(existing["suggestion_id"])
            connection.execute(
                """INSERT INTO intake_suggestions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (suggestion_id, suggestion_type, "pending", document_id, claim_id, fingerprint, title,
                 json.dumps(payload), float(confidence), "local-rules", version, now, now),
            )
        return self.get_suggestion(suggestion_id)

    def get_suggestion(self, suggestion_id):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM intake_suggestions WHERE suggestion_id=?", (suggestion_id,)).fetchone()
        if row is None:
            raise KeyError(suggestion_id)
        return Suggestion(
            row["suggestion_id"], row["suggestion_type"], row["status"], row["document_id"], row["claim_id"],
            row["fingerprint"], row["title"], json.loads(row["payload_json"]), row["confidence"],
            row["extraction_method"], row["extraction_version"], row["created_at"], row["updated_at"],
        )

    def list_suggestions(self, *, status="", suggestion_type=""):
        clauses=[]; args=[]
        if status: clauses.append("status=?"); args.append(status)
        if suggestion_type: clauses.append("suggestion_type=?"); args.append(suggestion_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            ids = [row[0] for row in connection.execute(
                "SELECT suggestion_id FROM intake_suggestions" + where + " ORDER BY created_at", args
            )]
        return [self.get_suggestion(item) for item in ids]

    def decide(self, suggestion_id, status):
        if status not in {"accepted", "rejected", "deferred", "not_claim_related", "pending"}:
            raise ValueError(status)
        suggestion = self.get_suggestion(suggestion_id)
        claim_id = suggestion.claim_id
        if status == "accepted" and suggestion.suggestion_type == "claim" and not claim_id:
            from core.claims import ClaimManager
            proposed = str(suggestion.payload.get("proposed_condition_name") or suggestion.title).strip()
            existing = next((item for item in ClaimManager(self.project).list_claims() if item.condition_name.casefold() == proposed.casefold()), None)
            proposed_values = {
                "secondary_to": str(suggestion.payload.get("secondary_to") or ""),
                "description": str(suggestion.payload.get("description") or ""),
                "service_event": str(suggestion.payload.get("service_event") or ""),
            }
            if existing:
                # Never overwrite confirmed content: only fill fields that are still blank.
                changes = {
                    key: value for key, value in proposed_values.items()
                    if value and not getattr(existing, key)
                }
                claim = ClaimManager(self.project).update(existing.claim_id, **changes) if changes else existing
            else:
                claim = ClaimManager(self.project).create(
                    proposed, claim_type=str(suggestion.payload.get("possible_claim_type") or "other"),
                    **proposed_values,
                )
            claim_id = claim.claim_id
        with self._connect() as connection:
            if not connection.execute(
                "UPDATE intake_suggestions SET status=?,claim_id=?,updated_at=? WHERE suggestion_id=?",
                (status, claim_id, _now(), suggestion_id),
            ).rowcount:
                raise KeyError(suggestion_id)
            if status == "accepted" and suggestion.suggestion_type == "evidence" and suggestion.payload.get("evidence_id"):
                connection.execute(
                    "UPDATE evidence SET review_status='relevant',reviewer_notes=TRIM(reviewer_notes || ' Accepted in Automation Review.') WHERE evidence_id=?",
                    (suggestion.payload["evidence_id"],),
                )
            if status == "accepted" and suggestion.suggestion_type == "timeline" and suggestion.payload.get("event_id"):
                connection.execute(
                    "UPDATE medical_timeline_events SET notes=TRIM(notes || ' Accepted in Automation Review.') WHERE event_id=?",
                    (suggestion.payload["event_id"],),
                )
            if status == "accepted" and suggestion.suggestion_type == "claim_field" and claim_id:
                allowed = {"description", "service_event", "current_diagnosis", "symptoms", "secondary_to"}
                field_name = str(suggestion.payload.get("field_name") or "")
                proposed = str(suggestion.payload.get("proposed_value") or "").strip()
                if field_name in allowed and proposed:
                    # Confirmed user content wins; accepted extraction fills blanks only.
                    connection.execute(
                        f"UPDATE claims SET {field_name}=?,updated_at=? "
                        f"WHERE claim_id=? AND TRIM({field_name})=''",
                        (proposed, _now(), claim_id),
                    )
        return self.get_suggestion(suggestion_id)

    def add_claim_draft(self, claim_id, field_name, text, source_ids, version):
        fingerprint = self.fingerprint(claim_id, field_name, text)
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO claim_draft_fields
                (draft_id,claim_id,field_name,status,generated_text,source_ids_json,fingerprint,extraction_version,created_at,updated_at)
                VALUES(?,?,?,'pending',?,?,?,?,?,?)""",
                (str(uuid.uuid4()), claim_id, field_name, text, json.dumps(source_ids), fingerprint, version, _now(), _now()),
            )

    def claim_drafts(self, claim_id=None, status="pending"):
        query = "SELECT * FROM claim_draft_fields WHERE status=?"
        args=[status]
        if claim_id:
            query += " AND claim_id=?"; args.append(claim_id)
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query + " ORDER BY created_at", args)]

    def recover_interrupted(self):
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE document_processing SET stage='needs reanalysis',failure_reason='Processing was interrupted',retry_eligible=1,updated_at=? "
                "WHERE stage NOT IN ('completed','partially completed','failed','cancelled','review required','imported')",
                (_now(),),
            )
            connection.execute(
                "UPDATE intake_runs SET status='interrupted',completed_at=?,error_message='Application closed before completion' WHERE status='running'",
                (_now(),),
            )
        return cursor.rowcount

    def set_classification(self, document_id, document_type, confidence, revision="", method="local-rules"):
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT user_override FROM document_classifications WHERE document_id=?", (document_id,)
            ).fetchone()
            if existing and existing["user_override"]:
                document_type = existing["user_override"]
            connection.execute(
                """INSERT INTO document_classifications VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(document_id) DO UPDATE SET document_type=excluded.document_type,
                revision=excluded.revision,confidence=excluded.confidence,
                extraction_method=excluded.extraction_method,updated_at=excluded.updated_at""",
                (document_id, document_type, revision, float(confidence), method, existing["user_override"] if existing else "", _now()),
            )

    def override_classification(self, document_id, document_type):
        with self._connect() as connection:
            if not connection.execute(
                "UPDATE document_classifications SET document_type=?,user_override=?,updated_at=? WHERE document_id=?",
                (document_type, document_type, _now(), document_id),
            ).rowcount:
                raise KeyError(document_id)

    def classification(self, document_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM document_classifications WHERE document_id=?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def import_statement(self, document_id, statement_type, fields, confidence, claim_id=None):
        now = _now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT statement_id,status FROM imported_statements WHERE document_id=?", (document_id,)
            ).fetchone()
            if row:
                if row["status"] == "pending":
                    connection.execute(
                        "UPDATE imported_statements SET statement_type=?,fields_json=?,confidence=?,claim_id=?,updated_at=? "
                        "WHERE statement_id=?",
                        (statement_type, json.dumps(fields), float(confidence), claim_id, now, row["statement_id"]),
                    )
                return row["statement_id"]
            statement_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO imported_statements VALUES(?,?,?,'pending',?,?,1,'local-rules',?,?,?)",
                (statement_id, document_id, statement_type, claim_id, json.dumps(fields), float(confidence), now, now),
            )
        return statement_id

    def list_imported_statements(self, statement_type="", status=""):
        clauses=[];args=[]
        if statement_type: clauses.append("statement_type=?");args.append(statement_type)
        if status: clauses.append("status=?");args.append(status)
        where=" WHERE "+" AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows=connection.execute(
                "SELECT * FROM imported_statements"+where+" ORDER BY created_at",args
            ).fetchall()
        output=[]
        for row in rows:
            item=dict(row);item["fields"]=json.loads(item.pop("fields_json"));output.append(item)
        return output

    def decide_statement(self, statement_id, status):
        if status not in {"pending","accepted","rejected"}: raise ValueError(status)
        with self._connect() as connection:
            if not connection.execute(
                "UPDATE imported_statements SET status=?,updated_at=? WHERE statement_id=?",
                (status,_now(),statement_id),
            ).rowcount: raise KeyError(statement_id)

    @staticmethod
    def fingerprint(*values):
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
