from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QTabWidget

from core.projects import ProjectInfo
from ui_qt.claims_page import ClaimsPage
from ui_qt.documents_page import DocumentsPage
from ui_qt.ocr_page import OCRPage
from ui_qt.settings_page import SettingsPage


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
        self.settings_page = SettingsPage()
        self.settings_page.settings_saved.connect(
            lambda: self.statusBar().showMessage("AI settings saved", 3000)
        )
        self.tabs.addTab(self.documents_page, "Documents")
        self.tabs.addTab(self.ocr_page, "OCR & Text")
        self.tabs.addTab(self.claims_page, "Claims")
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
