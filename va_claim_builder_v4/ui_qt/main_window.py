from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar, QVBoxLayout, QWidget

from core.projects import ProjectInfo


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectInfo) -> None:
        super().__init__()
        self.project = project
        self.setWindowTitle(f"VA Claim Builder 4.2 — {project.name}")
        self.resize(1180, 760)

        title = QLabel("VA Claim Builder 4.2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 26px; font-weight: 600;")
        project_label = QLabel(f"Persistent project: {project.name}\n{project.root}")
        project_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        project_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(project_label)
        layout.addStretch()
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        status = QStatusBar()
        status.showMessage("Project loaded")
        self.setStatusBar(status)
