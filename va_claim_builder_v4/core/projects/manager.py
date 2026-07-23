
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import AppPaths, resolve_app_paths

PROJECT_FOLDERS = ("uploads", "ocr", "ai", "evidence", "timeline", "reports", "cache", "logs", "temp")
SCHEMA_VERSION = 10


EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    evidence_type TEXT NOT NULL DEFAULT 'other',
    document_id TEXT,
    evidence_date TEXT NOT NULL DEFAULT '',
    provider_source TEXT NOT NULL DEFAULT '',
    relevance_notes TEXT NOT NULL DEFAULT '',
    strength_status TEXT NOT NULL DEFAULT 'unreviewed',
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewer_notes TEXT NOT NULL DEFAULT '',
    duplicate_of_evidence_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
    FOREIGN KEY(duplicate_of_evidence_id) REFERENCES evidence(evidence_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    relevance_notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(claim_id, evidence_id),
    FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_evidence_strength ON evidence(strength_status);
CREATE INDEX IF NOT EXISTS idx_evidence_document ON evidence(document_id);
CREATE INDEX IF NOT EXISTS idx_evidence_date ON evidence(evidence_date);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_evidence ON claim_evidence(evidence_id);
"""

EVIDENCE_ANALYSIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_analyses (
    analysis_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    job_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    analysis_version TEXT NOT NULL,
    result_json TEXT,
    error_message TEXT NOT NULL DEFAULT '',
    redaction_applied INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_evidence_analyses_evidence ON evidence_analyses(evidence_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_analyses_status ON evidence_analyses(status);
CREATE INDEX IF NOT EXISTS idx_evidence_analyses_job ON evidence_analyses(job_id);
"""

TIMELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS medical_timeline_events (
 event_id TEXT PRIMARY KEY, event_date TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL DEFAULT '',
 date_precision TEXT NOT NULL DEFAULT 'unknown', event_type TEXT NOT NULL DEFAULT 'other',
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', provider_facility TEXT NOT NULL DEFAULT '',
 body_system_condition TEXT NOT NULL DEFAULT '', document_id TEXT, evidence_id TEXT,
 treatment TEXT NOT NULL DEFAULT '', diagnosis TEXT NOT NULL DEFAULT '', symptoms_json TEXT NOT NULL DEFAULT '[]',
 medications_json TEXT NOT NULL DEFAULT '[]', testing_imaging TEXT NOT NULL DEFAULT '',
 functional_impact TEXT NOT NULL DEFAULT '', service_period_relevance TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
 FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS timeline_event_claims (
 event_id TEXT NOT NULL, claim_id TEXT NOT NULL, linked_at TEXT NOT NULL,
 PRIMARY KEY(event_id,claim_id),
 FOREIGN KEY(event_id) REFERENCES medical_timeline_events(event_id) ON DELETE CASCADE,
 FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS timeline_extractions (
 extraction_id TEXT PRIMARY KEY, job_id TEXT, status TEXT NOT NULL DEFAULT 'pending', provider TEXT NOT NULL DEFAULT '',
 model TEXT NOT NULL DEFAULT '', redaction_applied INTEGER NOT NULL DEFAULT 0, error_message TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS timeline_candidates (
 candidate_id TEXT PRIMARY KEY, extraction_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 event_json TEXT NOT NULL, document_id TEXT, evidence_id TEXT, merged_into_candidate_id TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(extraction_id) REFERENCES timeline_extractions(extraction_id) ON DELETE CASCADE,
 FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
 FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_medical_timeline_date ON medical_timeline_events(event_date,event_id);
CREATE INDEX IF NOT EXISTS idx_medical_timeline_type ON medical_timeline_events(event_type);
CREATE INDEX IF NOT EXISTS idx_timeline_event_claim ON timeline_event_claims(claim_id,event_id);
CREATE INDEX IF NOT EXISTS idx_timeline_candidate_status ON timeline_candidates(status,created_at);
"""

NEXUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS nexus_letters (
 letter_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, title TEXT NOT NULL, letter_type TEXT NOT NULL DEFAULT 'physician_review',
 status TEXT NOT NULL DEFAULT 'draft', primary_theory TEXT NOT NULL DEFAULT 'direct', theories_json TEXT NOT NULL DEFAULT '[]',
 author_name TEXT NOT NULL DEFAULT '', author_credentials TEXT NOT NULL DEFAULT '', specialty TEXT NOT NULL DEFAULT '',
 current_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS nexus_letter_versions (
 version_id TEXT PRIMARY KEY, letter_id TEXT NOT NULL, version_number INTEGER NOT NULL, content_json TEXT NOT NULL,
 ai_metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, UNIQUE(letter_id,version_number),
 FOREIGN KEY(letter_id) REFERENCES nexus_letters(letter_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS nexus_letter_evidence (letter_id TEXT NOT NULL,evidence_id TEXT NOT NULL,linked_at TEXT NOT NULL,PRIMARY KEY(letter_id,evidence_id),FOREIGN KEY(letter_id) REFERENCES nexus_letters(letter_id) ON DELETE CASCADE,FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS nexus_letter_timeline (letter_id TEXT NOT NULL,event_id TEXT NOT NULL,linked_at TEXT NOT NULL,PRIMARY KEY(letter_id,event_id),FOREIGN KEY(letter_id) REFERENCES nexus_letters(letter_id) ON DELETE CASCADE,FOREIGN KEY(event_id) REFERENCES medical_timeline_events(event_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS nexus_letter_documents (letter_id TEXT NOT NULL,document_id TEXT NOT NULL,linked_at TEXT NOT NULL,PRIMARY KEY(letter_id,document_id),FOREIGN KEY(letter_id) REFERENCES nexus_letters(letter_id) ON DELETE CASCADE,FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS nexus_literature (reference_id TEXT PRIMARY KEY,letter_id TEXT NOT NULL,title TEXT NOT NULL,author TEXT NOT NULL DEFAULT '',publication TEXT NOT NULL DEFAULT '',year TEXT NOT NULL DEFAULT '',doi_url TEXT NOT NULL DEFAULT '',relevance_note TEXT NOT NULL DEFAULT '',verified INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,FOREIGN KEY(letter_id) REFERENCES nexus_letters(letter_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS nexus_generations (generation_id TEXT PRIMARY KEY,letter_id TEXT NOT NULL,job_id TEXT,status TEXT NOT NULL DEFAULT 'pending',provider TEXT NOT NULL DEFAULT '',model TEXT NOT NULL DEFAULT '',redaction_applied INTEGER NOT NULL DEFAULT 0,error_message TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,completed_at TEXT,FOREIGN KEY(letter_id) REFERENCES nexus_letters(letter_id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_nexus_claim ON nexus_letters(claim_id,status);
CREATE INDEX IF NOT EXISTS idx_nexus_versions ON nexus_letter_versions(letter_id,version_number DESC);
CREATE INDEX IF NOT EXISTS idx_nexus_generation_job ON nexus_generations(job_id,status);
"""

DBQ_SCHEMA = """
CREATE TABLE IF NOT EXISTS dbq_records (dbq_id TEXT PRIMARY KEY,claim_id TEXT NOT NULL,template_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',title TEXT NOT NULL,condition TEXT NOT NULL DEFAULT '',exam_date TEXT NOT NULL DEFAULT '',examiner_name TEXT NOT NULL DEFAULT '',examiner_credentials TEXT NOT NULL DEFAULT '',specialty TEXT NOT NULL DEFAULT '',revision_number INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE RESTRICT);
CREATE TABLE IF NOT EXISTS dbq_revisions (revision_id TEXT PRIMARY KEY,dbq_id TEXT NOT NULL,revision_number INTEGER NOT NULL,fields_json TEXT NOT NULL,suggestions_json TEXT NOT NULL DEFAULT '[]',ai_metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,UNIQUE(dbq_id,revision_number),FOREIGN KEY(dbq_id) REFERENCES dbq_records(dbq_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS dbq_evidence (dbq_id TEXT NOT NULL,evidence_id TEXT NOT NULL,linked_at TEXT NOT NULL,PRIMARY KEY(dbq_id,evidence_id),FOREIGN KEY(dbq_id) REFERENCES dbq_records(dbq_id) ON DELETE CASCADE,FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS dbq_timeline (dbq_id TEXT NOT NULL,event_id TEXT NOT NULL,linked_at TEXT NOT NULL,PRIMARY KEY(dbq_id,event_id),FOREIGN KEY(dbq_id) REFERENCES dbq_records(dbq_id) ON DELETE CASCADE,FOREIGN KEY(event_id) REFERENCES medical_timeline_events(event_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS dbq_documents (dbq_id TEXT NOT NULL,document_id TEXT NOT NULL,linked_at TEXT NOT NULL,PRIMARY KEY(dbq_id,document_id),FOREIGN KEY(dbq_id) REFERENCES dbq_records(dbq_id) ON DELETE CASCADE,FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS dbq_generations (generation_id TEXT PRIMARY KEY,dbq_id TEXT NOT NULL,job_id TEXT,status TEXT NOT NULL DEFAULT 'pending',provider TEXT NOT NULL DEFAULT '',model TEXT NOT NULL DEFAULT '',redaction_applied INTEGER NOT NULL DEFAULT 0,error_message TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,completed_at TEXT,FOREIGN KEY(dbq_id) REFERENCES dbq_records(dbq_id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_dbq_claim ON dbq_records(claim_id,status);
CREATE INDEX IF NOT EXISTS idx_dbq_template ON dbq_records(template_id);
CREATE INDEX IF NOT EXISTS idx_dbq_revisions ON dbq_revisions(dbq_id,revision_number DESC);
CREATE INDEX IF NOT EXISTS idx_dbq_generation_job ON dbq_generations(job_id,status);
"""

RATING_STRATEGY_SCHEMA = """
CREATE TABLE IF NOT EXISTS rating_strategies (strategy_id TEXT PRIMARY KEY,claim_id TEXT NOT NULL,job_id TEXT,status TEXT NOT NULL DEFAULT 'pending',analysis_timestamp TEXT NOT NULL,analysis_version TEXT NOT NULL,confidence TEXT NOT NULL DEFAULT 'low',diagnostic_codes_json TEXT NOT NULL DEFAULT '[]',estimated_rating_range TEXT NOT NULL DEFAULT '',supporting_evidence_json TEXT NOT NULL DEFAULT '[]',contradictory_evidence_json TEXT NOT NULL DEFAULT '[]',missing_evidence_json TEXT NOT NULL DEFAULT '[]',recommended_actions_json TEXT NOT NULL DEFAULT '[]',secondary_opportunities_json TEXT NOT NULL DEFAULT '[]',aggravation_opportunities_json TEXT NOT NULL DEFAULT '[]',presumptive_opportunities_json TEXT NOT NULL DEFAULT '[]',strengths_json TEXT NOT NULL DEFAULT '[]',weaknesses_json TEXT NOT NULL DEFAULT '[]',generated_reasoning TEXT NOT NULL DEFAULT '',ai_metadata_json TEXT NOT NULL DEFAULT '{}',error_message TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_rating_strategy_claim ON rating_strategies(claim_id,analysis_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_rating_strategy_status ON rating_strategies(status);
CREATE INDEX IF NOT EXISTS idx_rating_strategy_job ON rating_strategies(job_id,status);
"""

OPTIMIZER_SCHEMA = """
CREATE TABLE IF NOT EXISTS optimizer_assessments (assessment_id TEXT PRIMARY KEY,claim_id TEXT NOT NULL,job_id TEXT,status TEXT NOT NULL DEFAULT 'pending',assessment_timestamp TEXT NOT NULL,assessment_version TEXT NOT NULL,overall_score INTEGER NOT NULL DEFAULT 0,service_connection_score INTEGER NOT NULL DEFAULT 0,severity_rating_score INTEGER NOT NULL DEFAULT 0,evidence_quality_score INTEGER NOT NULL DEFAULT 0,evidence_consistency_score INTEGER NOT NULL DEFAULT 0,confidence TEXT NOT NULL DEFAULT 'low',score_explanation_json TEXT NOT NULL DEFAULT '{}',ai_metadata_json TEXT NOT NULL DEFAULT '{}',error_message TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS optimizer_gaps (gap_id TEXT PRIMARY KEY,assessment_id TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,severity TEXT NOT NULL,priority INTEGER NOT NULL,confidence TEXT NOT NULL,evidence_basis_json TEXT NOT NULL DEFAULT '[]',recommended_resolution TEXT NOT NULL DEFAULT '',responsible_party TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'unresolved',follow_up_date TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',origin TEXT NOT NULL DEFAULT 'rule',user_confirmation TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(assessment_id) REFERENCES optimizer_assessments(assessment_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS optimizer_actions (action_id TEXT PRIMARY KEY,assessment_id TEXT NOT NULL,gap_id TEXT,description TEXT NOT NULL,priority INTEGER NOT NULL,expected_value TEXT NOT NULL,effort_level TEXT NOT NULL,dependency TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'pending',completion_notes TEXT NOT NULL DEFAULT '',origin TEXT NOT NULL DEFAULT 'rule',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(assessment_id) REFERENCES optimizer_assessments(assessment_id) ON DELETE CASCADE,FOREIGN KEY(gap_id) REFERENCES optimizer_gaps(gap_id) ON DELETE SET NULL);
CREATE INDEX IF NOT EXISTS idx_optimizer_claim ON optimizer_assessments(claim_id,assessment_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_optimizer_gap_filter ON optimizer_gaps(assessment_id,status,category,priority);
CREATE INDEX IF NOT EXISTS idx_optimizer_action_rank ON optimizer_actions(assessment_id,status,priority);
"""

SUBMISSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS submission_packages (package_id TEXT PRIMARY KEY,name TEXT NOT NULL,package_type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',package_version INTEGER NOT NULL DEFAULT 1,user_notes TEXT NOT NULL DEFAULT '',generated_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submission_claims (package_id TEXT NOT NULL,claim_id TEXT NOT NULL,sort_order INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(package_id,claim_id),FOREIGN KEY(package_id) REFERENCES submission_packages(package_id) ON DELETE CASCADE,FOREIGN KEY(claim_id) REFERENCES claims(claim_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS submission_sources (package_id TEXT NOT NULL,source_type TEXT NOT NULL,source_id TEXT NOT NULL,display_name TEXT NOT NULL DEFAULT '',exhibit_id TEXT NOT NULL DEFAULT '',sort_order INTEGER NOT NULL DEFAULT 0,section_key TEXT NOT NULL DEFAULT 'appendices',user_confirmed INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(package_id,source_type,source_id),FOREIGN KEY(package_id) REFERENCES submission_packages(package_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS submission_sections (package_id TEXT NOT NULL,section_key TEXT NOT NULL,title TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,sort_order INTEGER NOT NULL,PRIMARY KEY(package_id,section_key),FOREIGN KEY(package_id) REFERENCES submission_packages(package_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS submission_versions (version_id TEXT PRIMARY KEY,package_id TEXT NOT NULL,version_number INTEGER NOT NULL,snapshot_json TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(package_id,version_number),FOREIGN KEY(package_id) REFERENCES submission_packages(package_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS submission_exports (export_id TEXT PRIMARY KEY,package_id TEXT NOT NULL,version_number INTEGER NOT NULL,status TEXT NOT NULL,output_path TEXT NOT NULL DEFAULT '',formats_json TEXT NOT NULL DEFAULT '[]',validation_json TEXT NOT NULL DEFAULT '[]',manifest_json TEXT NOT NULL DEFAULT '{}',generation_metadata_json TEXT NOT NULL DEFAULT '{}',job_id TEXT,error_message TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,completed_at TEXT,FOREIGN KEY(package_id) REFERENCES submission_packages(package_id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_submission_type_status ON submission_packages(package_type,status);
CREATE INDEX IF NOT EXISTS idx_submission_sources_order ON submission_sources(package_id,sort_order);
CREATE INDEX IF NOT EXISTS idx_submission_exports ON submission_exports(package_id,version_number DESC);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip()
    value = re.sub(r"[ ._-]+", "-", value).strip("-")
    return value or "project"


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    project_id: str
    name: str
    root: Path
    manifest_path: Path
    database_path: Path
    created_at: str
    updated_at: str


class ProjectManager:
    def __init__(self, paths: AppPaths | None = None, *, home: str | Path | None = None) -> None:
        if paths is not None and home is not None:
            raise ValueError("Provide paths or home, not both")
        self.paths = paths or (AppPaths(home=Path(home)).ensure() if home is not None else resolve_app_paths())

    def create_project(self, name: str) -> ProjectInfo:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Project name is required.")
        project_id = str(uuid.uuid4())
        root = self.paths.projects / f"{_slugify(clean_name)}-{project_id[:8]}"
        root.mkdir(parents=True, exist_ok=False)
        for folder in PROJECT_FOLDERS:
            (root / folder).mkdir()
        now = _utc_now()
        manifest = {
            "project_id": project_id,
            "name": clean_name,
            "schema_version": SCHEMA_VERSION,
            "created_at": now,
            "updated_at": now,
            "folders": list(PROJECT_FOLDERS),
        }
        self._write_json(root / "manifest.json", manifest)
        self._initialize_database(root / "project.db", project_id, clean_name, now)
        info = self.open_project(root)
        self._remember(info)
        return info

    def open_project(self, root: str | Path) -> ProjectInfo:
        root = Path(root).expanduser().resolve()
        manifest_path = root / "manifest.json"
        database_path = root / "project.db"
        if not manifest_path.is_file():
            raise ValueError(f"Missing project manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {"project_id", "name", "created_at", "updated_at"}
        missing = sorted(required.difference(manifest))
        if missing:
            raise ValueError(f"Invalid project manifest; missing: {', '.join(missing)}")
        for folder in PROJECT_FOLDERS:
            (root / folder).mkdir(exist_ok=True)
        if not database_path.exists():
            self._initialize_database(database_path, manifest["project_id"], manifest["name"], manifest["created_at"])
        migration_backup: Path | None = None
        try:
            current_version = self._schema_version(database_path)
            if current_version > SCHEMA_VERSION:
                raise ValueError(
                    f"Project schema {current_version} is newer than supported schema {SCHEMA_VERSION}."
                )
            if current_version < SCHEMA_VERSION:
                migration_backup = self._backup_before_migration(database_path, manifest["project_id"])
            self._migrate_database(database_path)
            with sqlite3.connect(database_path) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("Database integrity check failed after migration")
        except Exception:
            if migration_backup is not None and migration_backup.is_file():
                shutil.copy2(migration_backup, database_path)
            raise
        if int(manifest.get("schema_version", 1)) < SCHEMA_VERSION:
            manifest["schema_version"] = SCHEMA_VERSION
            manifest["updated_at"] = _utc_now()
            self._write_json(manifest_path, manifest)
        info = ProjectInfo(
            project_id=str(manifest["project_id"]),
            name=str(manifest["name"]),
            root=root,
            manifest_path=manifest_path,
            database_path=database_path,
            created_at=str(manifest["created_at"]),
            updated_at=str(manifest["updated_at"]),
        )
        self._remember(info)
        return info

    def list_recent_projects(self) -> list[dict[str, Any]]:
        settings = self._read_settings()
        return [entry for entry in settings.get("recent_projects", []) if Path(entry.get("path", "")).exists()]

    def last_opened_project(self) -> ProjectInfo | None:
        path = self._read_settings().get("last_opened_project")
        if not path or not Path(path).exists():
            return None
        try:
            return self.open_project(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def import_legacy_database(self, project: ProjectInfo, legacy_db: str | Path) -> Path:
        source = Path(legacy_db).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        backup = self.paths.backups / f"legacy-{project.project_id}-{datetime.now():%Y%m%d-%H%M%S}.db"
        shutil.copy2(source, backup)
        return backup

    def _remember(self, project: ProjectInfo) -> None:
        settings = self._read_settings()
        recent = [entry for entry in settings.get("recent_projects", []) if entry.get("path") != str(project.root)]
        recent.insert(0, {"project_id": project.project_id, "name": project.name, "path": str(project.root), "opened_at": _utc_now()})
        settings["recent_projects"] = recent[:10]
        settings["last_opened_project"] = str(project.root)
        self._write_json(self.paths.settings_file, settings)

    def _read_settings(self) -> dict[str, Any]:
        try:
            return json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _initialize_database(path: Path, project_id: str, name: str, created_at: str) -> None:
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_metadata (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute("INSERT OR REPLACE INTO schema_metadata(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
            connection.execute(
                "INSERT OR REPLACE INTO project_metadata(project_id, name, created_at, updated_at) VALUES(?, ?, ?, ?)",
                (project_id, name, created_at, _utc_now()),
            )
            connection.commit()

    @staticmethod
    def _migrate_database(path: Path) -> None:
        """Apply project migrations safely; every statement is idempotent."""
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(EVIDENCE_SCHEMA)
            ProjectManager._add_column(connection, "evidence", "review_status", "TEXT NOT NULL DEFAULT 'unreviewed'")
            ProjectManager._add_column(connection, "evidence", "reviewer_notes", "TEXT NOT NULL DEFAULT ''")
            ProjectManager._add_column(connection, "evidence", "duplicate_of_evidence_id", "TEXT REFERENCES evidence(evidence_id) ON DELETE SET NULL")
            ProjectManager._add_column(connection, "claim_evidence", "relevance_notes", "TEXT NOT NULL DEFAULT ''")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_evidence_review_status ON evidence(review_status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_evidence_duplicate ON evidence(duplicate_of_evidence_id)")
            connection.executescript(EVIDENCE_ANALYSIS_SCHEMA)
            connection.executescript(TIMELINE_SCHEMA)
            connection.executescript(NEXUS_SCHEMA)
            connection.executescript(DBQ_SCHEMA)
            connection.executescript(RATING_STRATEGY_SCHEMA)
            connection.executescript(OPTIMIZER_SCHEMA)
            connection.executescript(SUBMISSION_SCHEMA)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_evidence_updated ON evidence(updated_at DESC, evidence_id);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()

    @staticmethod
    def _schema_version(path: Path) -> int:
        try:
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    "SELECT value FROM schema_metadata WHERE key='schema_version'"
                ).fetchone()
        except sqlite3.Error as exc:
            raise ValueError("The project database cannot be read safely.") from exc
        if row is None:
            return 1
        try:
            return int(row[0])
        except (TypeError, ValueError) as exc:
            raise ValueError("The project database has an invalid schema version.") from exc

    def _backup_before_migration(self, database_path: Path, project_id: str) -> Path:
        self.paths.backups.mkdir(parents=True, exist_ok=True)
        destination = self.paths.backups / (
            f"migration-{project_id}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
        )
        temp = destination.with_suffix(".incomplete")
        try:
            source = sqlite3.connect(database_path)
            target = sqlite3.connect(temp)
            try:
                source.backup(target)
                target.commit()
            finally:
                target.close()
                source.close()
            temp.replace(destination)
            return destination
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    @staticmethod
    def _add_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
