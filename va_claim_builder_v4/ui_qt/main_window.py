from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QTabWidget

from core.projects import ProjectInfo
from ui_qt.documents_page import DocumentsPage


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectInfo) -> None:
        super().__init__()
        self.project = project
        self.setWindowTitle(f"VA Claim Builder 4.2 — {project.name}")
        self.resize(1180, 760)

        self.tabs = QTabWidget()
        self.documents_page = DocumentsPage(project)
        self.tabs.addTab(self.documents_page, "Documents")
        self.setCentralWidget(self.tabs)

        project_menu = self.menuBar().addMenu("Project")
        refresh_action = QAction("Refresh Documents", self)
        refresh_action.triggered.connect(self.documents_page.refresh)
        project_menu.addAction(refresh_action)

        project_info_action = QAction("Project Information", self)
        project_info_action.triggered.connect(self._show_project_information)
        project_menu.addAction(project_info_action)

        status = QStatusBar()
        status.showMessage(f"Project loaded: {project.name}")
        self.setStatusBar(status)

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
