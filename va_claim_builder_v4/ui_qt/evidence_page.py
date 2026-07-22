from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import (
    EVIDENCE_STRENGTHS, EVIDENCE_TYPES, OCR_FILTERS, REVIEW_STATUSES, EvidenceManager,
)
from core.projects import ProjectInfo


class EvidencePage(QWidget):
    """Review evidence, its source text, and per-claim relevance in one workspace."""

    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = EvidenceManager(project)
        self.claims = ClaimManager(project)
        self.documents = DocumentManager(project)
        self.current_id: str | None = None
        self._claim_notes: dict[str, str] = {}
        self._active_claim_id: str | None = None
        self._loading = False
        self._saved_snapshot: tuple[object, ...] | None = None

        heading = QLabel("Evidence Review Workspace")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "Review each evidence item, inspect its OCR source text, and record how it relates to each linked claim."
        )
        description.setWordWrap(True)

        self.search_box = QLineEdit(); self.search_box.setPlaceholderText(
            "Search evidence, reviewer and claim notes, provider/source, or OCR text…"
        )
        self.status_filter = QComboBox(); self.status_filter.addItem("All review statuses", "")
        for value in REVIEW_STATUSES: self.status_filter.addItem(value.title(), value)
        self.type_filter = QComboBox(); self.type_filter.addItem("All evidence types", "")
        for value in EVIDENCE_TYPES: self.type_filter.addItem(value.title(), value)
        self.claim_filter = QComboBox(); self.claim_filter.addItem("All claims", "")
        self.unlinked_filter = QCheckBox("Unlinked only")
        self.ocr_filter = QComboBox(); self.ocr_filter.addItem("Any OCR", "")
        for value in OCR_FILTERS: self.ocr_filter.addItem(value.title(), value)
        refresh_button = QPushButton("Refresh"); refresh_button.clicked.connect(self.refresh)
        for control in (self.search_box, self.status_filter, self.type_filter, self.claim_filter, self.ocr_filter):
            (control.textChanged if isinstance(control, QLineEdit) else control.currentIndexChanged).connect(self.refresh)
        self.unlinked_filter.toggled.connect(self.refresh)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Search")); filters.addWidget(self.search_box, 1)
        for label, control in (("Status", self.status_filter), ("Type", self.type_filter),
                               ("Claim", self.claim_filter), ("OCR", self.ocr_filter)):
            filters.addWidget(QLabel(label)); filters.addWidget(control)
        filters.addWidget(self.unlinked_filter); filters.addWidget(refresh_button)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Title", "Review", "Type", "Date", "Provider / Source", "Claims", "OCR"])
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
        self.document = QComboBox(); self.document.currentIndexChanged.connect(self._update_source_review)
        self.evidence_date = QLineEdit(); self.evidence_date.setPlaceholderText("YYYY-MM-DD (optional)")
        self.provider_source = QLineEdit()
        self.relevance_notes = QTextEdit()
        self.strength_status = QComboBox(); self.strength_status.addItems(EVIDENCE_STRENGTHS)
        self.review_status = QComboBox(); self.review_status.addItems(REVIEW_STATUSES)
        self.review_status.currentTextChanged.connect(self._duplicate_state_changed)
        self.reviewer_notes = QTextEdit()
        self.duplicate_of = QComboBox(); self.duplicate_of.addItem("No retained evidence reference", None)
        self.duplicate_banner = QLabel("")
        self.duplicate_banner.setStyleSheet("color: #8a4b08; font-weight: 600;")

        details_form = QFormLayout()
        for label, control in (
            ("Title", self.title), ("Evidence type", self.evidence_type), ("Evidence date", self.evidence_date),
            ("Provider / source", self.provider_source), ("Source document", self.document),
            ("Strength", self.strength_status), ("Review status", self.review_status),
            ("Retained evidence", self.duplicate_of), ("Description", self.description),
            ("General relevance notes", self.relevance_notes), ("Reviewer notes", self.reviewer_notes),
        ): details_form.addRow(label, control)
        details_form.addRow("", self.duplicate_banner)
        details_tab = QWidget(); details_tab.setLayout(details_form)

        self.claim_links = QListWidget(); self.claim_links.setMinimumHeight(150)
        self.claim_links.currentItemChanged.connect(self._claim_selection_changed)
        self.claim_note = QTextEdit(); self.claim_note.setPlaceholderText("Why this evidence matters to the selected claim…")
        self.claim_note.textChanged.connect(self._store_active_claim_note)
        claim_help = QLabel("Check one or more claims. Select a claim to edit its claim-specific relevance note.")
        claim_help.setWordWrap(True)
        claim_tab = QWidget(); claim_layout = QVBoxLayout(claim_tab)
        claim_layout.addWidget(claim_help); claim_layout.addWidget(self.claim_links, 1)
        claim_layout.addWidget(QLabel("Selected claim relevance note")); claim_layout.addWidget(self.claim_note, 1)

        self.document_name = QLabel("No source document")
        self.document_type = QLabel("—")
        self.ocr_status = QLabel("Not associated")
        self.ocr_preview = QTextEdit(); self.ocr_preview.setReadOnly(True)
        self.ocr_preview.setPlaceholderText("Select evidence with available OCR text to preview it here.")
        source_form = QFormLayout(); source_form.addRow("Document", self.document_name)
        source_form.addRow("Document type", self.document_type); source_form.addRow("OCR status", self.ocr_status)
        source_tab = QWidget(); source_layout = QVBoxLayout(source_tab)
        source_layout.addLayout(source_form); source_layout.addWidget(QLabel("OCR text preview")); source_layout.addWidget(self.ocr_preview, 1)

        tabs = QTabWidget(); tabs.addTab(details_tab, "Review"); tabs.addTab(claim_tab, "Claim Associations")
        tabs.addTab(source_tab, "OCR & Source")
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.table, 1); left_layout.addWidget(self.empty_message)
        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)

        new_button = QPushButton("New Evidence"); new_button.clicked.connect(self.clear_editor)
        save_button = QPushButton("Save Review"); save_button.clicked.connect(self.save)
        delete_button = QPushButton("Delete Evidence"); delete_button.clicked.connect(self.delete)
        buttons = QHBoxLayout()
        for button in (new_button, save_button, delete_button): buttons.addWidget(button)
        buttons.addStretch()
        layout = QVBoxLayout(self); layout.addWidget(heading); layout.addWidget(description)
        layout.addLayout(buttons); layout.addLayout(filters); layout.addWidget(splitter, 1)
        self._reload_options(); self.refresh(); self._capture_snapshot()

    def _reload_options(self) -> None:
        filter_claim = self.claim_filter.currentData(); selected_document = self.document.currentData()
        checked = set(self._claim_ids()) if hasattr(self, "claim_links") else set()
        self.claim_filter.blockSignals(True); self.claim_filter.clear(); self.claim_filter.addItem("All claims", "")
        self.claim_links.blockSignals(True); self.claim_links.clear()
        for claim in self.claims.list_claims():
            self.claim_filter.addItem(claim.condition_name, claim.claim_id)
            item = QListWidgetItem(claim.condition_name); item.setData(Qt.ItemDataRole.UserRole, claim.claim_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if claim.claim_id in checked else Qt.CheckState.Unchecked)
            self.claim_links.addItem(item)
        self.claim_links.blockSignals(False)
        self.claim_filter.setCurrentIndex(max(0, self.claim_filter.findData(filter_claim))); self.claim_filter.blockSignals(False)
        self.document.blockSignals(True); self.document.clear(); self.document.addItem("No source document", None)
        for document in self.documents.list_documents():
            self.document.addItem(f"{document.original_name} ({document.status.replace('_', ' ')})", document.document_id)
        self.document.setCurrentIndex(max(0, self.document.findData(selected_document))); self.document.blockSignals(False)

    def _reload_duplicate_options(self, selected: str | None = None) -> None:
        self.duplicate_of.blockSignals(True); self.duplicate_of.clear()
        self.duplicate_of.addItem("No retained evidence reference", None)
        for record in self.manager.list():
            if record.evidence_id != self.current_id:
                self.duplicate_of.addItem(record.title, record.evidence_id)
        self.duplicate_of.setCurrentIndex(max(0, self.duplicate_of.findData(selected)))
        self.duplicate_of.blockSignals(False)

    def refresh(self) -> None:
        if self._loading: return
        selected_id = self.current_id
        try:
            self._reload_options()
            records = self.manager.list(
                review_status=str(self.status_filter.currentData() or "") or None,
                evidence_type=str(self.type_filter.currentData() or "") or None,
                claim_id=str(self.claim_filter.currentData() or "") or None,
                unlinked=self.unlinked_filter.isChecked(),
                ocr_availability=str(self.ocr_filter.currentData() or "") or None,
                search=self.search_box.text(),
            )
            self.table.blockSignals(True); self.table.setRowCount(len(records))
            for row, record in enumerate(records):
                values = (record.title, record.review_status.title(), record.evidence_type.title(), record.evidence_date,
                          record.provider_source, str(len(self.manager.claim_links_for_evidence(record.evidence_id))), record.ocr_status.title())
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole, record.evidence_id)
                    self.table.setItem(row, column, item)
            self.table.blockSignals(False); self.table.resizeColumnsToContents()
            self.empty_message.setVisible(not records)
            filtered = bool(self.search_box.text() or self.status_filter.currentData() or self.type_filter.currentData()
                            or self.claim_filter.currentData() or self.unlinked_filter.isChecked() or self.ocr_filter.currentData())
            self.empty_message.setText("No evidence matches the current search and filters." if filtered
                                       else "No evidence has been added to this project yet.")
            self._reload_duplicate_options(self.duplicate_of.currentData())
            self.current_id = selected_id; self._select_current()
        except Exception as exc:
            self.table.blockSignals(False); self.empty_message.setVisible(True)
            self.empty_message.setText(f"Unable to load evidence: {exc}")

    def clear_editor(self) -> None:
        if not self._confirm_discard(): return
        self._loading = True; self.current_id = None; self._claim_notes.clear(); self._active_claim_id = None
        self.title.clear(); self.description.clear(); self.evidence_type.setCurrentText("other")
        self.document.setCurrentIndex(0); self.evidence_date.clear(); self.provider_source.clear()
        self.relevance_notes.clear(); self.strength_status.setCurrentText("unreviewed")
        self.review_status.setCurrentText("unreviewed"); self.reviewer_notes.clear()
        self._reload_duplicate_options(); self.duplicate_of.setCurrentIndex(0); self.claim_note.clear()
        for index in range(self.claim_links.count()): self.claim_links.item(index).setCheckState(Qt.CheckState.Unchecked)
        self.table.clearSelection(); self._loading = False; self._update_source_review(); self._duplicate_state_changed()
        self._capture_snapshot()

    def _load_selected(self) -> None:
        if self._loading: return
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0): return
        requested = str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        if requested == self.current_id: return
        if not self._confirm_discard(): self._select_current(); return
        try:
            record = self.manager.get(requested); links = self.manager.claim_links_for_evidence(requested)
            linked = {link.claim_id for link in links}; self._claim_notes = {link.claim_id: link.relevance_notes for link in links}
            self._loading = True; self.current_id = record.evidence_id; self._active_claim_id = None
            self.title.setText(record.title); self.description.setPlainText(record.description)
            self.evidence_type.setCurrentText(record.evidence_type); self.evidence_date.setText(record.evidence_date)
            self.provider_source.setText(record.provider_source); self.relevance_notes.setPlainText(record.relevance_notes)
            self.strength_status.setCurrentText(record.strength_status); self.review_status.setCurrentText(record.review_status)
            self.reviewer_notes.setPlainText(record.reviewer_notes)
            self.document.setCurrentIndex(max(0, self.document.findData(record.document_id)))
            self._reload_duplicate_options(record.duplicate_of_evidence_id)
            for index in range(self.claim_links.count()):
                item = self.claim_links.item(index); item.setCheckState(
                    Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in linked else Qt.CheckState.Unchecked)
            self.claim_note.clear(); self._loading = False; self._update_source_review(); self._duplicate_state_changed()
            self._capture_snapshot()
        except Exception as exc:
            self._loading = False; QMessageBox.critical(self, "Unable to load evidence", str(exc))

    def _claim_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if self._loading: return
        self._store_active_claim_note(); self._active_claim_id = str(current.data(Qt.ItemDataRole.UserRole)) if current else None
        self.claim_note.blockSignals(True); self.claim_note.setPlainText(self._claim_notes.get(self._active_claim_id or "", ""))
        self.claim_note.setEnabled(bool(current)); self.claim_note.blockSignals(False)

    def _store_active_claim_note(self) -> None:
        if not self._loading and self._active_claim_id:
            self._claim_notes[self._active_claim_id] = self.claim_note.toPlainText()

    def _claim_ids(self) -> list[str]:
        return [str(self.claim_links.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.claim_links.count())
                if self.claim_links.item(i).checkState() == Qt.CheckState.Checked]

    def _values(self) -> dict[str, object]:
        self._store_active_claim_note(); claim_ids = self._claim_ids()
        return {
            "title": self.title.text(), "description": self.description.toPlainText(),
            "evidence_type": self.evidence_type.currentText(), "document_id": self.document.currentData(),
            "evidence_date": self.evidence_date.text(), "provider_source": self.provider_source.text(),
            "relevance_notes": self.relevance_notes.toPlainText(), "strength_status": self.strength_status.currentText(),
            "review_status": self.review_status.currentText(), "reviewer_notes": self.reviewer_notes.toPlainText(),
            "duplicate_of_evidence_id": self.duplicate_of.currentData() if self.review_status.currentText() == "duplicate" else None,
            "claim_ids": claim_ids, "claim_relevance_notes": {key: self._claim_notes.get(key, "") for key in claim_ids},
        }

    def save(self) -> None:
        try:
            values = self._values()
            if self.current_id: record = self.manager.update(self.current_id, **values)
            else: record = self.manager.create(str(values.pop("title")), **values)
            self.current_id = record.evidence_id; self._capture_snapshot(); self.refresh(); self._select_current()
        except Exception as exc: QMessageBox.warning(self, "Unable to save evidence", str(exc))

    def _select_current(self) -> None:
        if not self.current_id: return
        self._loading = True
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.current_id:
                self.table.selectRow(row); break
        self._loading = False

    def _update_source_review(self) -> None:
        document_id = self.document.currentData()
        if not document_id:
            self.document_name.setText("No source document"); self.document_type.setText("—")
            self.ocr_status.setText("Not associated"); self.ocr_preview.clear(); return
        try:
            document = self.documents.get(str(document_id)); self.document_name.setText(document.original_name)
            self.document_type.setText(document.mime_type or "Unknown")
            text = self.manager.ocr_text(self.current_id) if self.current_id and self.manager.get(self.current_id).document_id == document_id else None
            if text:
                self.ocr_status.setText("Available"); self.ocr_preview.setPlainText(text)
            elif document.status in {"ocr_failed", "failed"}:
                self.ocr_status.setText("Failed — review the OCR workspace and retry"); self.ocr_preview.setPlainText("OCR failed for this document.")
            elif document.status == "ocr_complete":
                self.ocr_status.setText("No extractable text"); self.ocr_preview.setPlainText("OCR completed, but no extractable text was found.")
            else:
                self.ocr_status.setText("Pending"); self.ocr_preview.setPlainText("OCR has not completed for this document.")
        except KeyError:
            self.document_name.setText("Document unavailable"); self.document_type.setText("—")
            self.ocr_status.setText("Unavailable"); self.ocr_preview.clear()

    def _duplicate_state_changed(self) -> None:
        duplicate = self.review_status.currentText() == "duplicate"
        self.duplicate_of.setEnabled(duplicate)
        self.duplicate_banner.setText("Marked duplicate; the evidence and source document are preserved." if duplicate else "")

    def _snapshot(self) -> tuple[object, ...]:
        values = self._values()
        return tuple((key, repr(values[key])) for key in sorted(values))

    def _capture_snapshot(self) -> None: self._saved_snapshot = self._snapshot()

    def _confirm_discard(self) -> bool:
        if self._saved_snapshot is None or self._snapshot() == self._saved_snapshot: return True
        return QMessageBox.question(self, "Discard unsaved edits?", "Discard the unsaved evidence review edits?") == QMessageBox.StandardButton.Yes

    def delete(self) -> None:
        if not self.current_id:
            QMessageBox.information(self, "Delete evidence", "Select an evidence record first."); return
        if QMessageBox.question(self, "Delete evidence", "Delete this evidence record and remove all of its claim links? The source document is preserved.") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.delete(self.current_id); self._saved_snapshot = None; self.clear_editor(); self.refresh()
        except Exception as exc: QMessageBox.critical(self, "Unable to delete evidence", str(exc))
