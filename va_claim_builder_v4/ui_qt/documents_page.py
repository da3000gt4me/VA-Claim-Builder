from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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
from core.projects import ProjectInfo


class DocumentsPage(QWidget):
    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = DocumentManager(project)

        heading = QLabel("Project Documents")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "Imported files are copied into this project's persistent uploads folder. "
            "Duplicate content is detected with SHA-256 hashing."
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
        self.summary.setText(f"{len(documents)} document{'s' if len(documents) != 1 else ''} in this project")

    def _add_documents(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Project Documents",
            str(Path.home()),
            "Supported documents (*.pdf *.docx *.txt *.png *.jpg *.jpeg *.tif *.tiff);;All files (*.*)",
        )
        if not filenames:
            return
        try:
            imported, duplicates = self.manager.import_files(filenames)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.refresh()
        message = f"Imported {len(imported)} new document(s)."
        if duplicates:
            message += f" Skipped {len(duplicates)} duplicate(s)."
        QMessageBox.information(self, "Import complete", message)

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
