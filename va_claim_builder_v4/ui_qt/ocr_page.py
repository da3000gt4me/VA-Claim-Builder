from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.documents import DocumentManager
from core.ocr import OCRManager
from core.projects import ProjectInfo


class OCRWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: OCRManager, document_ids: list[str]) -> None:
        super().__init__()
        self.manager = manager
        self.document_ids = document_ids
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            total = max(len(self.document_ids), 1)
            for index, document_id in enumerate(self.document_ids):
                if self._cancelled:
                    raise InterruptedError("OCR cancelled")

                def report(percent: int, message: str) -> None:
                    overall = int(((index + percent / 100) / total) * 100)
                    self.progress.emit(overall, message)

                self.manager.process(document_id, progress=report, cancelled=lambda: self._cancelled)
            self.completed.emit(f"Processed {len(self.document_ids)} document(s).")
        except InterruptedError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # surfaced to the desktop user
            self.failed.emit(str(exc))


class OCRPage(QWidget):
    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.documents = DocumentManager(project)
        self.ocr = OCRManager(project)
        self.worker: OCRWorker | None = None

        heading = QLabel("OCR & Text Extraction")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "Create page-labeled, searchable text artifacts inside the project's persistent OCR folder. "
            "PDFs use embedded text when available; image files use Tesseract OCR."
        )
        description.setWordWrap(True)

        self.run_button = QPushButton("Process Selected")
        self.run_button.clicked.connect(self._run_selected)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.refresh_button)
        controls.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status = QLabel("Ready")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Document", "Source Status", "OCR Method", "Pages", "Characters"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(controls)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        documents = self.documents.list_documents()
        results = {result.document_id: result for result in self.ocr.list_results()}
        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            result = results.get(document.document_id)
            item = QTableWidgetItem(document.original_name)
            item.setData(256, document.document_id)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem(document.status.replace("_", " ").title()))
            self.table.setItem(row, 2, QTableWidgetItem(result.method if result else "Not processed"))
            self.table.setItem(row, 3, QTableWidgetItem(str(result.page_count) if result else "—"))
            self.table.setItem(row, 4, QTableWidgetItem(str(result.character_count) if result else "—"))
        self.table.resizeColumnsToContents()

    def _run_selected(self) -> None:
        ids = [self.table.item(index.row(), 0).data(256) for index in self.table.selectionModel().selectedRows()]
        if not ids:
            QMessageBox.information(self, "OCR", "Select one or more documents first.")
            return
        self.worker = OCRWorker(self.ocr, [str(value) for value in ids])
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.status.setText("Cancelling after the current page…")

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, percent)))
        self.status.setText(message)

    def _on_completed(self, message: str) -> None:
        self.progress.setValue(100)
        self.status.setText(message)
        self._finish()

    def _on_failed(self, message: str) -> None:
        self.status.setText(message)
        if message != "OCR cancelled":
            QMessageBox.critical(self, "OCR failed", message)
        self._finish()

    def _finish(self) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.refresh()
        self.worker = None
