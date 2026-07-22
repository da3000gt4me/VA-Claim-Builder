from __future__ import annotations
import hashlib, mimetypes, shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from core.ingestion.categories import DocumentCategory, DRAFT_CATEGORIES
from core.storage.project_db import ProjectDB

@dataclass
class IngestResult:
    document_id: str
    duplicate_of: str | None
    original_path: Path
    working_path: Path | None
    sha256: str

class DocumentIngestor:
    def __init__(self, db: ProjectDB, project_root: str | Path):
        self.db = db
        self.project_root = Path(project_root)
        (self.project_root / "originals").mkdir(parents=True, exist_ok=True)
        (self.project_root / "working").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    def ingest_path(self, project_id: str, source: str | Path, category: DocumentCategory, claim_ids: list[str] | None = None) -> IngestResult:
        source = Path(source)
        if not source.is_file(): raise FileNotFoundError(source)
        safe_name = source.name.replace("/", "_").replace("\\", "_")
        category_dir = self.project_root / "originals" / category.value
        category_dir.mkdir(parents=True, exist_ok=True)
        destination = category_dir / safe_name
        if destination.exists():
            destination = category_dir / f"{destination.stem}_{source.stat().st_mtime_ns}{destination.suffix}"
        shutil.copy2(source, destination)
        digest = self._digest(destination)
        duplicate = self.db.find_duplicate(project_id, digest)
        working_path = None
        if category in DRAFT_CATEGORIES:
            working_dir = self.project_root / "working" / category.value
            working_dir.mkdir(parents=True, exist_ok=True)
            working_path = working_dir / destination.name
            shutil.copy2(destination, working_path)
        doc_id = self.db.add_document({
            "project_id": project_id, "category": category.value, "original_name": source.name,
            "original_path": str(destination), "working_path": str(working_path) if working_path else None,
            "sha256": digest, "mime_type": mimetypes.guess_type(source.name)[0],
            "duplicate_of": duplicate["id"] if duplicate else None,
            "classification_reviewed": category != DocumentCategory.UNCLASSIFIED,
            "signed_status": "draft" if category in DRAFT_CATEGORIES else "unknown",
            "metadata": {"editable_starting_point": category in DRAFT_CATEGORIES},
        })
        if claim_ids: self.db.link_document_claims(doc_id, claim_ids)
        return IngestResult(doc_id, duplicate["id"] if duplicate else None, destination, working_path, digest)
