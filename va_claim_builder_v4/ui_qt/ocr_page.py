from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from core.documents import DocumentManager
from core.ocr import OCRManager
from core.projects import ProjectInfo

from .checked_table import CheckableHeader


class OCRWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: OCRManager, document_ids: list[str], force_ocr: bool = False) -> None:
        super().__init__()
        self.manager = manager
        self.document_ids = document_ids
        self.force_ocr = force_ocr
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            total = max(len(self.document_ids), 1)
            for index, document_id in enumerate(self.document_ids):
                if self._cancelled:
                    raise InterruptedError("OCR cancelled")
                self.manager.process(
                    document_id,
                    progress=lambda percent, message, i=index: self.progress.emit(
                        int(((i + percent / 100) / total) * 100), message
                    ),
                    cancelled=lambda: self._cancelled,
                    force_ocr=self.force_ocr,
                )
            self.completed.emit(f"Processed {len(self.document_ids)} document(s).")
        except InterruptedError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class OCRPage(QWidget):
    def __init__(self, project: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.documents = DocumentManager(project)
        self.ocr = OCRManager(project)
        self.worker: OCRWorker | None = None
        self._checked_ids: set[str] = set()
        self._current_document: str | None = None

        heading = QLabel("OCR & Text Extraction")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "Native PDF text is evaluated first. Low-quality or image-only pages use local "
            "Tesseract OCR and remain visible for page-level review."
        )
        description.setWordWrap(True)

        self.run_button = QPushButton("Process Checked")
        self.run_button.clicked.connect(lambda: self._run_checked(False))
        self.reprocess_button = QPushButton("Reprocess Checked with OCR")
        self.reprocess_button.clicked.connect(lambda: self._run_checked(True))
        self.delete_button = QPushButton("Delete Checked OCR Outputs")
        self.delete_button.clicked.connect(self._delete_checked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        controls = QHBoxLayout()
        for control in (
            self.run_button, self.reprocess_button, self.delete_button,
            self.cancel_button, self.refresh_button,
        ):
            controls.addWidget(control)
        controls.addStretch()

        self.progress = QProgressBar()
        self.status = QLabel("Ready")
        self.checked_count = QLabel("0 checked")
        self.table = QTableWidget(0, 6)
        self.check_header = CheckableHeader(self.table)
        self.table.setHorizontalHeader(self.check_header)
        self.table.setHorizontalHeaderLabels(
            ["Document", "Source Status", "Method", "Pages", "Characters", "Review"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_document)
        self.table.itemChanged.connect(self._check_changed)
        self.check_header.toggled.connect(self._check_visible)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.page_selector = QComboBox()
        self.page_selector.currentIndexChanged.connect(self._load_page)
        self.page_state = QLabel("No page selected")
        self.page_method = QLabel("—")
        self.page_confidence = QLabel("—")
        self.failure_reason = QLabel("")
        self.failure_reason.setWordWrap(True)
        page_form = QFormLayout()
        page_form.addRow("Page", self.page_selector)
        page_form.addRow("State", self.page_state)
        page_form.addRow("Method", self.page_method)
        page_form.addRow("Quality", self.page_confidence)
        page_form.addRow("Failure / review reason", self.failure_reason)
        self.raw_text = QTextEdit(); self.raw_text.setReadOnly(True)
        self.normalized_text = QTextEdit(); self.normalized_text.setReadOnly(True)
        self.corrected_text = QTextEdit()
        text_tabs = QTabWidget()
        for widget, name in (
            (self.raw_text, "Raw"), (self.normalized_text, "Normalized"),
            (self.corrected_text, "Corrected"),
        ):
            text_tabs.addTab(widget, name)
        self.rotation = QSpinBox(); self.rotation.setRange(0, 270); self.rotation.setSingleStep(90)
        retry = QPushButton("Rotate and Retry Page"); retry.clicked.connect(self._retry_page)
        save = QPushButton("Save Correction / Mark Readable"); save.clicked.connect(self._save_correction)
        unreadable = QPushButton("Mark Unreadable"); unreadable.clicked.connect(
            lambda: self._save_correction("unreadable")
        )
        revert = QPushButton("Revert Correction"); revert.clicked.connect(self._revert_correction)
        page_actions = QHBoxLayout()
        page_actions.addWidget(QLabel("Rotation")); page_actions.addWidget(self.rotation)
        for control in (retry, save, unreadable, revert): page_actions.addWidget(control)
        page_actions.addStretch()
        right = QWidget(); right_layout = QVBoxLayout(right)
        right_layout.addLayout(page_form); right_layout.addWidget(text_tabs, 1); right_layout.addLayout(page_actions)
        left = QWidget(); left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.checked_count); left_layout.addWidget(self.table, 1)
        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(right)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(heading); layout.addWidget(description); layout.addLayout(controls)
        layout.addWidget(self.progress); layout.addWidget(self.status); layout.addWidget(splitter, 1)
        self.refresh()

    def refresh(self) -> None:
        self._remember_checks()
        documents = self.documents.list_documents()
        results = {result.document_id: result for result in self.ocr.list_results()}
        self.table.blockSignals(True)
        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            result = results.get(document.document_id)
            pages = self.ocr.list_pages(document.document_id) if result else []
            review = sum(page.state in {"partial_text", "unreadable_after_retry", "user_review_required"} for page in pages)
            values = (
                document.original_name, document.status.replace("_", " ").title(),
                result.method if result else "Not processed",
                str(result.page_count) if result else "—",
                str(result.character_count) if result else "—",
                f"{review} page(s)" if review else "Ready",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, document.document_id)
                if column == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked if document.document_id in self._checked_ids
                        else Qt.CheckState.Unchecked
                    )
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self._update_check_state()
        if self._current_document:
            self._select_document(self._current_document)

    def checked_document_ids(self) -> list[str]:
        self._remember_checks()
        return sorted(self._checked_ids)

    def _run_checked(self, force_ocr: bool) -> None:
        ids = self.checked_document_ids()
        if not ids:
            QMessageBox.information(self, "OCR", "Check one or more documents first."); return
        self.worker = OCRWorker(self.ocr, ids, force_ocr)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self._set_running(True); self.progress.setValue(0); self.worker.start()

    def _delete_checked(self) -> None:
        ids = self.checked_document_ids()
        if not ids:
            QMessageBox.information(self, "Delete OCR outputs", "Check one or more documents first."); return
        if QMessageBox.question(
            self, "Delete checked OCR outputs",
            f"Delete OCR output for {len(ids)} checked document(s)? Source documents are preserved."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.ocr.delete_outputs(ids)
            self._checked_ids.difference_update(ids)
            self.status.setText(f"Deleted {count} OCR output(s); source documents were preserved.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Unable to delete OCR output", str(exc))

    def _load_document(self) -> None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0): return
        self._current_document = str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        self.page_selector.blockSignals(True); self.page_selector.clear()
        for page in self.ocr.list_pages(self._current_document):
            self.page_selector.addItem(f"Page {page.page_number}", page.page_number)
        self.page_selector.blockSignals(False)
        if self.page_selector.count():
            self.page_selector.setCurrentIndex(0); self._load_page()
        else:
            self._clear_page()

    def _load_page(self) -> None:
        if not self._current_document or self.page_selector.currentData() is None:
            self._clear_page(); return
        page = self.ocr.get_page(self._current_document, int(self.page_selector.currentData()))
        self.page_state.setText(page.state.replace("_", " ").title())
        self.page_method.setText(page.extraction_method)
        self.page_confidence.setText(f"{page.confidence:.1%}")
        self.failure_reason.setText(page.failure_reason or "; ".join(page.quality.get("reasons", [])) or "None")
        self.raw_text.setPlainText(page.raw_text); self.normalized_text.setPlainText(page.normalized_text)
        self.corrected_text.setPlainText(page.corrected_text or page.normalized_text)
        self.rotation.setValue(page.rotation)

    def _save_correction(self, readability: str = "readable") -> None:
        if not self._current_document or self.page_selector.currentData() is None: return
        self.ocr.save_correction(
            self._current_document, int(self.page_selector.currentData()),
            self.corrected_text.toPlainText(), readability=readability,
        )
        self._load_page(); self.refresh()

    def _revert_correction(self) -> None:
        if not self._current_document or self.page_selector.currentData() is None: return
        self.ocr.revert_correction(self._current_document, int(self.page_selector.currentData()))
        self._load_page()

    def _retry_page(self) -> None:
        if not self._current_document or self.page_selector.currentData() is None: return
        try:
            self.ocr.retry_page(
                self._current_document, int(self.page_selector.currentData()),
                rotation=self.rotation.value(),
            )
            self._load_page(); self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Page OCR retry failed", str(exc))

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel(); self.status.setText("Cancelling after the current page…")

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, percent))); self.status.setText(message)

    def _on_completed(self, message: str) -> None:
        self.progress.setValue(100); self.status.setText(message); self._finish()

    def _on_failed(self, message: str) -> None:
        self.status.setText(message)
        if message != "OCR cancelled": QMessageBox.critical(self, "OCR failed", message)
        self._finish()

    def _finish(self) -> None:
        self._set_running(False); self.refresh(); self.worker = None

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running); self.reprocess_button.setEnabled(not running)
        self.delete_button.setEnabled(not running); self.cancel_button.setEnabled(running)

    def _remember_checks(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item: continue
            identifier = str(item.data(Qt.ItemDataRole.UserRole))
            if item.checkState() == Qt.CheckState.Checked: self._checked_ids.add(identifier)
            else: self._checked_ids.discard(identifier)

    def _check_changed(self, item) -> None:
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
        self.table.blockSignals(False); self._update_check_state()

    def _update_check_state(self) -> None:
        visible = [self.table.item(row, 0) for row in range(self.table.rowCount()) if self.table.item(row, 0)]
        checked = sum(item.checkState() == Qt.CheckState.Checked for item in visible)
        state = Qt.CheckState.Unchecked if not checked else (
            Qt.CheckState.Checked if checked == len(visible) else Qt.CheckState.PartiallyChecked
        )
        self.check_header.setCheckState(state); self.checked_count.setText(f"{len(self._checked_ids)} checked")

    def _select_document(self, document_id: str) -> None:
        for row in range(self.table.rowCount()):
            if str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)) == document_id:
                self.table.selectRow(row); return

    def _clear_page(self) -> None:
        self.page_state.setText("No extracted pages"); self.page_method.setText("—")
        self.page_confidence.setText("—"); self.failure_reason.clear()
        self.raw_text.clear(); self.normalized_text.clear(); self.corrected_text.clear()
