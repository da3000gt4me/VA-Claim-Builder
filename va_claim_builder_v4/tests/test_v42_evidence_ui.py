from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.claims import ClaimManager
from core.evidence import EvidenceManager
from core.projects import AppPaths, ProjectManager
from ui_qt.evidence_page import EvidencePage
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


def test_evidence_review_controls_save_status_and_claim_note(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "app"
    project = ProjectManager(AppPaths(root=root).ensure()).create_project("UI Review")
    claim = ClaimManager(project).create("Migraines")
    page = EvidencePage(project)

    page.title.setText("Headache diary")
    page.review_status.setCurrentText("relevant")
    page.reviewer_notes.setPlainText("Reviewed against treatment history")
    item = page.claim_links.item(0)
    item.setCheckState(Qt.CheckState.Checked)
    page.claim_links.setCurrentItem(item)
    page.claim_note.setPlainText("Documents frequency for the migraine claim")
    page.save()

    records = EvidenceManager(project).list(review_status="relevant", claim_id=claim.claim_id)
    assert len(records) == 1
    assert records[0].reviewer_notes == "Reviewed against treatment history"
    assert EvidenceManager(project).claim_links_for_evidence(records[0].evidence_id)[0].relevance_notes == (
        "Documents frequency for the migraine claim"
    )
    assert page.status_filter.count() == 6
    assert page.ocr_filter.count() == 6
    page.close(); app.processEvents()
