
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStatusBar, QTabWidget

from core.projects import ProjectInfo
from ui_qt.claims_page import ClaimsPage
from ui_qt.documents_page import DocumentsPage
from ui_qt.evidence_page import EvidencePage
from ui_qt.ocr_page import OCRPage
from ui_qt.settings_page import SettingsPage
from ui_qt.timeline_page import TimelinePage
from ui_qt.nexus_page import NexusPage
from ui_qt.dbq_page import DBQPage
from ui_qt.rating_strategy_page import RatingStrategyPage
from ui_qt.optimizer_page import OptimizerPage
from ui_qt.submission_page import SubmissionPage
from ui_qt.statements_page import StatementsPage
from ui_qt.intake_review_page import IntakeReviewPage
from core.version import FULL_NAME
from core.maintenance import MaintenanceError, ProjectMaintenance
from core.jobs import JobManager
from core.resources import documentation_path


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectInfo) -> None:
        super().__init__()
        self.project = project
        self.maintenance = ProjectMaintenance(project)
        self.setWindowTitle(f"{FULL_NAME} — {project.name}")
        self.resize(1180, 760)

        self.tabs = QTabWidget()
        self.documents_page = DocumentsPage(project)
        self.intake_review_page = IntakeReviewPage(project)
        self.ocr_page = OCRPage(project)
        self.claims_page = ClaimsPage(project)
        self.evidence_page = EvidencePage(project)
        self.timeline_page = TimelinePage(project)
        self.nexus_page = NexusPage(project)
        self.dbq_page = DBQPage(project)
        self.rating_strategy_page = RatingStrategyPage(project)
        self.optimizer_page = OptimizerPage(project)
        self.submission_page = SubmissionPage(project)
        self.statements_page = StatementsPage(project)
        self.settings_page = SettingsPage()
        self.settings_page.settings_saved.connect(
            lambda: self.statusBar().showMessage("AI settings saved", 3000)
        )
        self.tabs.addTab(self.documents_page, "Documents")
        self.tabs.addTab(self.intake_review_page, "Automation Review")
        self.tabs.addTab(self.ocr_page, "OCR & Text")
        self.tabs.addTab(self.claims_page, "Claims")
        self.tabs.addTab(self.evidence_page, "Evidence")
        self.tabs.addTab(self.timeline_page, "Medical Timeline")
        self.tabs.addTab(self.nexus_page, "Nexus Letters")
        self.tabs.addTab(self.statements_page, "Buddy / Witness")
        self.tabs.addTab(self.dbq_page, "DBQ Assistant")
        self.tabs.addTab(self.rating_strategy_page, "Rating Strategy")
        self.tabs.addTab(self.optimizer_page, "Claim Optimizer")
        self.tabs.addTab(self.submission_page, "Submission Builder")
        self.tabs.addTab(self.settings_page, "Settings")
        self.setCentralWidget(self.tabs)
        self.documents_page.automation_finished.connect(self._refresh_workspace)
        self.intake_review_page.automation_finished.connect(self._refresh_workspace)

        project_menu = self.menuBar().addMenu("Project")
        refresh_action = QAction("Refresh Workspace", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh_workspace)
        project_menu.addAction(refresh_action)

        project_info_action = QAction("Project Information", self)
        project_info_action.triggered.connect(self._show_project_information)
        project_menu.addAction(project_info_action)
        project_menu.addSeparator()
        backup_action = QAction("Create Backup…", self)
        backup_action.setShortcut("Ctrl+B")
        backup_action.triggered.connect(self._create_backup)
        project_menu.addAction(backup_action)
        restore_action = QAction("Restore Backup…", self)
        restore_action.triggered.connect(self._restore_backup)
        project_menu.addAction(restore_action)
        validate_action = QAction("Validate and Repair Project…", self)
        validate_action.triggered.connect(self._validate_project)
        project_menu.addAction(validate_action)
        diagnostics_action = QAction("Export Diagnostic Bundle…", self)
        diagnostics_action.triggered.connect(self._export_diagnostics)
        project_menu.addAction(diagnostics_action)

        claims_menu = self.menuBar().addMenu("Claims")
        claims_action = QAction("Open Claims Workspace", self)
        claims_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.claims_page))
        claims_menu.addAction(claims_action)

        evidence_menu = self.menuBar().addMenu("Evidence")
        evidence_action = QAction("Open Evidence Workspace", self)
        evidence_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.evidence_page))
        evidence_menu.addAction(evidence_action)
        timeline_menu = self.menuBar().addMenu("Timeline")
        timeline_action = QAction("Open Medical Timeline", self)
        timeline_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.timeline_page))
        timeline_menu.addAction(timeline_action)
        nexus_menu = self.menuBar().addMenu("Nexus Letters")
        nexus_action = QAction("Open Nexus Letters", self)
        nexus_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.nexus_page))
        nexus_menu.addAction(nexus_action)
        statements_action = QAction("Open Buddy / Witness Statements", self)
        statements_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.statements_page))
        nexus_menu.addAction(statements_action)
        dbq_menu = self.menuBar().addMenu("DBQ Assistant")
        dbq_action = QAction("Open DBQ Assistant", self)
        dbq_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.dbq_page))
        dbq_menu.addAction(dbq_action)
        rating_menu = self.menuBar().addMenu("Rating Strategy")
        rating_action = QAction("Open Rating Strategy", self)
        rating_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.rating_strategy_page))
        rating_menu.addAction(rating_action)
        optimizer_menu = self.menuBar().addMenu("Claim Optimizer")
        optimizer_action = QAction("Open Claim Optimizer", self)
        optimizer_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.optimizer_page))
        optimizer_menu.addAction(optimizer_action)
        submission_menu = self.menuBar().addMenu("Submission Builder")
        submission_action = QAction("Open Submission Builder", self)
        submission_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.submission_page))
        submission_menu.addAction(submission_action)

        settings_menu = self.menuBar().addMenu("Settings")
        ai_settings_action = QAction("AI & Privacy Settings", self)
        ai_settings_action.triggered.connect(
            lambda: self.tabs.setCurrentWidget(self.settings_page)
        )
        settings_menu.addAction(ai_settings_action)

        help_menu = self.menuBar().addMenu("Help")
        privacy_action = QAction("Privacy Summary", self)
        privacy_action.triggered.connect(self._show_privacy)
        help_menu.addAction(privacy_action)
        guide_action = QAction("User Guide", self)
        guide_action.setShortcut("F1")
        guide_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(documentation_path())))
        )
        help_menu.addAction(guide_action)
        about_action = QAction("About", self)
        about_action.triggered.connect(
            lambda: QMessageBox.about(self, "About VA Claim Builder", f"{FULL_NAME}\nRelease Candidate software for local testing.")
        )
        help_menu.addAction(about_action)

        status = QStatusBar()
        status.showMessage(f"Project loaded: {project.name}")
        self.setStatusBar(status)

    def _refresh_workspace(self) -> None:
        self.documents_page.refresh()
        self.intake_review_page.refresh()
        self.ocr_page.refresh()
        self.claims_page.refresh()
        self.evidence_page.refresh()
        self.timeline_page.refresh()
        self.nexus_page.refresh()
        self.statements_page.refresh()
        self.dbq_page.refresh()
        self.rating_strategy_page.refresh()
        self.optimizer_page.refresh()
        self.submission_page.refresh()
        self.settings_page.load()
        self.statusBar().showMessage("Workspace refreshed", 3000)

    def _show_project_information(self) -> None:
        QMessageBox.information(
            self,
            "Project Information",
            (
                f"Name: {self.project.name}\n"
                f"Project ID: {self.project.project_id}\n"
                f"Location: {self.project.root}\n"
                f"Created: {self.project.created_at}"
            ),
        )

    def _create_backup(self) -> None:
        destination = QFileDialog.getExistingDirectory(self, "Choose Backup Folder")
        if not destination:
            return
        try:
            path = self.maintenance.create_backup(destination)
            QMessageBox.information(self, "Backup Complete", f"Validated backup created at:\n{path}")
        except MaintenanceError as exc:
            QMessageBox.critical(self, "Backup Failed", f"The project was not changed.\n\n{exc}")

    def _restore_backup(self) -> None:
        archive, _ = QFileDialog.getOpenFileName(self, "Choose Backup", filter="VA Claim Builder Backup (*.vcbbackup.zip *.zip)")
        if not archive:
            return
        destination = QFileDialog.getExistingDirectory(self, "Choose Parent Folder for Restored Project")
        if not destination:
            return
        try:
            preview = self.maintenance.restore_preview(archive)
            target = str(__import__("pathlib").Path(destination) / f"{preview['project_name']}-restored")
            if QMessageBox.question(self, "Restore Backup", f"Restore {preview['file_count']} files into:\n{target}?") != QMessageBox.Yes:
                return
            restored = self.maintenance.restore(archive, target)
            QMessageBox.information(self, "Restore Complete", f"Restored project: {restored.root}\nOpen it from the welcome screen.")
        except MaintenanceError as exc:
            QMessageBox.critical(self, "Restore Failed", f"No existing project was overwritten.\n\n{exc}")

    def _validate_project(self) -> None:
        issues = self.maintenance.validate_project()
        if not issues:
            QMessageBox.information(self, "Project Validation", "No integrity problems were found.")
            return
        details = "\n".join(f"[{item['level'].upper()}] {item['message']}" for item in issues)
        repairable = any(item.get("repairable") for item in issues)
        if repairable and QMessageBox.question(self, "Project Validation", details + "\n\nApply safe repairs?") == QMessageBox.Yes:
            actions = self.maintenance.repair_safe()
            QMessageBox.information(self, "Repair Complete", "\n".join(actions) or "No repairs were needed.")
        else:
            QMessageBox.warning(self, "Project Validation", details)

    def _export_diagnostics(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(self, "Export Diagnostic Bundle", "va-claim-builder-diagnostics.json", "JSON (*.json)")
        if destination:
            path = self.maintenance.export_diagnostics(destination)
            QMessageBox.information(self, "Diagnostics Exported", f"Sanitized diagnostics saved to:\n{path}")

    def _show_privacy(self) -> None:
        QMessageBox.information(self, "Privacy Summary", "Projects, logs, backups, and temporary files remain local. Cloud AI is used only when configured; Local-only mode prevents cloud calls. Redaction reduces identifiers but cannot guarantee anonymity. Diagnostics exclude evidence text and credentials.")

    def closeEvent(self, event) -> None:
        active = [job for job in JobManager(self.project).list(limit=200) if job.status in {"queued", "running", "cancelling"}]
        if active and QMessageBox.question(self, "Active Work", f"{len(active)} background job(s) are active. Cancel safely and close?") != QMessageBox.Yes:
            event.ignore()
            return
        for page in (self.intake_review_page, self.ocr_page, self.evidence_page, self.timeline_page, self.nexus_page, self.dbq_page, self.rating_strategy_page, self.optimizer_page, self.submission_page):
            worker = getattr(page, "worker", None)
            if worker is not None and hasattr(worker, "cancel"):
                worker.cancel()
        JobManager(self.project).recover_interrupted()
        event.accept()
