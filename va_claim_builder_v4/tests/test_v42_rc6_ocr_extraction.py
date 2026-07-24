from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.intake import AutomatedIntakeOrchestrator, IntakeManager, LocalMedicalExtractor
from core.intake.structured import (
    classify_document, extract_diagnoses, parse_20_0995, parse_statement,
)
from core.ocr import OCRManager, evaluate_text, normalize_extracted_text
from core.nexus import NexusLetterManager
from core.projects import AppPaths, ProjectManager
from core.projects.manager import SCHEMA_VERSION
from core.timeline import TimelineManager


def project(tmp_path: Path):
    paths = AppPaths(root=tmp_path / "app").ensure()
    return ProjectManager(paths).create_project("RC6 Synthetic"), paths


def test_normalization_repairs_wrapped_paragraph_and_hyphenation_but_preserves_structure():
    raw = (
        "ASSESSMENT:\n"
        "The patient has chronic cervi-\ncal pain that limits lifting\n"
        "and prolonged standing.\n\n"
        "Medications: Gabapentin 300 mg\n"
        "• Continue physical therapy\n"
        "• MRI follow-up"
    )
    text = normalize_extracted_text(raw)
    assert "cervical pain" in text
    assert "limits lifting and prolonged standing." in text
    assert "ASSESSMENT:" in text
    assert "\n• Continue" in text and "\n• MRI" in text


def test_quality_uses_composite_indicators_and_flags_fragmented_text():
    good = evaluate_text(
        "Assessment: Cervical radiculopathy M54.12 documented on 03/14/2025 by Dr. Alex Smith."
    )
    bad = evaluate_text("@@@ x x x q q q ###")
    assert good.score > bad.score
    assert good.diagnosis_code_count == 1
    assert good.date_count == 1
    assert bad.review_required


def test_native_plain_text_persists_raw_normalized_pages_and_corrections(tmp_path):
    item, _ = project(tmp_path)
    source = tmp_path / "wrapped record.txt"
    source.write_text("Diagnosis: Cervi-\\ncal radiculopathy M54.12\\nProvider: Dr. Alex Smith", encoding="utf-8")
    document, _ = DocumentManager(item).import_file(source)
    manager = OCRManager(item)
    result = manager.process(document.document_id)
    page = manager.get_page(document.document_id, 1)
    assert result.page_count == 1
    assert page.raw_text
    assert page.normalized_text
    manager.save_correction(document.document_id, 1, "Corrected diagnosis text")
    manager.process(document.document_id)
    assert manager.get_page(document.document_id, 1).corrected_text == "Corrected diagnosis text"
    assert "Corrected diagnosis text" in manager.get(document.document_id).text_path.read_text()


def test_delete_many_ocr_outputs_is_transactional_and_preserves_documents(tmp_path):
    item, _ = project(tmp_path)
    documents = DocumentManager(item)
    ids = []
    for index in range(3):
        source = tmp_path / f"{index}.txt"; source.write_text(f"Record {index}", encoding="utf-8")
        record, _ = documents.import_file(source); OCRManager(item).process(record.document_id); ids.append(record.document_id)
    assert OCRManager(item).delete_outputs(ids[:2]) == 2
    assert {row.document_id for row in OCRManager(item).list_results()} == {ids[2]}
    assert len(documents.list_documents()) == 3


def test_evidence_bulk_delete_removes_only_requested_records_and_keeps_document(tmp_path):
    item, _ = project(tmp_path)
    source = tmp_path / "source.txt"; source.write_text("evidence source", encoding="utf-8")
    document, _ = DocumentManager(item).import_file(source)
    manager = EvidenceManager(item)
    records = [manager.create(f"Evidence {index}", document_id=document.document_id) for index in range(3)]
    assert manager.delete_many([records[0].evidence_id, records[2].evidence_id]) == 2
    assert [record.evidence_id for record in manager.list()] == [records[1].evidence_id]
    assert DocumentManager(item).get(document.document_id).stored_path.exists()


def test_form_20_0995_acroform_section_21a_parsing():
    fields = {
        "Section21A_Issue1_Condition": "Migraine headaches",
        "Section21A_Issue1_Secondary": "Cervical spine condition",
        "Section21A_Issue1_Description": "Headaches worsened with neck pain",
        "Section21A_Issue1_Event": "Vehicle accident during training",
        "Section21A_Issue1_DecisionDate": "03/14/2025",
    }
    classification = classify_document("", filename="VA Form 20-0995.pdf", fields=fields)
    suggestions = parse_20_0995([], fields=fields)
    assert classification.document_type == "va_form_20_0995"
    assert suggestions[0]["condition"] == "Migraine headaches"
    assert suggestions[0]["secondary_to"] == "Cervical spine condition"
    assert suggestions[0]["service_event"] == "Vehicle accident during training"
    assert suggestions[0]["extraction_method"] == "acroform"


def test_flattened_20_0995_multiple_issue_rows_include_page_provenance():
    page = """VA FORM 20-0995 SUPPLEMENTAL CLAIM
SECTION 21A
CONDITION 1: Migraine headaches
DATE OF VA DECISION: 03/14/2025
SECONDARY TO: Cervical spine condition
DESCRIPTION: Headaches follow neck flares
SERVICE EVENT: Training vehicle accident
THEORY: Secondary service connection
CONDITION 2: Tinnitus
DESCRIPTION: Ringing began after flight line noise
SERVICE EVENT: Aircraft noise exposure"""
    rows = parse_20_0995([(2, page)])
    assert [row["condition"] for row in rows] == ["Migraine headaches", "Tinnitus"]
    assert all(row["source_page"] == 2 for row in rows)


