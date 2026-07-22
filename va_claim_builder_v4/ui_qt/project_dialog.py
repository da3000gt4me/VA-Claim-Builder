from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from core.projects import ProjectInfo, ProjectManager


class ProjectDialog:
    @staticmethod
    def choose_or_create(parent, manager: ProjectManager) -> ProjectInfo | None:
        recent = manager.last_opened_project()
        if recent is not None:
            return recent

        choice = QMessageBox.question(
            parent,
            "VA Claim Builder",
            "Create a new persistent project? Choose No to open an existing project.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return None
        if choice == QMessageBox.StandardButton.Yes:
            name, accepted = QInputDialog.getText(parent, "New Project", "Project name:")
            return manager.create_project(name) if accepted and name.strip() else None

        directory = QFileDialog.getExistingDirectory(parent, "Open VA Claim Builder Project", str(manager.paths.projects))
        return manager.open_project(Path(directory)) if directory else None
