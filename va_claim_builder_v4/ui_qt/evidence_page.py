from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EVIDENCE_STRENGTHS, EVIDENCE_TYPES, EvidenceManager
from core.projects import ProjectInfo


class EvidencePage(QWidget):
    """Native project workspace for cataloging and linking claim evidence."""

    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = EvidenceManager(project)
        self.claims = ClaimManager(project)
        self.documents = DocumentManager(project)
        self.current_id: str | None = None

        heading = QLabel("Evidence Workspace")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "Catalog evidence once, associate an existing project document if applicable, "
            "and link the evidence to every claim it supports. OCR is optional and may be completed later."
        )
        description.setWordWrap(True)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search title, description, provider, notes, or document…")
        self.type_filter = QComboBox(); self.type_filter.addItem("All evidence types", "")
        for value in EVIDENCE_TYPES: self.type_filter.addItem(value.title(), value)
        self.claim_filter = QComboBox(); self.claim_filter.addItem("All claims", "")
        refresh_button = QPushButton("Refresh"); refresh_button.clicked.connect(self.refresh)
        self.search_box.textChanged.connect(self.refresh)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.claim_filter.currentIndexChanged.connect(self.refresh)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Search")); filters.addWidget(self.search_box, 1)
        filters.addWidget(QLabel("Type")); filters.addWidget(self.type_filter)
        filters.addWidget(QLabel("Claim")); filters.addWidget(self.claim_filter)
        filters.addWidget(refresh_button)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Title", "Type", "Date", "Provider / Source", "Strength", "OCR"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.empty_message = QLabel("No evidence has been added to this project yet.")
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_message.setStyleSheet("color: #666; padding: 18px;")

        self.title = QLineEdit()
        self.description = QTextEdit()
        self.evidence_type = QComboBox(); self.evidence_type.addItems(EVIDENCE_TYPES)
        self.document = QComboBox()
        self.document.currentIndexChanged.connect(self._update_ocr_status)
        self.evidence_date = QLineEdit(); self.evidence_date.setPlaceholderText("YYYY-MM-DD (optional)")
        self.provider_source = QLineEdit()
        self.relevance_notes = QTextEdit()
        self.strength_status = QComboBox(); self.strength_status.addItems(EVIDENCE_STRENGTHS)
        self.ocr_status = QLabel("Not associated")
        self.claim_links = QListWidget()
        self.claim_links.setMinimumHeight(100)

        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Evidence type", self.evidence_type)
        form.addRow("Evidence date", self.evidence_date)
        form.addRow("Provider / source", self.provider_source)
        form.addRow("Source document", self.document)
        form.addRow("Document OCR", self.ocr_status)
        form.addRow("Strength / status", self.strength_status)
        form.addRow("Description", self.description)
        form.addRow("Relevance notes", self.relevance_notes)
        form.addRow("Linked claims", self.claim_links)
        editor = QWidget(); editor.setLayout(form)

        left = QWidget(); left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.table, 1); left_layout.addWidget(self.empty_message)
        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(editor)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)

        new_button = QPushButton("New Evidence"); new_button.clicked.connect(self.clear_editor)
        save_button = QPushButton("Save Evidence"); save_button.clicked.connect(self.save)
        delete_button = QPushButton("Delete Evidence"); delete_button.clicked.connect(self.delete)
        buttons = QHBoxLayout()
        for button in (new_button, save_button, delete_button): buttons.addWidget(button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(heading); layout.addWidget(description); layout.addLayout(buttons)
        layout.addLayout(filters); layout.addWidget(splitter, 1)
        self._reload_options()
        self.refresh()

    def _reload_options(self) -> None:
        selected_filter = self.claim_filter.currentData()
        self.claim_filter.blockSignals(True)
        self.claim_filter.clear(); self.claim_filter.addItem("All claims", "")
        self.claim_links.clear()
        for claim in self.claims.list_claims():
            self.claim_filter.addItem(claim.condition_name, claim.claim_id)
            item = QListWidgetItem(claim.condition_name)
            item.setData(Qt.ItemDataRole.UserRole, claim.claim_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.claim_links.addItem(item)
        index = self.claim_filter.findData(selected_filter)
        self.claim_filter.setCurrentIndex(max(0, index))
        self.claim_filter.blockSignals(False)

        selected_document = self.document.currentData()
        self.document.clear(); self.document.addItem("No source document", None)
        for document in self.documents.list_documents():
            self.document.addItem(f"{document.original_name} ({document.status.replace('_', ' ')})", document.document_id)
        index = self.document.findData(selected_document)
        self.document.setCurrentIndex(max(0, index))

    def _update_ocr_status(self) -> None:
        document_id = self.document.currentData()
        if not document_id:
            self.ocr_status.setText("Not associated")
            return
        try:
            document = self.documents.get(str(document_id))
            self.ocr_status.setText("Available" if document.status == "ocr_complete" else "Pending")
        except KeyError:
            self.ocr_status.setText("Document unavailable")

    def refresh(self) -> None:
        try:
            self._reload_options()
            records = self.manager.list(
                evidence_type=str(self.type_filter.currentData() or "") or None,
                claim_id=str(self.claim_filter.currentData() or "") or None,
                search=self.search_box.text(),
            )
            self.table.setRowCount(len(records))
            for row, record in enumerate(records):
                values = (
                    record.title, record.evidence_type.title(), record.evidence_date,
                    record.provider_source, record.strength_status.title(), record.ocr_status.title(),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, record.evidence_id)
                    self.table.setItem(row, column, item)
            self.table.resizeColumnsToContents()
            self.empty_message.setVisible(not records)
            if not records:
                filtered = bool(self.search_box.text() or self.type_filter.currentData() or self.claim_filter.currentData())
                self.empty_message.setText(
                    "No evidence matches the current search and filters."
                    if filtered else "No evidence has been added to this project yet."
                )
        except Exception as exc:
            self.empty_message.setVisible(True)
            self.empty_message.setText(f"Unable to load evidence: {exc}")

    def clear_editor(self) -> None:
        self.current_id = None
        self.title.clear(); self.description.clear(); self.evidence_type.setCurrentText("other")
        self.document.setCurrentIndex(0); self.evidence_date.clear(); self.provider_source.clear()
        self.relevance_notes.clear(); self.strength_status.setCurrentText("unreviewed")
        self.ocr_status.setText("Not associated")
        for index in range(self.claim_links.count()): self.claim_links.item(index).setCheckState(Qt.CheckState.Unchecked)
        self.table.clearSelection()

    def _load_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None: return
        try:
            record = self.manager.get(str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)))
            linked = {claim.claim_id for claim in self.manager.claims_for_evidence(record.evidence_id)}
            self.current_id = record.evidence_id
            self.title.setText(record.title); self.description.setPlainText(record.description)
            self.evidence_type.setCurrentText(record.evidence_type)
            self.evidence_date.setText(record.evidence_date); self.provider_source.setText(record.provider_source)
            self.relevance_notes.setPlainText(record.relevance_notes)
            self.strength_status.setCurrentText(record.strength_status)
            document_index = self.document.findData(record.document_id)
            self.document.setCurrentIndex(max(0, document_index))
            self.ocr_status.setText(record.ocr_status.title())
            for index in range(self.claim_links.count()):
                item = self.claim_links.item(index)
                item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in linked else Qt.CheckState.Unchecked)
        except Exception as exc:
            QMessageBox.critical(self, "Unable to load evidence", str(exc))

    def _claim_ids(self) -> list[str]:
        return [
            str(self.claim_links.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.claim_links.count())
            if self.claim_links.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _values(self) -> dict[str, object]:
        return {
            "title": self.title.text(), "description": self.description.toPlainText(),
            "evidence_type": self.evidence_type.currentText(), "document_id": self.document.currentData(),
            "evidence_date": self.evidence_date.text(), "provider_source": self.provider_source.text(),
            "relevance_notes": self.relevance_notes.toPlainText(),
            "strength_status": self.strength_status.currentText(), "claim_ids": self._claim_ids(),
        }

    def save(self) -> None:
        try:
            values = self._values()
            if self.current_id:
                record = self.manager.update(self.current_id, **values)
            else:
                title = str(values.pop("title"))
                record = self.manager.create(title, **values)
            self.current_id = record.evidence_id
            self.refresh()
            self._select_current()
        except Exception as exc:
            QMessageBox.warning(self, "Unable to save evidence", str(exc))

    def _select_current(self) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.current_id:
                self.table.selectRow(row)
                return

    def delete(self) -> None:
        if not self.current_id:
            QMessageBox.information(self, "Delete evidence", "Select an evidence record first.")
            return
        if QMessageBox.question(
            self, "Delete evidence", "Delete this evidence record and remove all of its claim links?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.delete(self.current_id)
            self.clear_editor(); self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Unable to delete evidence", str(exc))
