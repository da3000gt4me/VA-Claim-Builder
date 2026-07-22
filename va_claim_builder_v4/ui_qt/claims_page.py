from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from core.claims import CLAIM_STATUSES, CLAIM_TYPES, ClaimManager
from core.projects import ProjectInfo


class ClaimsPage(QWidget):
    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = ClaimManager(project)
        self.current_id: str | None = None

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Condition", "Type", "Status", "Secondary to"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected)

        self.condition = QLineEdit()
        self.claim_type = QComboBox(); self.claim_type.addItems(CLAIM_TYPES)
        self.status = QComboBox(); self.status.addItems(CLAIM_STATUSES)
        self.secondary_to = QLineEdit()
        self.description = QTextEdit()
        self.service_event = QTextEdit()
        self.current_diagnosis = QTextEdit()
        self.symptoms = QTextEdit()
        self.notes = QTextEdit()

        form = QFormLayout()
        form.addRow("Condition", self.condition)
        form.addRow("Claim type", self.claim_type)
        form.addRow("Status", self.status)
        form.addRow("Secondary to", self.secondary_to)
        form.addRow("Description", self.description)
        form.addRow("In-service event/exposure", self.service_event)
        form.addRow("Current diagnosis", self.current_diagnosis)
        form.addRow("Symptoms/functional impact", self.symptoms)
        form.addRow("Notes", self.notes)
        editor = QWidget(); editor.setLayout(form)

        splitter = QSplitter(); splitter.addWidget(self.table); splitter.addWidget(editor)
        splitter.setStretchFactor(1, 1)

        new_button = QPushButton("New Claim"); new_button.clicked.connect(self.clear_editor)
        save_button = QPushButton("Save Claim"); save_button.clicked.connect(self.save)
        delete_button = QPushButton("Delete"); delete_button.clicked.connect(self.delete)
        up_button = QPushButton("Move Up"); up_button.clicked.connect(lambda: self.move(-1))
        down_button = QPushButton("Move Down"); down_button.clicked.connect(lambda: self.move(1))
        buttons = QHBoxLayout()
        for button in (new_button, save_button, delete_button, up_button, down_button): buttons.addWidget(button)
        buttons.addStretch()

        heading = QLabel("Claims Workspace")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout = QVBoxLayout(self)
        layout.addWidget(heading); layout.addLayout(buttons); layout.addWidget(splitter)
        self.refresh()

    def refresh(self) -> None:
        claims = self.manager.list_claims()
        self.table.setRowCount(len(claims))
        for row, claim in enumerate(claims):
            values = (claim.condition_name, claim.claim_type, claim.status, claim.secondary_to)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, claim.claim_id)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def clear_editor(self) -> None:
        self.current_id = None
        self.condition.clear(); self.claim_type.setCurrentText("direct")
        self.status.setCurrentText("draft"); self.secondary_to.clear()
        for field in (self.description, self.service_event, self.current_diagnosis, self.symptoms, self.notes): field.clear()
        self.table.clearSelection()

    def _load_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None: return
        claim_id = self.table.item(row, 0).data(256)
        claim = self.manager.get(claim_id)
        self.current_id = claim.claim_id
        self.condition.setText(claim.condition_name); self.claim_type.setCurrentText(claim.claim_type)
        self.status.setCurrentText(claim.status); self.secondary_to.setText(claim.secondary_to)
        self.description.setPlainText(claim.description); self.service_event.setPlainText(claim.service_event)
        self.current_diagnosis.setPlainText(claim.current_diagnosis); self.symptoms.setPlainText(claim.symptoms)
        self.notes.setPlainText(claim.notes)

    def _values(self) -> dict[str, str]:
        return {
            "condition_name": self.condition.text(), "claim_type": self.claim_type.currentText(),
            "status": self.status.currentText(), "secondary_to": self.secondary_to.text(),
            "description": self.description.toPlainText(), "service_event": self.service_event.toPlainText(),
            "current_diagnosis": self.current_diagnosis.toPlainText(), "symptoms": self.symptoms.toPlainText(),
            "notes": self.notes.toPlainText(),
        }

    def save(self) -> None:
        try:
            values = self._values()
            if self.current_id:
                claim = self.manager.update(self.current_id, **values)
            else:
                name = values.pop("condition_name")
                claim = self.manager.create(name, **values)
            self.current_id = claim.claim_id; self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Unable to save claim", str(exc))

    def delete(self) -> None:
        if not self.current_id: return
        if QMessageBox.question(self, "Delete claim", "Delete this claimed condition?") != QMessageBox.StandardButton.Yes: return
        self.manager.delete(self.current_id); self.clear_editor(); self.refresh()

    def move(self, offset: int) -> None:
        if not self.current_id: return
        self.manager.move(self.current_id, offset); self.refresh()
