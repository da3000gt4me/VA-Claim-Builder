from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QTabWidget

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


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectInfo) -> None:
        super().__init__()
        self.project = project
        self.setWindowTitle(f"VA Claim Builder 4.2 — {project.name}")
        self.resize(1180, 760)

        self.tabs = QTabWidget()
        self.documents_page = DocumentsPage(project)
        self.ocr_page = OCRPage(project)
        self.claims_page = ClaimsPage(project)
        self.evidence_page = EvidencePage(project)
        self.timeline_page = TimelinePage(project)
        self.nexus_page = NexusPage(project)
        self.dbq_page = DBQPage(project)
        self.rating_strategy_page = RatingStrategyPage(project)
        self.optimizer_page = OptimizerPage(project)
        self.submission_page = SubmissionPage(project)
        self.settings_page = SettingsPage()
        self.settings_page.settings_saved.connect(
            lambda: self.statusBar().showMessage("AI settings saved", 3000)
        )
        self.tabs.addTab(self.documents_page, "Documents")
        self.tabs.addTab(self.ocr_page, "OCR & Text")
        self.tabs.addTab(self.claims_page, "Claims")
        self.tabs.addTab(self.evidence_page, "Evidence")
        self.tabs.addTab(self.timeline_page, "Medical Timeline")
        self.tabs.addTab(self.nexus_page, "Nexus Letters")
        self.tabs.addTab(self.dbq_page, "DBQ Assistant")
        self.tabs.addTab(self.rating_strategy_page, "Rating Strategy")
        self.tabs.addTab(self.optimizer_page, "Claim Optimizer")
        self.tabs.addTab(self.submission_page, "Submission Builder")
        self.tabs.addTab(self.settings_page, "Settings")
        self.setCentralWidget(self.tabs)

        project_menu = self.menuBar().addMenu("Project")
        refresh_action = QAction("Refresh Workspace", self)
        refresh_action.triggered.connect(self._refresh_workspace)
        project_menu.addAction(refresh_action)

        project_info_action = QAction("Project Information", self)
        project_info_action.triggered.connect(self._show_project_information)
        project_menu.addAction(project_info_action)

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

        status = QStatusBar()
        status.showMessage(f"Project loaded: {project.name}")
        self.setStatusBar(status)

    def _refresh_workspace(self) -> None:
        self.documents_page.refresh()
        self.ocr_page.refresh()
        self.claims_page.refresh()
        self.evidence_page.refresh()
        self.timeline_page.refresh()
        self.nexus_page.refresh()
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
