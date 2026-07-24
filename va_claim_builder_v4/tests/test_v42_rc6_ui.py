from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.ocr import OCRManager
from core.projects import ProjectManager
from ui_qt.evidence_page import EvidencePage
from ui_qt.ocr_page import OCRPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_project(tmp_path: Path):
    return ProjectManager(home=tmp_path / "app").create_project("RC6 UI")


def test_evidence_checkboxes_are_authoritative_and_header_is_tri_state(app, tmp_path):
    project = make_project(tmp_path)
    manager = EvidenceManager(project)
    records = [manager.create(f"Evidence {index}") for index in range(3)]
    page = EvidencePage(project)
    page.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert page.check_header.checkState() == Qt.CheckState.PartiallyChecked
    page.table.selectRow(2)
    assert page._checked_evidence_ids() == [records[0].evidence_id]
    manager.delete_many(page._checked_evidence_ids())
    assert {item.evidence_id for item in manager.list()} == {
        records[1].evidence_id, records[2].evidence_id,
    }
    page.deleteLater()


def test_evidence_filter_preserves_checked_ids_and_header_selects_visible(app, tmp_path):
    project = make_project(tmp_path)
    manager = EvidenceManager(project)
    manager.create("Alpha", review_status="relevant")
    manager.create("Beta", review_status="unreviewed")
    page = EvidencePage(project)
    page.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    checked = set(page._checked_evidence_ids())
    page.status_filter.setCurrentIndex(page.status_filter.findData("unreviewed"))
    assert checked <= set(page._checked_evidence_ids())
    page._check_visible(Qt.CheckState.Checked)
    assert page.check_header.checkState() == Qt.CheckState.Checked
    assert len(page._checked_evidence_ids()) == 2
    page.deleteLater()


def test_ocr_checked_ids_drive_bulk_delete_not_highlight(app, tmp_path):
    project = make_project(tmp_path)
    documents = DocumentManager(project)
    ids = []
    for index in range(3):
        source = tmp_path / f"record-{index}.txt"
        source.write_text(f"Diagnosis: Synthetic {index}", encoding="utf-8")
        document, _ = documents.import_file(source)
        OCRManager(project).process(document.document_id)
        ids.append(document.document_id)
    page = OCRPage(project)
    visible_ids = [
        str(page.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        for row in range(page.table.rowCount())
    ]
    page.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    page.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    page.table.selectRow(2)
    checked = page.checked_document_ids()
    assert set(checked) == set(visible_ids[:2])
    OCRManager(project).delete_outputs(checked)
    assert {item.document_id for item in OCRManager(project).list_results()} == {visible_ids[2]}
    assert len(documents.list_documents()) == 3
    page.deleteLater()


def test_ocr_header_selects_and_clears_all_visible_rows(app, tmp_path):
    project = make_project(tmp_path)
    for index in range(2):
        source = tmp_path / f"source-{index}.txt"; source.write_text(f"synthetic {index}", encoding="utf-8")
        DocumentManager(project).import_file(source)
    page = OCRPage(project)
    page._check_visible(Qt.CheckState.Checked)
    assert len(page.checked_document_ids()) == 2
    assert page.check_header.checkState() == Qt.CheckState.Checked
    page._check_visible(Qt.CheckState.Unchecked)
    assert page.checked_document_ids() == []
    page.deleteLater()
