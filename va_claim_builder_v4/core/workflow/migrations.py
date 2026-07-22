from __future__ import annotations
import json, shutil, sqlite3
from datetime import datetime, timezone
from pathlib import Path

LATEST_SCHEMA_VERSION = 13

class MigrationManager:
    def __init__(self, db_path: str | Path): self.db_path = Path(db_path)
    def current_version(self) -> int:
        with sqlite3.connect(self.db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT)")
            row = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            return int(row[0] or 0)
    def migrate(self, target: int = LATEST_SCHEMA_VERSION) -> dict:
        backup = self.db_path.with_suffix(self.db_path.suffix + ".pre_migration.bak")
        shutil.copy2(self.db_path, backup)
        start = self.current_version(); applied=[]
        try:
            with sqlite3.connect(self.db_path) as con:
                for version in range(start + 1, target + 1):
                    self._apply(con, version)
                    con.execute("INSERT OR REPLACE INTO schema_migrations VALUES(?,?,?)", (version, datetime.now(timezone.utc).isoformat(), f"Increment {version} compatibility migration"))
                    applied.append(version)
                con.commit()
            return {"from": start, "to": target, "applied": applied, "backup": str(backup), "status": "complete"}
        except Exception:
            shutil.copy2(backup, self.db_path)
            raise
    @staticmethod
    def _apply(con: sqlite3.Connection, version: int):
        if version == 13:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_runs(
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
              progress REAL NOT NULL DEFAULT 0, checkpoint_json TEXT NOT NULL DEFAULT '{}', error TEXT,
              started_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS security_events(
              id TEXT PRIMARY KEY, project_id TEXT, event_type TEXT NOT NULL, severity TEXT NOT NULL,
              detail TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)
