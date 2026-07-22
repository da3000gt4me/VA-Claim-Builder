from __future__ import annotations
import json, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path

def now(): return datetime.now(timezone.utc).isoformat()

class WorkflowRecoveryService:
    def __init__(self, db_path: str | Path): self.db_path = Path(db_path)
    def start(self, project_id: str, stage: str, checkpoint: dict | None = None) -> str:
        run_id = "run_" + uuid.uuid4().hex
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT INTO workflow_runs VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id,project_id,stage,"running",0.0,json.dumps(checkpoint or {}),None,now(),now(),None))
        return run_id
    def checkpoint(self, run_id: str, progress: float, data: dict):
        with sqlite3.connect(self.db_path) as con:
            con.execute("UPDATE workflow_runs SET progress=?,checkpoint_json=?,updated_at=? WHERE id=?", (max(0,min(1,float(progress))),json.dumps(data),now(),run_id))
    def fail(self, run_id: str, error: str):
        with sqlite3.connect(self.db_path) as con:
            con.execute("UPDATE workflow_runs SET status='failed',error=?,updated_at=? WHERE id=?", (error,now(),run_id))
    def complete(self, run_id: str, data: dict | None = None):
        with sqlite3.connect(self.db_path) as con:
            con.execute("UPDATE workflow_runs SET status='complete',progress=1,checkpoint_json=?,updated_at=?,completed_at=? WHERE id=?", (json.dumps(data or {}),now(),now(),run_id))
    def resumable(self, project_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory=sqlite3.Row
            rows=con.execute("SELECT * FROM workflow_runs WHERE project_id=? AND status IN ('running','failed') ORDER BY updated_at DESC",(project_id,)).fetchall()
        out=[]
        for row in rows:
            d=dict(row); d['checkpoint']=json.loads(d.pop('checkpoint_json') or '{}'); out.append(d)
        return out
