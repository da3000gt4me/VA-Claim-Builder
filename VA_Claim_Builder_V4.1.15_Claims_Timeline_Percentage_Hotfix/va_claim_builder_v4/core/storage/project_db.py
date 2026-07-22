from __future__ import annotations
import json, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, condition_name TEXT NOT NULL, theory TEXT NOT NULL DEFAULT 'unknown',
 status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, category TEXT NOT NULL, original_name TEXT NOT NULL,
 original_path TEXT NOT NULL, working_path TEXT, sha256 TEXT NOT NULL, mime_type TEXT,
 upload_date TEXT NOT NULL, extraction_status TEXT NOT NULL DEFAULT 'queued', ocr_status TEXT NOT NULL DEFAULT 'not_started',
 ocr_confidence REAL, duplicate_of TEXT, classification_reviewed INTEGER NOT NULL DEFAULT 1,
 include_in_final INTEGER NOT NULL DEFAULT 0, signed_status TEXT NOT NULL DEFAULT 'unknown', metadata_json TEXT NOT NULL DEFAULT '{}',
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(duplicate_of) REFERENCES documents(id)
);
CREATE INDEX IF NOT EXISTS idx_documents_project_category ON documents(project_id, category);
CREATE INDEX IF NOT EXISTS idx_documents_sha ON documents(project_id, sha256);
CREATE TABLE IF NOT EXISTS document_claim_links (
 document_id TEXT NOT NULL, claim_id TEXT NOT NULL, link_type TEXT NOT NULL DEFAULT 'relevant',
 PRIMARY KEY(document_id, claim_id),
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS timeline_events (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, claim_id TEXT, event_date_start TEXT, event_date_end TEXT,
 date_precision TEXT NOT NULL, event_type TEXT NOT NULL, description TEXT NOT NULL, source_type TEXT NOT NULL,
 source_document_id TEXT, source_page INTEGER, reporter TEXT, confidence REAL NOT NULL DEFAULT 0.5,
 verification_status TEXT NOT NULL DEFAULT 'unreviewed', reconciliation_status TEXT NOT NULL DEFAULT 'unreviewed',
 created_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE SET NULL,
 FOREIGN KEY(source_document_id) REFERENCES documents(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS evidence_annotations (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, claim_id TEXT, document_id TEXT NOT NULL, page INTEGER,
 claim_element TEXT NOT NULL, polarity TEXT NOT NULL, finding TEXT NOT NULL, quote TEXT,
 confidence REAL NOT NULL, ai_provider TEXT, ai_model TEXT, review_status TEXT NOT NULL DEFAULT 'pending',
 reviewer_note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE SET NULL,
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS draft_revisions (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_document_id TEXT NOT NULL, claim_id TEXT,
 revision_type TEXT NOT NULL, output_path TEXT NOT NULL, change_log_json TEXT NOT NULL DEFAULT '[]',
 source_annotation_ids_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(source_document_id) REFERENCES documents(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS review_decisions (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
 decision TEXT NOT NULL, note TEXT, reviewer TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_pages (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, document_id TEXT NOT NULL, page INTEGER NOT NULL,
 text TEXT NOT NULL DEFAULT '', extraction_method TEXT NOT NULL DEFAULT 'unknown', ocr_confidence REAL,
 needs_review INTEGER NOT NULL DEFAULT 0, warnings_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
 UNIQUE(document_id,page),
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_pages_project ON document_pages(project_id, document_id, page);
CREATE TABLE IF NOT EXISTS claim_chunk_links (
 claim_id TEXT NOT NULL, page_id TEXT NOT NULL, relevance_type TEXT NOT NULL DEFAULT 'linked_document',
 PRIMARY KEY(claim_id,page_id),
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE CASCADE,
 FOREIGN KEY(page_id) REFERENCES document_pages(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS contradictions (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, claim_id TEXT, kind TEXT NOT NULL, severity TEXT NOT NULL,
 summary TEXT NOT NULL, left_source TEXT, right_source TEXT, resolution_prompt TEXT, status TEXT NOT NULL DEFAULT 'open',
 resolution_note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS ocr_jobs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, document_id TEXT NOT NULL, status TEXT NOT NULL,
 pages_total INTEGER NOT NULL DEFAULT 0, pages_complete INTEGER NOT NULL DEFAULT 0, low_confidence_pages INTEGER NOT NULL DEFAULT 0,
 error TEXT, started_at TEXT NOT NULL, completed_at TEXT,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS literature_sources (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, claim_id TEXT, title TEXT NOT NULL, authors TEXT,
 year TEXT, source TEXT, doi TEXT, pmid TEXT, url TEXT, abstract TEXT, study_type TEXT,
 quality_tier TEXT, verification_status TEXT NOT NULL DEFAULT 'unverified', reviewer_note TEXT,
 created_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS generated_outputs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, output_type TEXT NOT NULL, claim_id TEXT,
 path TEXT NOT NULL, approved_only INTEGER NOT NULL DEFAULT 1, manifest_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
 FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE SET NULL
);
"""

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"

class ProjectDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def create_project(self, name: str) -> str:
        project_id = uid("prj")
        ts = now()
        with self.connect() as con:
            con.execute("INSERT INTO projects VALUES(?,?,?,?)", (project_id, name, ts, ts))
        return project_id

    def ensure_default_project(self, name: str = "My VA Claim Project") -> str:
        with self.connect() as con:
            row = con.execute("SELECT id FROM projects ORDER BY created_at LIMIT 1").fetchone()
        return row["id"] if row else self.create_project(name)

    def add_claim(self, project_id: str, condition_name: str, theory: str = "unknown") -> str:
        claim_id = uid("clm")
        with self.connect() as con:
            con.execute("INSERT INTO claims VALUES(?,?,?,?,?,?)", (claim_id, project_id, condition_name.strip(), theory, "active", now()))
        return claim_id

    def list_claims(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM claims WHERE project_id=? ORDER BY condition_name", (project_id,))]

    def update_claim(self, claim_id: str, *, condition_name: str | None = None, theory: str | None = None, status: str | None = None) -> None:
        fields, values = [], []
        if condition_name is not None:
            cleaned = condition_name.strip()
            if not cleaned:
                raise ValueError("Claim name cannot be blank.")
            fields.append("condition_name=?"); values.append(cleaned)
        if theory is not None:
            fields.append("theory=?"); values.append(theory)
        if status is not None:
            fields.append("status=?"); values.append(status)
        if not fields:
            return
        values.append(claim_id)
        with self.connect() as con:
            con.execute(f"UPDATE claims SET {', '.join(fields)} WHERE id=?", values)

    def delete_claim(self, claim_id: str) -> None:
        # Related rows use CASCADE or SET NULL according to their evidentiary role.
        with self.connect() as con:
            con.execute("DELETE FROM claims WHERE id=?", (claim_id,))

    def delete_claims(self, claim_ids: Iterable[str]) -> int:
        ids = [str(x) for x in claim_ids if x]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as con:
            before = con.total_changes
            con.execute(f"DELETE FROM claims WHERE id IN ({placeholders})", ids)
            return con.total_changes - before

    def add_document(self, record: dict[str, Any]) -> str:
        document_id = record.get("id") or uid("doc")
        values = (
            document_id, record["project_id"], record["category"], record["original_name"], record["original_path"],
            record.get("working_path"), record["sha256"], record.get("mime_type"), now(),
            record.get("extraction_status", "queued"), record.get("ocr_status", "not_started"), record.get("ocr_confidence"),
            record.get("duplicate_of"), int(record.get("classification_reviewed", True)), int(record.get("include_in_final", False)),
            record.get("signed_status", "unknown"), json.dumps(record.get("metadata", {}), default=str),
        )
        with self.connect() as con:
            con.execute("""INSERT INTO documents(id,project_id,category,original_name,original_path,working_path,sha256,mime_type,
            upload_date,extraction_status,ocr_status,ocr_confidence,duplicate_of,classification_reviewed,include_in_final,signed_status,metadata_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
        return document_id

    def find_duplicate(self, project_id: str, sha256: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM documents WHERE project_id=? AND sha256=? ORDER BY upload_date LIMIT 1", (project_id, sha256)).fetchone()
        return dict(row) if row else None

    def list_documents(self, project_id: str, category: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM documents WHERE project_id=?", [project_id]
        if category:
            sql += " AND category=?"; args.append(category)
        sql += " ORDER BY category, upload_date DESC"
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, args)]

    def link_document_claims(self, document_id: str, claim_ids: Iterable[str]):
        with self.connect() as con:
            for claim_id in claim_ids:
                con.execute("INSERT OR REPLACE INTO document_claim_links(document_id,claim_id) VALUES(?,?)", (document_id, claim_id))

    def add_timeline_event(self, project_id: str, event: dict[str, Any]) -> str:
        event_id = uid("evt")
        with self.connect() as con:
            con.execute("""INSERT INTO timeline_events(id,project_id,claim_id,event_date_start,event_date_end,date_precision,event_type,
            description,source_type,source_document_id,source_page,reporter,confidence,verification_status,reconciliation_status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                event_id, project_id, event.get("claim_id"), event.get("event_date_start"), event.get("event_date_end"),
                event.get("date_precision", "unknown"), event.get("event_type", "symptom"), event["description"],
                event.get("source_type", "veteran_reported"), event.get("source_document_id"), event.get("source_page"),
                event.get("reporter"), float(event.get("confidence", 0.5)), event.get("verification_status", "unreviewed"),
                event.get("reconciliation_status", "unreviewed"), now()))
        return event_id

    def list_timeline(self, project_id: str, claim_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM timeline_events WHERE project_id=?", [project_id]
        if claim_id:
            sql += " AND claim_id=?"; args.append(claim_id)
        sql += " ORDER BY COALESCE(event_date_start,'9999-12-31'), created_at"
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, args)]

    def timeline_event_exists(self, project_id: str, event: dict[str, Any]) -> bool:
        with self.connect() as con:
            row = con.execute("""SELECT 1 FROM timeline_events WHERE project_id=?
                AND COALESCE(claim_id,'')=COALESCE(?, '')
                AND COALESCE(event_date_start,'')=COALESCE(?, '')
                AND COALESCE(event_date_end,'')=COALESCE(?, '')
                AND event_type=? AND lower(trim(description))=lower(trim(?))
                AND COALESCE(source_document_id,'')=COALESCE(?, '')
                AND COALESCE(source_page,-1)=COALESCE(?, -1) LIMIT 1""",
                (project_id,event.get('claim_id'),event.get('event_date_start'),event.get('event_date_end'),
                 event.get('event_type','other'),event.get('description',''),event.get('source_document_id'),event.get('source_page'))).fetchone()
        return bool(row)

    def add_timeline_events_if_new(self, project_id: str, events: Iterable[dict[str, Any]]) -> int:
        added=0
        for event in events:
            if not self.timeline_event_exists(project_id,event):
                self.add_timeline_event(project_id,event); added+=1
        return added

    def update_timeline_event(self, event_id: str, event: dict[str, Any]) -> None:
        allowed = ["claim_id","event_date_start","event_date_end","date_precision","event_type","description",
                   "source_type","reporter","confidence","verification_status","reconciliation_status"]
        fields=[]; values=[]
        for name in allowed:
            if name in event:
                fields.append(f"{name}=?"); values.append(event[name])
        if not fields: return
        values.append(event_id)
        with self.connect() as con:
            con.execute(f"UPDATE timeline_events SET {', '.join(fields)} WHERE id=?", values)

    def delete_timeline_event(self, event_id: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM timeline_events WHERE id=?", (event_id,))

    def add_annotation(self, project_id: str, item: dict[str, Any]) -> str:
        annotation_id = item.get("id") or uid("ann")
        ts = now()
        with self.connect() as con:
            con.execute("""INSERT INTO evidence_annotations(id,project_id,claim_id,document_id,page,claim_element,polarity,finding,quote,
            confidence,ai_provider,ai_model,review_status,reviewer_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                annotation_id, project_id, item.get("claim_id"), item["document_id"], item.get("page"), item["claim_element"],
                item["polarity"], item["finding"], item.get("quote"), float(item.get("confidence", 0.5)), item.get("ai_provider"),
                item.get("ai_model"), item.get("review_status", "pending"), item.get("reviewer_note"), ts, ts))
        return annotation_id

    def update_annotation(self, annotation_id: str, *, claim_element: str | None = None, polarity: str | None = None, finding: str | None = None, reviewer_note: str | None = None):
        fields=[]; args=[]
        for name,value in (("claim_element",claim_element),("polarity",polarity),("finding",finding),("reviewer_note",reviewer_note)):
            if value is not None:
                fields.append(f"{name}=?"); args.append(value)
        if not fields: return
        fields.append("updated_at=?"); args.append(now()); args.append(annotation_id)
        with self.connect() as con:
            con.execute(f"UPDATE evidence_annotations SET {', '.join(fields)} WHERE id=?", args)

    def review_annotation(self, annotation_id: str, decision: str, note: str = "", reviewer: str = "user"):
        if decision not in {"approved", "rejected", "needs_edit"}:
            raise ValueError("Unsupported review decision")
        with self.connect() as con:
            row = con.execute("SELECT project_id FROM evidence_annotations WHERE id=?", (annotation_id,)).fetchone()
            if not row: raise KeyError(annotation_id)
            con.execute("UPDATE evidence_annotations SET review_status=?,reviewer_note=?,updated_at=? WHERE id=?", (decision, note, now(), annotation_id))
            con.execute("INSERT INTO review_decisions VALUES(?,?,?,?,?,?,?,?)", (uid("rev"), row["project_id"], "evidence_annotation", annotation_id, decision, note, reviewer, now()))

    def list_annotations(self, project_id: str, status: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM evidence_annotations WHERE project_id=?", [project_id]
        if status: sql += " AND review_status=?"; args.append(status)
        sql += " ORDER BY created_at DESC"
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, args)]

    def list_annotations_enriched(self, project_id: str, status: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT a.*,d.original_name AS document_name,d.category,d.signed_status
                 FROM evidence_annotations a JOIN documents d ON d.id=a.document_id
                 WHERE a.project_id=?"""
        args=[project_id]
        if status:
            sql += " AND a.review_status=?"; args.append(status)
        sql += " ORDER BY a.created_at DESC"
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql,args)]

    def upsert_document_page(self, project_id: str, document_id: str, page: int, text: str,
                             extraction_method: str, ocr_confidence: float | None,
                             needs_review: bool, warnings: list[str] | None = None) -> str:
        page_id = f"pg_{document_id}_{page}"
        with self.connect() as con:
            con.execute("""INSERT INTO document_pages(id,project_id,document_id,page,text,extraction_method,ocr_confidence,needs_review,warnings_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(document_id,page) DO UPDATE SET
                text=excluded.text,extraction_method=excluded.extraction_method,ocr_confidence=excluded.ocr_confidence,
                needs_review=excluded.needs_review,warnings_json=excluded.warnings_json""",
                (page_id, project_id, document_id, page, text, extraction_method, ocr_confidence, int(needs_review), json.dumps(warnings or []), now()))
        return page_id

    def link_page_claim(self, page_id: str, claim_id: str, relevance_type: str = "linked_document"):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO claim_chunk_links(claim_id,page_id,relevance_type) VALUES(?,?,?)", (claim_id,page_id,relevance_type))

    def list_chunks(self, project_id: str, claim_id: str | None = None, needs_review: bool | None = None) -> list[dict[str, Any]]:
        sql = """SELECT p.*, d.original_name AS document_name, d.category,
                 GROUP_CONCAT(ccl.claim_id) AS linked_claim_ids
                 FROM document_pages p JOIN documents d ON d.id=p.document_id
                 LEFT JOIN claim_chunk_links ccl ON ccl.page_id=p.id WHERE p.project_id=?"""
        args: list[Any] = [project_id]
        if claim_id:
            sql += " AND EXISTS(SELECT 1 FROM claim_chunk_links x WHERE x.page_id=p.id AND x.claim_id=?)"; args.append(claim_id)
        if needs_review is not None:
            sql += " AND p.needs_review=?"; args.append(int(needs_review))
        sql += " GROUP BY p.id ORDER BY d.original_name,p.page"
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql,args)]

    def get_document_claim_ids(self, document_id: str) -> list[str]:
        with self.connect() as con:
            return [r["claim_id"] for r in con.execute("SELECT claim_id FROM document_claim_links WHERE document_id=?", (document_id,))]

    def update_document_processing(self, document_id: str, extraction_status: str, ocr_status: str, ocr_confidence: float | None):
        with self.connect() as con:
            con.execute("UPDATE documents SET extraction_status=?,ocr_status=?,ocr_confidence=? WHERE id=?",
                        (extraction_status,ocr_status,ocr_confidence,document_id))

    def add_contradictions(self, project_id: str, items: list[dict[str, Any]]) -> list[str]:
        ids=[]
        with self.connect() as con:
            con.execute("DELETE FROM contradictions WHERE project_id=? AND status='open'", (project_id,))
            for item in items:
                cid=uid("con"); ids.append(cid); ts=now()
                con.execute("""INSERT INTO contradictions(id,project_id,claim_id,kind,severity,summary,left_source,right_source,resolution_prompt,status,resolution_note,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,'open',NULL,?,?)""", (cid,project_id,item.get('claim_id'),item['kind'],item['severity'],item['summary'],item.get('left_source'),item.get('right_source'),item.get('resolution_prompt'),ts,ts))
        return ids

    def list_contradictions(self, project_id: str, status: str | None = None) -> list[dict[str, Any]]:
        sql,args="SELECT * FROM contradictions WHERE project_id=?",[project_id]
        if status: sql+=" AND status=?"; args.append(status)
        sql+=" ORDER BY severity DESC,created_at DESC"
        with self.connect() as con: return [dict(r) for r in con.execute(sql,args)]

    def resolve_contradiction(self, contradiction_id: str, note: str):
        with self.connect() as con:
            con.execute("UPDATE contradictions SET status='resolved',resolution_note=?,updated_at=? WHERE id=?", (note,now(),contradiction_id))
    def add_literature_source(self, project_id: str, item: dict[str, Any]) -> str:
        source_id=uid("lit")
        with self.connect() as con:
            con.execute("""INSERT INTO literature_sources(id,project_id,claim_id,title,authors,year,source,doi,pmid,url,abstract,study_type,quality_tier,verification_status,reviewer_note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id,project_id,item.get("claim_id"),item["title"],item.get("authors"),item.get("year"),item.get("source"),item.get("doi"),item.get("pmid"),item.get("url"),item.get("abstract"),item.get("study_type"),item.get("quality_tier"),item.get("verification_status","unverified"),item.get("reviewer_note"),now()))
        return source_id

    def list_literature_sources(self, project_id: str, claim_id: str | None=None) -> list[dict[str, Any]]:
        sql,args="SELECT * FROM literature_sources WHERE project_id=?",[project_id]
        if claim_id: sql+=" AND claim_id=?"; args.append(claim_id)
        sql+=" ORDER BY year DESC,title"
        with self.connect() as con: return [dict(r) for r in con.execute(sql,args)]

