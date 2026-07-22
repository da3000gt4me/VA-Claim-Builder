from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from core.claims import ClaimManager
from core.evidence import EvidenceManager
from core.evidence import EvidenceAnalysisService
from core.ai.types import AIResponse
from core.settings import AISettings, SettingsManager
from core.projects import AppPaths, ProjectManager
from ui_qt.evidence_page import EvidencePage
from ui_qt.timeline_page import TimelinePage
from ui_qt.nexus_page import NexusPage
from ui_qt.main_window import MainWindow


def test_evidence_workspace_is_integrated_into_main_window(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "app"
    monkeypatch.setenv("VCB_HOME", str(root))
    project = ProjectManager(AppPaths(root=root).ensure()).create_project("UI Evidence")
    window = MainWindow(project)

    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["Documents", "OCR & Text", "Claims", "Evidence", "Medical Timeline", "Nexus Letters", "Settings"]
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


def test_medical_timeline_navigation_editing_filters_and_controls(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([]); root=tmp_path/"app";project=ProjectManager(AppPaths(root=root).ensure()).create_project("UI Timeline")
    ClaimManager(project).create("Back condition");page=TimelinePage(project)
    page.title.setText("Initial evaluation");page.event_date.setText("2022-01-03");page.event_type.setCurrentText("diagnosis");page.provider.setText("VA Clinic");page.description.setPlainText("Evaluation confirmed back pain");page.save()
    assert page.table.rowCount()==1 and "Initial evaluation" in page.narrative.toPlainText()
    page.provider_filter.setText("Other");app.processEvents();assert page.table.rowCount()==0
    page.provider_filter.setText("VA");app.processEvents();assert page.table.rowCount()==1
    button_texts={button.text() for button in page.findChildren(QPushButton)}
    assert {"Extract Checked Evidence","Extract Document","Cancel Extraction","Accept Candidate","Reject Candidate","Save Accepted Events","Export CSV…"}<=button_texts
    assert page.tabs.tabText(0)=="Structured Table" and page.tabs.tabText(1)=="Narrative" and page.tabs.tabText(2)=="Candidate Review"
    page.close();app.processEvents()


def test_nexus_navigation_creation_sources_revisions_and_controls(tmp_path: Path) -> None:
    app=QApplication.instance() or QApplication([]);root=tmp_path/"app";project=ProjectManager(AppPaths(root=root).ensure()).create_project("UI Nexus");ClaimManager(project).create("Back condition");e=EvidenceManager(project).create("Medical note");TimelinePage(project).manager.create("Back evaluation")
    page=NexusPage(project);page.title.setText("Back Nexus Draft");page.sections["current_diagnosis"].setPlainText("Lumbar strain");page.evidence_sources.item(0).setCheckState(Qt.CheckState.Checked);page.save()
    assert page.table.rowCount()==1 and page.revisions.rowCount()==1 and page.manager.get(page.current_id).evidence_ids==(e.evidence_id,)
    buttons={b.text() for b in page.findChildren(QPushButton)}
    assert {"Create Draft","Save Manual Edits","Duplicate Draft","Delete","Export DOCX…","Generate AI-assisted Draft","Cancel Generation"}<=buttons
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())]==["Draft Editor","Sources & AI Generation","Revision History"]
    page.close();app.processEvents()


def test_ai_analysis_controls_display_history_and_advisory_result(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "app"; paths = AppPaths(root=root).ensure()
    project = ProjectManager(paths).create_project("UI AI Analysis")
    claim = ClaimManager(project).create("Migraines")
    evidence = EvidenceManager(project).create("Neurology note")
    settings = SettingsManager(paths); settings.save_ai_settings(AISettings(openai_api_key="fake-key"))
    payload = {
        "summary": "Neurology note documents recurring headaches.",
        "diagnoses_or_conditions": ["Migraine"],
        "symptoms_and_functional_limitations": ["Missed work"],
        "treatment_testing_medications": ["Medication trial"], "dates_and_providers": [],
        "in_service_events_or_exposures": [], "nexus_supporting_statements": [],
        "aggravation_evidence": [], "secondary_service_connection_evidence": [],
        "favorable_evidence": ["Ongoing treatment"], "unfavorable_or_contradictory_evidence": [],
        "missing_information_or_clarification_needs": [],
        "recommended_claim_associations": [{"claim_id": claim.claim_id, "claim_name": "Migraines", "reason": "Relevant note"}],
        "confidence": "medium",
    }

    class Router:
        def generate(self, request):
            return AIResponse(provider="openai", model="fake-model", text="", parsed=payload)

    service = EvidenceAnalysisService(project, settings_manager=settings, router_factory=lambda _settings: Router())
    service.analyze(evidence.evidence_id)
    page = EvidencePage(project); page.analysis = service; page.table.selectRow(0); app.processEvents()
    page._refresh_analysis()

    assert page.analyze_selected_button.text() == "Analyze Selected"
    assert page.analyze_batch_button.text() == "Analyze Checked / Filtered"
    assert page.cancel_analysis_button.text() == "Cancel Analysis"
    assert page.analysis_history.count() == 1
    assert "advisory" in page.analysis_advisory.text().lower()
    assert "Neurology note documents" in page.analysis_result.toPlainText()
    assert page.analysis_recommendations.count() == 1
    assert EvidenceManager(project).claims_for_evidence(evidence.evidence_id) == []
    page.analysis_recommendations.item(0).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    page._apply_recommendations()
    assert [item.claim_id for item in EvidenceManager(project).claims_for_evidence(evidence.evidence_id)] == [claim.claim_id]
    page.close(); app.processEvents()
