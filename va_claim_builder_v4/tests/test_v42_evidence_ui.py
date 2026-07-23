
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
from ui_qt.dbq_page import DBQPage
from ui_qt.rating_strategy_page import RatingStrategyPage
from ui_qt.optimizer_page import OptimizerPage
from ui_qt.submission_page import SubmissionPage
from ui_qt.main_window import MainWindow


def test_evidence_workspace_is_integrated_into_main_window(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "app"
    monkeypatch.setenv("VCB_HOME", str(root))
    project = ProjectManager(AppPaths(root=root).ensure()).create_project("UI Evidence")
    window = MainWindow(project)

    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["Documents", "Automation Review", "OCR & Text", "Claims", "Evidence", "Medical Timeline", "Nexus Letters", "DBQ Assistant", "Rating Strategy", "Claim Optimizer", "Submission Builder", "Settings"]
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


def test_dbq_navigation_template_edit_sources_completeness_and_controls(tmp_path: Path) -> None:
    app=QApplication.instance() or QApplication([]);root=tmp_path/"app";project=ProjectManager(AppPaths(root=root).ensure()).create_project("UI DBQ");ClaimManager(project).create("Migraines");e=EvidenceManager(project).create("Headache diary");page=DBQPage(project);page.template.setCurrentIndex(page.template.findData("headaches_migraines"));page.title.setText("Migraine preparation");page.condition.setText("Migraines");page.field_widgets["claimant_reported_symptoms"].setPlainText("Weekly headaches");page.evidence_sources.item(0).setCheckState(Qt.CheckState.Checked);page.save()
    assert page.table.rowCount()==1 and page.revisions.rowCount()==1 and page.manager.get(page.current_id).evidence_ids==(e.evidence_id,);assert page.field_widgets["prostrating_attacks"].isReadOnly();assert "Score:" in page.completeness.toPlainText()
    buttons={b.text() for b in page.findChildren(QPushButton)};assert {"Create DBQ Work Product","Save Manual Edits","Duplicate","Delete","Export DOCX…","Generate AI Suggestions","Cancel Generation","Accept Suggestion","Reject Suggestion"}<=buttons
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())]==["DBQ Editor","Sources & Suggestions","Completeness & Revisions"];page.close();app.processEvents()


def test_rating_strategy_navigation_history_filters_and_sections(tmp_path: Path) -> None:
    app=QApplication.instance() or QApplication([]);root=tmp_path/"app";project=ProjectManager(AppPaths(root=root).ensure()).create_project("UI Rating");claim=ClaimManager(project).create("Migraines");page=RatingStrategyPage(project);record=page.manager.create(claim.claim_id,status="completed",confidence="medium",estimated_rating_range="10%–30% preliminary",strengths=["Diagnosis documented"],missing_evidence=["Occupational impact"],recommended_actions=["Add headache log"]);page.refresh();page.history.selectRow(0);app.processEvents()
    assert page.history.rowCount()==1 and "10%–30%" in page.summary.text() and "Diagnosis documented" in page.sections["strengths"].toPlainText();assert page.claim_filter.count()==2 and page.status_filter.count()==5
    buttons={b.text() for b in page.findChildren(QPushButton)};assert {"Analyze Selected Claim","Analyze Filtered Claims","Cancel Analysis","Refresh"}<=buttons;assert set(page.sections)=={"strengths","weaknesses","missing_evidence","contradictory_evidence","recommended_actions","supporting_evidence","secondary_opportunities","aggravation_opportunities","presumptive_opportunities","generated_reasoning"};page.close();app.processEvents()


def test_optimizer_navigation_gap_management_filters_history_and_exports(tmp_path: Path) -> None:
    app=QApplication.instance() or QApplication([]);root=tmp_path/"app";project=ProjectManager(AppPaths(root=root).ensure()).create_project("UI Optimizer");claim=ClaimManager(project).create("Back strain");page=OptimizerPage(project);a=page.manager.create(claim.claim_id,status="completed",overall_score=40,service_connection_score=50,severity_rating_score=30,evidence_quality_score=60,evidence_consistency_score=80,confidence="low",score_explanation={"formula":"weighted"});g=page.manager.add_gap(a.assessment_id,"missing_current_diagnosis","Diagnosis missing",priority=1);page.claims_list.setCurrentRow(0);page.refresh();page.history.selectRow(0);app.processEvents()
    assert page.gaps.rowCount()==1 and "Overall: 40%" in page.scores.text();page.gaps.selectRow(0);page._decision("resolve");assert page.manager.get_gap(g.gap_id).status=="resolved";page._decision("reopen");assert page.manager.get_gap(g.gap_id).status=="unresolved";page.unresolved.setChecked(True);app.processEvents();assert page.gaps.rowCount()==1
    buttons={b.text() for b in page.findChildren(QPushButton)};assert {"Analyze Selected Claim","Analyze All Claims","Cancel Analysis","Add Manual Gap","Edit Gap","Resolve Gap","Reopen Gap","Mark Not Applicable","Accept AI Suggestion","Reject AI Suggestion","Mark Action Completed","Export Lay Statement DOCX…","Export Provider Request DOCX…"}<=buttons;page.close();app.processEvents()


def test_submission_navigation_creation_source_section_exhibit_validation_and_history(tmp_path: Path) -> None:
    app=QApplication.instance() or QApplication([]);root=tmp_path/"app";project=ProjectManager(AppPaths(root=root).ensure()).create_project("UI Submission");claim=ClaimManager(project).create("Migraines");ev=EvidenceManager(project).create("Headache diary");page=SubmissionPage(project);page.name.setText("Migraine package");page.package_type.setCurrentIndex(page.package_type.findData("single_claim"));page.claim_select.item(0).setCheckState(Qt.CheckState.Checked);page.source_lists["evidence"].item(0).setCheckState(Qt.CheckState.Checked);page.save();page._validate()
    assert page.packages.rowCount()==1 and page.sections.rowCount()>=20 and page.exhibits.rowCount()==1 and page.manager.get(page.current).claim_ids==(claim.claim_id,);assert page.manager.get(page.current).sources[0].source_id==ev.evidence_id and "WARNING" not in page.validation.toPlainText().splitlines()[0]
    page.sections.selectRow(1);before=page.manager.get(page.current).sections[1]["section_key"];page._move_section(-1);assert page.manager.get(page.current).sections[0]["section_key"]==before
    buttons={b.text() for b in page.findChildren(QPushButton)};assert {"Create Package","Save Package Configuration","Duplicate Package","Delete Package","Move Section Up","Move Exhibit Up","Rename Exhibit","Validate Package","Generate Package","Cancel Generation","Open Output Folder"}<=buttons;page.close();app.processEvents()


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
