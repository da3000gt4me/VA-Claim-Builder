from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image
from docx import Document
from pypdf import PdfReader
import pytesseract

from core.documents import DocumentManager
from core.projects import ProjectInfo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class OCRResult:
    document_id: str
    text_path: Path
    metadata_path: Path
    page_count: int
    character_count: int
    method: str
    completed_at: str


class OCRManager:
    """Extracts searchable text and stores project-scoped OCR artifacts."""

    def __init__(self, project: ProjectInfo) -> None:
        self.project = project
        self.documents = DocumentManager(project)
        self.output_dir = project.root / "ocr"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def process(
        self,
        document_id: str,
        *,
        progress: Callable[[int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OCRResult:
        document = self.documents.get(document_id)
        suffix = document.stored_path.suffix.lower()
        emit = progress or (lambda _percent, _message: None)
        is_cancelled = cancelled or (lambda: False)
        emit(1, f"Preparing {document.original_name}")

        if suffix == ".pdf":
            pages, method = self._extract_pdf(document.stored_path, emit, is_cancelled)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            if is_cancelled():
                raise InterruptedError("OCR cancelled")
            emit(25, "Running image OCR")
            with Image.open(document.stored_path) as image:
                pages = [pytesseract.image_to_string(image)]
            method = "tesseract-image"
        elif suffix == ".docx":
            emit(30, "Extracting Word document text")
            word = Document(document.stored_path)
            pages = ["\n".join(paragraph.text for paragraph in word.paragraphs)]
            method = "docx-text"
        elif suffix in {".txt", ".md", ".csv", ".json"}:
            emit(30, "Reading text document")
            pages = [document.stored_path.read_text(encoding="utf-8", errors="replace")]
            method = "plain-text"
        else:
            raise ValueError(f"OCR/text extraction is not supported for {suffix or 'this file type'}.")

        if is_cancelled():
            raise InterruptedError("OCR cancelled")

        labeled = []
        for index, text in enumerate(pages, start=1):
            labeled.append(f"--- PAGE {index} ---\n{text.strip()}\n")
        combined = "\n".join(labeled).strip() + "\n"
        text_path = self.output_dir / f"{document_id}.txt"
        metadata_path = self.output_dir / f"{document_id}.json"
        completed_at = _utc_now()
        text_path.write_text(combined, encoding="utf-8")
        metadata = {
            "document_id": document_id,
            "source_name": document.original_name,
            "page_count": len(pages),
            "character_count": len(combined),
            "method": method,
            "completed_at": completed_at,
            "text_path": str(text_path),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        with sqlite3.connect(self.project.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ocr_results(
                    document_id, text_path, metadata_path, page_count,
                    character_count, method, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    str(text_path.relative_to(self.project.root)),
                    str(metadata_path.relative_to(self.project.root)),
                    len(pages),
                    len(combined),
                    method,
                    completed_at,
                ),
            )
            connection.execute("UPDATE documents SET status = 'ocr_complete' WHERE document_id = ?", (document_id,))
            connection.commit()
        emit(100, f"Completed {document.original_name}")
        return self.get(document_id)

    def get(self, document_id: str) -> OCRResult:
        with sqlite3.connect(self.project.database_path) as connection:
            row = connection.execute(
                """
                SELECT document_id, text_path, metadata_path, page_count,
                       character_count, method, completed_at
                FROM ocr_results WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return OCRResult(
            document_id=str(row[0]),
            text_path=self.project.root / str(row[1]),
            metadata_path=self.project.root / str(row[2]),
            page_count=int(row[3]),
            character_count=int(row[4]),
            method=str(row[5]),
            completed_at=str(row[6]),
        )

    def list_results(self) -> list[OCRResult]:
        with sqlite3.connect(self.project.database_path) as connection:
            ids = [row[0] for row in connection.execute("SELECT document_id FROM ocr_results ORDER BY completed_at DESC")]
        return [self.get(str(document_id)) for document_id in ids]

    def _extract_pdf(self, path: Path, emit: Callable[[int, str], None], is_cancelled: Callable[[], bool]) -> tuple[list[str], str]:
        reader = PdfReader(str(path))
        pages: list[str] = []
        total = max(len(reader.pages), 1)
        for index, page in enumerate(reader.pages, start=1):
            if is_cancelled():
                raise InterruptedError("OCR cancelled")
            emit(max(2, int(index / total * 90)), f"Extracting PDF page {index} of {total}")
            pages.append(page.extract_text() or "")
        return pages, "pypdf-text"

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.project.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ocr_results (
                    document_id TEXT PRIMARY KEY,
                    text_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    character_count INTEGER NOT NULL,
                    method TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ocr_completed_at ON ocr_results(completed_at);
                """
            )
            connection.commit()
