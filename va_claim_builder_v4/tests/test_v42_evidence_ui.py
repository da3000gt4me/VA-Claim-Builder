from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.projects import AppPaths, ProjectManager
from ui_qt.main_window import MainWindow


def test_evidence_workspace_is_integrated_into_main_window(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "app"
    monkeypatch.setenv("VCB_HOME", str(root))
    project = ProjectManager(AppPaths(root=root).ensure()).create_project("UI Evidence")
    window = MainWindow(project)

    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["Documents", "OCR & Text", "Claims", "Evidence", "Settings"]
    assert window.evidence_page.table.rowCount() == 0
    assert window.evidence_page.empty_message.text() == "No evidence has been added to this project yet."
    window.close()
    app.processEvents()
