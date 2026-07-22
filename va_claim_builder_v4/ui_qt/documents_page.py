from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.documents import DocumentManager
from core.jobs import JobManager
from core.projects import ProjectInfo
from ui_qt.progress_panel import ProgressPanel
from workers import DocumentImportWorker


class DocumentsPage(QWidget):
    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.manager = DocumentManager(project)
        self.jobs = JobManager(project)
        self.jobs.recover_interrupted()
        self._thread: QThread | None = None
        self._worker: DocumentImportWorker | None = None

        heading = QLabel("Project Documents")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "Imported files are copied into this project's persistent uploads folder. "
            "Imports run in the background with persistent progress and cancellation support."
        )
        description.setWordWrap(True)

        self.add_button = QPushButton("Add Documents…")
        self.add_button.clicked.connect(self._add_documents)
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._remove_selected)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.remove_button)
        button_row.addStretch()

        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_button.clicked.connect(self._cancel_import)

        self.summary = QLabel()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Size", "Status", "Imported"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(button_row)
        layout.addWidget(self.progress_panel)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        documents = self.manager.list_documents()
        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            name_item = QTableWidgetItem(document.original_name)
            name_item.setData(Qt.ItemDataRole.UserRole, document.document_id)
            name_item.setToolTip(str(document.stored_path))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(document.mime_type))
            self.table.setItem(row, 2, QTableWidgetItem(self._format_size(document.size_bytes)))
            self.table.setItem(row, 3, QTableWidgetItem(document.status.title()))
            self.table.setItem(row, 4, QTableWidgetItem(document.imported_at))
        self.table.resizeColumnsToContents()
        job_count = len(self.jobs.list())
        self.summary.setText(
            f"{len(documents)} document{'s' if len(documents) != 1 else ''} in this project"
            f" · {job_count} recorded background job{'s' if job_count != 1 else ''}"
        )

    def _add_documents(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Project Documents",
            str(Path.home()),
            "Supported documents (*.pdf *.docx *.txt *.png *.jpg *.jpeg *.tif *.tiff);;All files (*.*)",
        )
        if not filenames:
            return
        self._start_import(filenames)

    def _start_import(self, filenames: list[str]) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "Import active", "A document import is already running.")
            return
        self.add_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.progress_panel.start(f"Preparing to import {len(filenames)} document(s)…")

        thread = QThread(self)
        worker = DocumentImportWorker(self.project, filenames)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress_panel.update_progress)
        worker.completed.connect(self._import_completed)
        worker.failed.connect(self._import_failed)
        worker.cancelled.connect(self._import_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._import_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _cancel_import(self) -> None:
        if self._worker is not None:
            self.progress_panel.cancel_button.setEnabled(False)
            self.progress_panel.label.setText("Cancelling after the current file…")
            self._worker.cancel()

    def _import_completed(self, imported: int, duplicates: int) -> None:
        message = f"Imported {imported} new document(s)."
        if duplicates:
            message += f" Skipped {duplicates} duplicate(s)."
        self.progress_panel.finish(message)
        self.refresh()
        QMessageBox.information(self, "Import complete", message)

    def _import_failed(self, message: str) -> None:
        self.progress_panel.finish("Import failed")
        QMessageBox.critical(self, "Import failed", message)

    def _import_cancelled(self) -> None:
        self.progress_panel.finish("Import cancelled")
        self.refresh()

    def _import_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.add_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        self.refresh()

    def _remove_selected(self) -> None:
        document_ids = {
            self.table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            for index in self.table.selectionModel().selectedRows()
        }
        if not document_ids:
            return
        answer = QMessageBox.question(
            self,
            "Remove documents",
            f"Remove {len(document_ids)} selected document(s) from this project?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for document_id in document_ids:
            self.manager.remove(str(document_id))
        self.refresh()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        value = float(size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{size_bytes} B"