def test_diagnosis_extraction_codes_status_provider_and_source_page():
    pages = [(3, """Encounter 04/02/2025
Provider: Dr. Alex Smith
Specialty: Neurology
Assessment: Cervical radiculopathy M54.12
Diagnosis: possible carpal tunnel syndrome G56.00
Family history: diabetes E11.9""")]
    rows = extract_diagnoses(pages, provider="Alex Smith", facility="VA Clinic", specialty="Neurology")
    confirmed = next(row for row in rows if row["code"] == "M54.12")
    suspected = next(row for row in rows if row["code"] == "G56.00")
    assert confirmed["status"] == "confirmed"
    assert suspected["status"] == "suspected"
    assert confirmed["provider"] == "Alex Smith"
    assert confirmed["source_page"] == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PERSONAL TIMELINE\\n03/14/2004 - injured knee during training", "personal_timeline"),
        ("BUDDY STATEMENT\\nWitness: Jordan Doe\\nI observed daily pain.", "buddy_witness_statement"),
        ("NEXUS LETTER\\nProvider: Dr. A\\nCredentials: MD\\nat least as likely as not", "provider_nexus_letter"),
        ("SELF-AUTHORED NEXUS STATEMENT\\nI believe this is due to service.", "claimant_nexus_statement"),
    ],
)
def test_structured_document_classification(text, expected):
    assert classify_document(text).document_type == expected


def test_statement_parser_does_not_promote_lay_observation_to_medical_opinion():
    classification = classify_document(
        "BUDDY STATEMENT\nWitness: Jordan Doe\nRelationship to claimant: spouse\n"
        "Functional impact: I observed difficulty walking\nSignature: Jordan Doe"
    )
    fields = parse_statement(classification, "Witness: Jordan Doe\nRelationship to claimant: spouse\n"
                            "Functional impact: I observed difficulty walking\nSignature: Jordan Doe")
    assert fields["author_type"] == "lay witness"
    assert fields["functional_impact"] == "I observed difficulty walking"
    assert not fields["opinion_language"]
    assert fields["signed"]


def test_end_to_end_local_intake_creates_pending_traceable_results_and_preserves_decisions(tmp_path):
    item, paths = project(tmp_path)
    claim = ClaimManager(item).create("Cervical radiculopathy")
    sources = {
        "medical.txt": """MEDICAL RECORD
Encounter 03/14/2025
Provider: Dr. Alex Smith
Facility: North Clinic
Specialty: Neurology
Assessment: Cervical radiculopathy M54.12
Medication: Gabapentin
MRI impression: foraminal narrowing
Treatment: physical therapy""",
        "timeline.txt": """PERSONAL TIMELINE
03/14/2004 - injured neck in a training vehicle accident
04/20/2004 - symptoms continued during duty""",
        "provider nexus.txt": """NEXUS LETTER
Provider: Dr. Dana Lee
Credentials: MD
Condition: Cervical radiculopathy
Rationale: Records and imaging were reviewed
Opinion: at least as likely as not related to service
Signature: Dana Lee, MD""",
        "buddy.txt": """BUDDY STATEMENT
Witness: Jordan Doe
Relationship to claimant: service buddy
Condition: Neck pain
Functional impact: I observed difficulty lifting after the accident
Signature: Jordan Doe""",
    }
    ids = []
    for name, content in sources.items():
        path = tmp_path / name; path.write_text(content, encoding="utf-8")
        document, _ = DocumentManager(item).import_file(path); ids.append(document.document_id)
    summary = AutomatedIntakeOrchestrator(item).run_documents(ids)
    assert summary.documents_processed == 4
    suggestions = IntakeManager(item).list_suggestions()
    assert suggestions and all(row.status == "pending" for row in suggestions)
    assert any(row.payload.get("diagnosis_details") for row in suggestions if row.suggestion_type == "metadata")
    assert TimelineManager(item).list()
    statements = IntakeManager(item).list_imported_statements()
    assert {row["statement_type"] for row in statements} == {"provider_nexus_letter", "buddy_witness_statement"}
    assert any(ids[2] in letter.document_ids for letter in NexusLetterManager(item).list())
    first = suggestions[0]
    IntakeManager(item).decide(first.suggestion_id, "rejected")
    reopened = ProjectManager(paths).open_project(item.root)
    assert IntakeManager(reopened).get_suggestion(first.suggestion_id).status == "rejected"
    assert ClaimManager(reopened).get(claim.claim_id).condition_name == "Cervical radiculopathy"


def test_schema_11_migration_is_idempotent_and_preserves_project(tmp_path):
    item, paths = project(tmp_path)
    with sqlite3.connect(item.database_path) as connection:
        connection.execute("UPDATE schema_metadata SET value='10' WHERE key='schema_version'")
    reopened = ProjectManager(paths).open_project(item.root)
    reopened = ProjectManager(paths).open_project(reopened.root)
    with sqlite3.connect(reopened.database_path) as connection:
        version = int(connection.execute(
            "SELECT value FROM schema_metadata WHERE key='schema_version'"
        ).fetchone()[0])
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION == 11
    assert {"ocr_pages", "document_classifications", "imported_statements"} <= tables
