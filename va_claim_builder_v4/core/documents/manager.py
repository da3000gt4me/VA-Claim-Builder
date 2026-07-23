
from __future__ import annotations

import hashlib
import mimetypes
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.projects import ProjectInfo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    document_id: str
    original_name: str
    stored_name: str
    stored_path: Path
    sha256: str
    size_bytes: int
    mime_type: str
    status: str
    imported_at: str


class DocumentManager:
    """Imports source documents into a persistent project and catalogs them."""

    def __init__(self, project: ProjectInfo) -> None:
        self.project = project
        self.uploads_dir = project.root / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.project.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def import_file(self, source: str | Path) -> tuple[DocumentInfo, bool]:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        digest = self._sha256(source_path)
        existing = self._find_by_hash(digest)
        if existing is not None:
            return existing, False

        document_id = str(uuid.uuid4())
        suffix = source_path.suffix.lower()
        stored_name = f"{document_id}{suffix}"
        destination = self.uploads_dir / stored_name
        shutil.copy2(source_path, destination)

        mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        imported_at = _utc_now()
        size_bytes = destination.stat().st_size
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents(
                    document_id, original_name, stored_name, sha256, size_bytes,
                    mime_type, status, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    source_path.name,
                    stored_name,
                    digest,
                    size_bytes,
                    mime_type,
                    "imported",
                    imported_at,
                ),
            )
            connection.commit()
        from core.intake.manager import IntakeManager
        from core.claims import ClaimManager
        ClaimManager(self.project)
        IntakeManager(self.project).ensure_document(document_id, digest)
        return self.get(document_id), True

    def import_files(self, sources: list[str | Path]) -> tuple[list[DocumentInfo], list[DocumentInfo]]:
        imported: list[DocumentInfo] = []
        duplicates: list[DocumentInfo] = []
        for source in sources:
            document, created = self.import_file(source)
            (imported if created else duplicates).append(document)
        return imported, duplicates

    def list_documents(self) -> list[DocumentInfo]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, original_name, stored_name, sha256, size_bytes,
                       mime_type, status, imported_at
                FROM documents
                ORDER BY imported_at DESC, original_name COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_info(row) for row in rows]

    def get(self, document_id: str) -> DocumentInfo:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, original_name, stored_name, sha256, size_bytes,
                       mime_type, status, imported_at
                FROM documents WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return self._row_to_info(row)

    def remove(self, document_id: str, *, delete_file: bool = True) -> None:
        document = self.get(document_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            connection.commit()
        if delete_file:
            document.stored_path.unlink(missing_ok=True)

    def _find_by_hash(self, digest: str) -> DocumentInfo | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, original_name, stored_name, sha256, size_bytes,
                       mime_type, status, imported_at
                FROM documents WHERE sha256 = ?
                """,
                (digest,),
            ).fetchone()
        return self._row_to_info(row) if row else None

    def _row_to_info(self, row: tuple[object, ...]) -> DocumentInfo:
        return DocumentInfo(
            document_id=str(row[0]),
            original_name=str(row[1]),
            stored_name=str(row[2]),
            stored_path=self.uploads_dir / str(row[2]),
            sha256=str(row[3]),
            size_bytes=int(row[4]),
            mime_type=str(row[5]),
            status=str(row[6]),
            imported_at=str(row[7]),
        )

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL UNIQUE,
                    size_bytes INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
                CREATE INDEX IF NOT EXISTS idx_documents_name ON documents(original_name);
                """
            )
            connection.commit()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
