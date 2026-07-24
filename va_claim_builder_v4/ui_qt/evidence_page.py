from __future__ import annotations

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import (
    EVIDENCE_STRENGTHS, EVIDENCE_TYPES, OCR_FILTERS, REVIEW_STATUSES, EvidenceManager,
    EvidenceAnalysisRecord, EvidenceAnalysisService,
)
from core.projects import AppPaths, ProjectInfo
from core.settings import SettingsManager
from workers import EvidenceAnalysisWorker
from .checked_table import CheckableHeader


class EvidencePage(QWidget):
    """Review evidence, its source text, and per-claim relevance in one workspace."""

    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = EvidenceManager(project)
        self.project = project
        app_paths = AppPaths(root=project.root.parent.parent).ensure()
        self.settings_manager = SettingsManager(app_paths)
        self.analysis = EvidenceAnalysisService(project, settings_manager=self.settings_manager)
        self.claims = ClaimManager(project)
        self.documents = DocumentManager(project)
        self.current_id: str | None = None
        self._claim_notes: dict[str, str] = {}
        self._active_claim_id: str | None = None
        self._loading = False
        self._saved_snapshot: tuple[object, ...] | None = None
        self._analysis_thread: QThread | None = None
        self._analysis_worker: EvidenceAnalysisWorker | None = None
        self._checked_ids: set[str] = set()

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
        self.check_header = CheckableHeader(self.table)
        self.table.setHorizontalHeader(self.check_header)
        self.table.setHorizontalHeaderLabels(["Title", "Review", "Type", "Date", "Provider / Source", "Claims", "OCR"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected)
        self.table.itemChanged.connect(self._evidence_check_changed)
        self.check_header.toggled.connect(self._check_visible)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.checked_count = QLabel("0 checked")
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

        self.analysis_advisory = QLabel(
            "AI-generated analysis is advisory only and is not a medical diagnosis or legal determination."
        )
        self.analysis_advisory.setWordWrap(True)
        self.analysis_advisory.setStyleSheet("color: #8a4b08; font-weight: 600;")
        self.analysis_history = QComboBox(); self.analysis_history.currentIndexChanged.connect(self._show_history_record)
        self.analysis_metadata = QLabel("No analysis has been run for this evidence.")
        self.analysis_metadata.setWordWrap(True)
        self.analysis_result = QTextEdit(); self.analysis_result.setReadOnly(True)
        self.analysis_recommendations = QListWidget(); self.analysis_recommendations.setMinimumHeight(90)
        self.apply_recommendations_button = QPushButton("Link Approved Recommendations")
        self.apply_recommendations_button.clicked.connect(self._apply_recommendations)
        self.apply_recommendations_button.setEnabled(False)
        analysis_tab = QWidget(); analysis_layout = QVBoxLayout(analysis_tab)
        analysis_layout.addWidget(self.analysis_advisory)
        analysis_layout.addWidget(QLabel("Analysis history")); analysis_layout.addWidget(self.analysis_history)
        analysis_layout.addWidget(self.analysis_metadata); analysis_layout.addWidget(self.analysis_result, 1)
        analysis_layout.addWidget(QLabel("Recommended claim associations (review before linking)"))
        analysis_layout.addWidget(self.analysis_recommendations)
        analysis_layout.addWidget(self.apply_recommendations_button)

        self.editor_tabs = QTabWidget(); self.editor_tabs.addTab(details_tab, "Review")
        self.editor_tabs.addTab(claim_tab, "Claim Associations")
        self.editor_tabs.addTab(source_tab, "OCR & Source"); self.editor_tabs.addTab(analysis_tab, "AI Analysis")
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.checked_count); left_layout.addWidget(self.table, 1); left_layout.addWidget(self.empty_message)
        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(self.editor_tabs)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)

        new_button = QPushButton("New Evidence"); new_button.clicked.connect(self.clear_editor)
        save_button = QPushButton("Save Review"); save_button.clicked.connect(self.save)
        delete_button = QPushButton("Delete Evidence"); delete_button.clicked.connect(self.delete)
        self.analyze_selected_button = QPushButton("Analyze Selected")
        self.analyze_selected_button.clicked.connect(self._analyze_selected)
        self.analyze_batch_button = QPushButton("Analyze Checked / Filtered")
        self.analyze_batch_button.clicked.connect(self._analyze_checked_or_filtered)
        self.cancel_analysis_button = QPushButton("Cancel Analysis")
        self.cancel_analysis_button.clicked.connect(self._cancel_analysis); self.cancel_analysis_button.setEnabled(False)
        self.refresh_analysis_button = QPushButton("Refresh Analysis")
        self.refresh_analysis_button.clicked.connect(self._refresh_analysis)
        buttons = QHBoxLayout()
        for button in (new_button, save_button, delete_button): buttons.addWidget(button)
        for button in (self.analyze_selected_button, self.analyze_batch_button,
                       self.cancel_analysis_button, self.refresh_analysis_button): buttons.addWidget(button)
        buttons.addStretch()
        self.analysis_progress = QProgressBar(); self.analysis_progress.setRange(0, 100); self.analysis_progress.setValue(0)
        self.analysis_status = QLabel("Analysis ready")
        layout = QVBoxLayout(self); layout.addWidget(heading); layout.addWidget(description)
        layout.addLayout(buttons); layout.addWidget(self.analysis_progress); layout.addWidget(self.analysis_status)
        layout.addLayout(filters); layout.addWidget(splitter, 1)
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
            self._remember_visible_checks()
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
                    if column == 0:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Checked if record.evidence_id in self._checked_ids else Qt.CheckState.Unchecked)
                    self.table.setItem(row, column, item)
            self.table.blockSignals(False); self.table.resizeColumnsToContents()
            self._update_check_state()
            self.empty_message.setVisible(not records)
            filtered = bool(self.search_box.text() or self.status_filter.currentData() or self.type_filter.currentData()
                            or self.claim_filter.currentData() or self.unlinked_filter.isChecked() or self.ocr_filter.currentData())
            self.empty_message.setText("No evidence matches the current search and filters." if filtered
                                       else "No evidence has been added to this project yet.")
            self._reload_duplicate_options(self.duplicate_of.currentData())
            self.current_id = selected_id; self._select_current()
            self._refresh_analysis()
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
        self._refresh_analysis()
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
            self._refresh_analysis()
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
        ids = self._checked_evidence_ids()
        if not ids:
            QMessageBox.information(self, "Delete evidence", "Check one or more evidence records first."); return
        preview = "\n".join(f"• {self.manager.get(item).title}" for item in ids[:5])
        extra = f"\n…and {len(ids) - 5} more" if len(ids) > 5 else ""
        if QMessageBox.question(
            self, "Delete checked evidence",
            f"Delete {len(ids)} checked evidence record(s) and their links?\n\n{preview}{extra}\n\n"
            "Source documents and claims are preserved."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.delete_many(ids)
            self._checked_ids.difference_update(ids)
            if self.current_id in ids:
                self.current_id = None; self._saved_snapshot = None
            self.refresh()
        except Exception as exc: QMessageBox.critical(self, "Unable to delete evidence", str(exc))

    def _checked_evidence_ids(self) -> list[str]:
        self._remember_visible_checks()
        return sorted(self._checked_ids)

    def _remember_visible_checks(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item: continue
            identifier = str(item.data(Qt.ItemDataRole.UserRole))
            if item.checkState() == Qt.CheckState.Checked: self._checked_ids.add(identifier)
            else: self._checked_ids.discard(identifier)

    def _evidence_check_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0: return
        identifier = str(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState() == Qt.CheckState.Checked: self._checked_ids.add(identifier)
        else: self._checked_ids.discard(identifier)
        self._update_check_state()

    def _check_visible(self, state) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item: continue
            item.setCheckState(state)
            identifier = str(item.data(Qt.ItemDataRole.UserRole))
            if state == Qt.CheckState.Checked: self._checked_ids.add(identifier)
            else: self._checked_ids.discard(identifier)
        self.table.blockSignals(False)
        self._update_check_state()

    def _update_check_state(self) -> None:
        visible = [
            self.table.item(row, 0) for row in range(self.table.rowCount())
            if self.table.item(row, 0)
        ]
        checked = sum(item.checkState() == Qt.CheckState.Checked for item in visible)
        state = Qt.CheckState.Unchecked if checked == 0 else (
            Qt.CheckState.Checked if checked == len(visible) else Qt.CheckState.PartiallyChecked
        )
        self.check_header.setCheckState(state)
        self.checked_count.setText(f"{len(self._checked_ids)} checked")

    def _analyze_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "AI evidence analysis", "Select an evidence item first."); return
        evidence_id = str(self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole))
        self._start_analysis([evidence_id])

    def _analyze_checked_or_filtered(self) -> None:
        evidence_ids = self._checked_evidence_ids()
        if not evidence_ids:
            evidence_ids = [str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)) for row in range(self.table.rowCount())]
        if not evidence_ids:
            QMessageBox.information(self, "AI evidence analysis", "No evidence matches the current filters."); return
        self._start_analysis(evidence_ids)

    def _start_analysis(self, evidence_ids: list[str]) -> None:
        if self._analysis_thread is not None:
            QMessageBox.information(self, "AI evidence analysis", "Evidence analysis is already running."); return
        thread = QThread(self)
        worker = EvidenceAnalysisWorker(
            self.project, evidence_ids,
            service_factory=lambda project: EvidenceAnalysisService(project, settings_manager=self.settings_manager),
        )
        worker.moveToThread(thread); thread.started.connect(worker.run)
        worker.progress.connect(self._analysis_progress_changed)
        worker.analysis_updated.connect(lambda _analysis_id: self._refresh_analysis())
        worker.completed.connect(self._analysis_completed); worker.failed.connect(self._analysis_failed)
        worker.cancelled.connect(self._analysis_cancelled); worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._analysis_finished)
        self._analysis_thread = thread; self._analysis_worker = worker
        self.analyze_selected_button.setEnabled(False); self.analyze_batch_button.setEnabled(False)
        self.cancel_analysis_button.setEnabled(True); self.analysis_progress.setValue(0)
        self.analysis_status.setText(f"Preparing {len(evidence_ids)} evidence analysis request(s)…")
        thread.start()

    def _cancel_analysis(self) -> None:
        if self._analysis_worker:
            self.cancel_analysis_button.setEnabled(False); self.analysis_status.setText("Cancelling analysis…")
            self._analysis_worker.cancel()

    def _analysis_progress_changed(self, percent: int, message: str) -> None:
        self.analysis_progress.setValue(percent); self.analysis_status.setText(message)

    def _analysis_completed(self, completed: int, failed: int) -> None:
        self.analysis_progress.setValue(100)
        self.analysis_status.setText(f"Analysis complete: {completed} completed, {failed} failed")
        self._refresh_analysis()

    def _analysis_failed(self, message: str) -> None:
        self.analysis_status.setText(message); self._refresh_analysis()
        QMessageBox.warning(self, "AI evidence analysis", message)

    def _analysis_cancelled(self) -> None:
        self.analysis_status.setText("Evidence analysis cancelled"); self._refresh_analysis()

    def _analysis_finished(self) -> None:
        self._analysis_thread = None; self._analysis_worker = None
        self.analyze_selected_button.setEnabled(True); self.analyze_batch_button.setEnabled(True)
        self.cancel_analysis_button.setEnabled(False); self._refresh_analysis()

    def _refresh_analysis(self) -> None:
        selected = self.analysis_history.currentData() if hasattr(self, "analysis_history") else None
        self.analysis_history.blockSignals(True); self.analysis_history.clear()
        if not self.current_id:
            self.analysis_metadata.setText("Select an evidence item to view analysis history.")
            self.analysis_result.clear(); self.analysis_recommendations.clear()
            self.apply_recommendations_button.setEnabled(False); self.analysis_history.blockSignals(False); return
        history = self.analysis.history(self.current_id)
        for record in history:
            label = f"{record.created_at} — {record.status.title()} — {record.provider or 'provider pending'}"
            self.analysis_history.addItem(label, record.analysis_id)
        index = self.analysis_history.findData(selected)
        self.analysis_history.setCurrentIndex(index if index >= 0 else (0 if history else -1))
        self.analysis_history.blockSignals(False)
        self._show_history_record()

    def _show_history_record(self) -> None:
        analysis_id = self.analysis_history.currentData()
        if not analysis_id:
            self.analysis_metadata.setText("No analysis has been run for this evidence.")
            self.analysis_result.clear(); self.analysis_recommendations.clear()
            self.apply_recommendations_button.setEnabled(False); return
        record = self.analysis.get(str(analysis_id)); redaction = "Applied" if record.redaction_applied else "Not applied"
        self.analysis_metadata.setText(
            f"Status: {record.status.title()} · Provider: {record.provider or '—'} · Model: {record.model or '—'} · "
            f"Date: {record.completed_at or record.created_at} · Redaction: {redaction} · "
            f"Confidence: {record.result.confidence.title() if record.result else '—'}"
        )
        if record.result:
            self.analysis_result.setPlainText(self._format_analysis(record))
        else:
            self.analysis_result.setPlainText(record.error_message or "Analysis is pending.")
        self.analysis_recommendations.clear()
        if record.result:
            for recommendation in record.result.recommended_claim_associations:
                item = QListWidgetItem(
                    f"{recommendation['claim_name']}: {recommendation['reason']}"
                ); item.setData(Qt.ItemDataRole.UserRole, recommendation["claim_id"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Unchecked)
                self.analysis_recommendations.addItem(item)
        self.apply_recommendations_button.setEnabled(self.analysis_recommendations.count() > 0)

    @staticmethod
    def _format_analysis(record: EvidenceAnalysisRecord) -> str:
        result = record.result
        if not result: return record.error_message
        labels = (
            ("Summary", [result.summary]), ("Diagnoses or conditions", result.diagnoses_or_conditions),
            ("Symptoms and functional limitations", result.symptoms_and_functional_limitations),
            ("Treatment, testing, and medications", result.treatment_testing_medications),
            ("Dates and providers", result.dates_and_providers),
            ("Possible in-service events or exposures", result.in_service_events_or_exposures),
            ("Possible nexus-supporting statements", result.nexus_supporting_statements),
            ("Possible aggravation evidence", result.aggravation_evidence),
            ("Possible secondary-service-connection evidence", result.secondary_service_connection_evidence),
            ("Favorable evidence", result.favorable_evidence),
            ("Unfavorable or contradictory evidence", result.unfavorable_or_contradictory_evidence),
            ("Missing information or clarification needs", result.missing_information_or_clarification_needs),
        )
        sections = []
        for title, values in labels:
            sections.append(title + "\n" + ("\n".join(f"• {value}" for value in values) if values else "• None identified"))
        return "\n\n".join(sections)

    def _apply_recommendations(self) -> None:
        claim_ids = [str(self.analysis_recommendations.item(i).data(Qt.ItemDataRole.UserRole))
                     for i in range(self.analysis_recommendations.count())
                     if self.analysis_recommendations.item(i).checkState() == Qt.CheckState.Checked]
        if not claim_ids or not self.current_id:
            QMessageBox.information(self, "Claim associations", "Check one or more recommendations first."); return
        if QMessageBox.question(self, "Confirm claim associations",
                                f"Link this evidence to {len(claim_ids)} reviewed recommended claim(s)?") != QMessageBox.StandardButton.Yes:
            return
        existing = {link.claim_id for link in self.manager.claim_links_for_evidence(self.current_id)}
        for claim_id in claim_ids:
            if claim_id not in existing:
                self.manager.link_claim(self.current_id, claim_id)
        linked = {link.claim_id for link in self.manager.claim_links_for_evidence(self.current_id)}
        for index in range(self.claim_links.count()):
            item = self.claim_links.item(index)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in linked else Qt.CheckState.Unchecked)
        self._capture_snapshot(); self.refresh()
