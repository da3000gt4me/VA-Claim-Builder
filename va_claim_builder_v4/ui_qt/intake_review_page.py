
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from core.documents import DocumentManager
from core.intake import IntakeManager
from core.projects import ProjectInfo
from ui_qt.progress_panel import ProgressPanel
from workers import AutomatedIntakeWorker


class IntakeReviewPage(QWidget):
    automation_finished = Signal()

    def __init__(self, project: ProjectInfo, parent=None):
        super().__init__(parent)
        self.project = project
        self.intake = IntakeManager(project)
        self.documents = DocumentManager(project)
        self.intake.recover_interrupted()
        self._thread = None; self.worker = None

        heading = QLabel("Automation Review Center")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        guidance = QLabel(
            "Automatic intake creates local draft evidence, timeline events, claim matches, and suggestions. "
            "Nothing here is a confirmed medical fact or nexus opinion until you review it."
        )
        guidance.setWordWrap(True)
        self.analyze_unprocessed = QPushButton("Analyze All Unprocessed")
        self.analyze_failed = QPushButton("Reanalyze Failed")
        self.resume = QPushButton("Resume Interrupted")
        self.reanalyze = QPushButton("Reanalyze Selected Documents")
        self.analyze_unprocessed.clicked.connect(lambda: self._run(self._document_ids({"imported", "queued", "needs reanalysis", "stale"})))
        self.analyze_failed.clicked.connect(lambda: self._run(self._document_ids({"failed"}), force=True))
        self.resume.clicked.connect(lambda: self._run(self._document_ids({"needs reanalysis"}), force=True))
        self.reanalyze.clicked.connect(lambda: self._run(self._selected_document_ids(), force=True))
        buttons = QHBoxLayout()
        for button in (self.analyze_unprocessed, self.analyze_failed, self.resume, self.reanalyze):
            buttons.addWidget(button)
        buttons.addStretch()
        self.progress = ProgressPanel()
        self.progress.cancel_button.clicked.connect(self._cancel)
        self.summary = QLabel()

        self.queue = QTableWidget(0, 6)
        self.queue.setHorizontalHeaderLabels(["Document", "Stage", "Progress", "Method", "Warnings", "Failure"])
        self.queue.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.suggestions = QTableWidget(0, 5)
        self.suggestions.setHorizontalHeaderLabels(["Type", "Title", "Confidence", "Status", "Source"])
        self.suggestions.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accept = QPushButton("Accept Selected")
        self.reject = QPushButton("Reject Selected")
        self.defer = QPushButton("Defer Selected")
        self.not_related = QPushButton("Mark Not Claim-Related")
        self.export = QPushButton("Export Review Report")
        self.accept.clicked.connect(lambda: self._decide("accepted"))
        self.reject.clicked.connect(lambda: self._decide("rejected"))
        self.defer.clicked.connect(lambda: self._decide("deferred"))
        self.not_related.clicked.connect(lambda: self._decide("not_claim_related"))
        self.export.clicked.connect(self._export)
        actions = QHBoxLayout()
        for button in (self.accept, self.reject, self.defer, self.not_related, self.export):
            actions.addWidget(button)
        actions.addStretch()
        suggestion_tab = QWidget(); suggestion_layout = QVBoxLayout(suggestion_tab)
        suggestion_layout.addLayout(actions); suggestion_layout.addWidget(self.suggestions)
        tabs = QTabWidget(); tabs.addTab(self.queue, "Processing Queue"); tabs.addTab(suggestion_tab, "Review Items")
        layout = QVBoxLayout(self)
        layout.addWidget(heading); layout.addWidget(guidance); layout.addLayout(buttons)
        layout.addWidget(self.progress); layout.addWidget(self.summary); layout.addWidget(tabs, 1)
        self.refresh()

    def refresh(self):
        states = self.intake.list_states()
        docs = {item.document_id: item for item in self.documents.list_documents()}
        self.queue.setRowCount(len(states))
        for row, state in enumerate(states):
            document = docs.get(state.document_id)
            values = [document.original_name if document else state.document_id, state.stage, f"{state.progress}%",
                      state.method, str(state.warning_count), state.failure_reason]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole, state.document_id)
                self.queue.setItem(row, column, item)
        suggestions = self.intake.list_suggestions()
        self.suggestions.setRowCount(len(suggestions))
        for row, suggestion in enumerate(suggestions):
            document = docs.get(suggestion.document_id)
            values = [suggestion.suggestion_type, suggestion.title, f"{suggestion.confidence:.0%}",
                      suggestion.status, document.original_name if document else suggestion.document_id]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole, suggestion.suggestion_id)
                item.setToolTip(json.dumps(suggestion.payload, indent=2))
                self.suggestions.setItem(row, column, item)
        pending = sum(item.status == "pending" for item in suggestions)
        failed = sum(item.stage == "failed" for item in states)
        self.summary.setText(f"{pending} item(s) awaiting review · {failed} failed document(s)")
        self.queue.resizeColumnsToContents(); self.suggestions.resizeColumnsToContents()

    def _document_ids(self, stages):
        known = {state.document_id: state.stage for state in self.intake.list_states()}
        return [doc.document_id for doc in self.documents.list_documents() if known.get(doc.document_id, "imported") in stages]

    def _selected_document_ids(self):
        return list({self.queue.item(index.row(), 0).data(Qt.ItemDataRole.UserRole) for index in self.queue.selectionModel().selectedRows()})

    def _run(self, document_ids, force=False):
        if not document_ids:
            QMessageBox.information(self, "Automatic intake", "No matching documents require analysis.")
            return
        if self._thread:
            return
        self.progress.start(f"Analyzing {len(document_ids)} document(s)…")
        thread = QThread(self); worker = AutomatedIntakeWorker(self.project, document_ids, force=force)
        worker.moveToThread(thread); thread.started.connect(worker.run)
        worker.progress.connect(self.progress.update_progress)
        worker.completed.connect(self._completed); worker.failed.connect(self._failed)
        worker.cancelled.connect(lambda: self.progress.finish("Analysis cancelled; partial valid results were preserved."))
        worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater); thread.finished.connect(self._finished)
        self._thread=thread; self.worker=worker; thread.start()

    def _cancel(self):
        if self.worker: self.worker.cancel()

    def _completed(self, summary):
        self.progress.finish(
            f"Processed {summary.documents_processed}; evidence {summary.evidence_created}; "
            f"timeline {summary.timeline_events_created}; claim suggestions {summary.claim_suggestions_created}."
        )
        self.refresh(); self.automation_finished.emit()

    def _failed(self, message):
        self.progress.finish("Analysis failed")
        QMessageBox.critical(self, "Automatic intake failed", message)

    def _finished(self):
        self._thread=None; self.worker=None; self.refresh()

    def _decide(self, status):
        ids = {self.suggestions.item(index.row(), 0).data(Qt.ItemDataRole.UserRole) for index in self.suggestions.selectionModel().selectedRows()}
        for suggestion_id in ids: self.intake.decide(str(suggestion_id), status)
        self.refresh(); self.automation_finished.emit()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Intake Review", "intake-review.json", "JSON (*.json)")
        if path:
            payload = {
                "processing": [state.__dict__ if hasattr(state, "__dict__") else {field: getattr(state, field) for field in state.__slots__} for state in self.intake.list_states()],
                "suggestions": [{"type": item.suggestion_type, "status": item.status, "title": item.title,
                                 "confidence": item.confidence, "payload": item.payload} for item in self.intake.list_suggestions()],
            }
            from pathlib import Path
            Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
