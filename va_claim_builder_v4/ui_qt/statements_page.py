from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from core.intake import IntakeManager


class StatementsPage(QWidget):
    """Review imported buddy/witness statements without converting lay facts to diagnoses."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.manager = IntakeManager(project)
        heading = QLabel("Buddy & Witness Statements")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        notice = QLabel(
            "Imported lay statements remain review drafts. Firsthand observations, information "
            "reported to the witness, and medical conclusions must be reviewed separately."
        )
        notice.setWordWrap(True)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Author", "Relationship", "Condition", "Status", "Signed"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._show)
        self.preview = QTextEdit(); self.preview.setReadOnly(True)
        splitter = QSplitter(); splitter.addWidget(self.table); splitter.addWidget(self.preview)
        accept = QPushButton("Accept Imported Statement"); accept.clicked.connect(lambda: self._decide("accepted"))
        reject = QPushButton("Reject Extraction"); reject.clicked.connect(lambda: self._decide("rejected"))
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        for button in (accept, reject, refresh): actions.addWidget(button)
        actions.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(heading); layout.addWidget(notice); layout.addLayout(actions); layout.addWidget(splitter, 1)
        self.refresh()

    def refresh(self):
        rows = self.manager.list_imported_statements("buddy_witness_statement")
        self.table.setRowCount(len(rows))
        for row, statement in enumerate(rows):
            fields = statement["fields"]
            values = (
                fields.get("author", ""), fields.get("relationship", ""),
                fields.get("condition", ""), statement["status"],
                "Yes" if fields.get("signed") else "No",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, statement["statement_id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, json.dumps(fields, indent=2))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _show(self):
        row = self.table.currentRow()
        self.preview.setPlainText(
            str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1))
            if row >= 0 and self.table.item(row, 0) else ""
        )

    def _decide(self, status):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Buddy statement", "Select an imported statement first."); return
        self.manager.decide_statement(
            str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)), status
        )
        self.refresh()
