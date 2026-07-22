from __future__ import annotations
import hashlib, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

class AuditLog:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with sqlite3.connect(self.db_path) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS ai_audit (
              id INTEGER PRIMARY KEY, created_at TEXT, task TEXT, provider TEXT, model TEXT,
              request_hash TEXT, response_hash TEXT, request_id TEXT, approved INTEGER DEFAULT 0,
              reviewer_note TEXT)""")

    @staticmethod
    def digest(value: object) -> str:
        blob = json.dumps(value, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()

    def record(self, task: str, provider: str, model: str, request: object, response: object, request_id: str | None):
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT INTO ai_audit(created_at,task,provider,model,request_hash,response_hash,request_id) VALUES(?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), task, provider, model, self.digest(request), self.digest(response), request_id))
