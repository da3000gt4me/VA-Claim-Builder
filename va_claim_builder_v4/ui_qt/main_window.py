from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QTabWidget

from core.projects import ProjectInfo
from ui_qt.documents_page import DocumentsPage
from ui_qt.ocr_page import OCRPage


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectInfo) -> None:
        super().__init__()
        self.project = project
        self.setWindowTitle(f"VA Claim Builder 4.2 — {project.name}")
        self.resize(1180, 760)

        self.tabs = QTabWidget()
        self.documents_page = DocumentsPage(project)
        self.ocr_page = OCRPage(project)
        self.tabs.addTab(self.documents_page, "Documents")
        self.tabs.addTab(self.ocr_page, "OCR & Text")
        self.setCentralWidget(self.tabs)

        project_menu = self.menuBar().addMenu("Project")
        refresh_action = QAction("Refresh Workspace", self)
        refresh_action.triggered.connect(self._refresh_workspace)
        project_menu.addAction(refresh_action)

        project_info_action = QAction("Project Information", self)
        project_info_action.triggered.connect(self._show_project_information)
        project_menu.addAction(project_info_action)

        status = QStatusBar()
        status.showMessage(f"Project loaded: {project.name}")
        self.setStatusBar(status)

    def _refresh_workspace(self) -> None:
        self.documents_page.refresh()
        self.ocr_page.refresh()
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
