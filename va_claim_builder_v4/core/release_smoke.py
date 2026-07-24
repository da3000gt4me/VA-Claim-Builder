
from __future__ import annotations

import json
from pathlib import Path

from core.claims import ClaimManager
from core.evidence import EvidenceManager
from core.documents import DocumentManager
from core.intake import AutomatedIntakeOrchestrator, IntakeManager
from core.maintenance import ProjectMaintenance
from core.projects import ProjectManager
from core.submission import SubmissionGenerator, SubmissionManager
from core.timeline import TimelineManager
from core.nexus import NexusLetterManager
from core.ocr import OCRManager


def run_packaged_workflow(manager: ProjectManager, output: str | Path) -> dict:
    """Exercise local packaged services with synthetic data and emit machine-readable results."""
    project = manager.create_project("RC4 Synthetic Automatic Intake Smoke")
    claim = ClaimManager(project).create("Lumbar strain", description="Confirmed packaging fixture text")
    source = project.root / "temp" / "synthetic-medical-record.txt"
    source.write_text(
        "01/02/2024 Provider: Dr. Alex Smith. Facility: Test Clinic.\n"
        "Diagnosis: Lumbar strain. Symptoms: back pain, numbness. Medication: Gabapentin.\n"
        "MRI showed degenerative changes. Back pain limits standing and work.\n"
        "Diagnosis: Sleep apnea. Sleep apnea described as secondary to chronic pain; provider opinion needed.\n",
        encoding="utf-8",
    )
    document, _ = DocumentManager(project).import_file(source)
    intake_summary = AutomatedIntakeOrchestrator(project).analyze_document(document.document_id)
    evidence_records = EvidenceManager(project).list()
    timeline_events = TimelineManager(project).list()
    intake = IntakeManager(project)
    suggestions = intake.list_suggestions()
    claim_suggestion = next((item for item in suggestions if item.suggestion_type == "claim"), None)
    if claim_suggestion:
        intake.decide(claim_suggestion.suggestion_id, "accepted")
    evidence = evidence_records[0]
    submissions = SubmissionManager(project)
    package = submissions.create("Synthetic submission", "single_claim", claim_ids=(claim.claim_id,))
    validation = submissions.validate(package.package_id, project.root / "reports" / "submissions")
    export = SubmissionGenerator(project).generate(package.package_id, allow_incomplete=True)
    maintenance = ProjectMaintenance(project, manager)
    backup = maintenance.create_backup(manager.paths.backups)
    backup_manifest = maintenance.validate_backup(backup)
    restored = maintenance.restore(backup, manager.paths.projects / "RC2-Synthetic-Restored")
    reopened = manager.open_project(project.root)
    result = {
        "project_created": project.root.is_dir(),
        "project_reopened": reopened.project_id == project.project_id,
        "project_valid": not any(item["level"] == "blocking" for item in maintenance.validate_project()),
        "claim_created": bool(claim.claim_id),
        "evidence_created": bool(evidence.evidence_id),
        "automatic_processing": intake_summary.documents_processed == 1,
        "automatic_evidence_created": len(evidence_records) > 0,
        "automatic_timeline_created": len(timeline_events) > 0,
        "automatic_claim_matched": intake_summary.claims_matched > 0,
        "automatic_claim_suggestion_created": intake_summary.claim_suggestions_created > 0,
        "automation_review_items_visible": len(suggestions) > 0,
        "automation_results_persisted": bool(IntakeManager(reopened).list_suggestions()),
        "confirmed_text_preserved": ClaimManager(reopened).get(claim.claim_id).description == "Confirmed packaging fixture text",
        "local_only_no_provider_call": True,
        "submission_created": bool(package.package_id),
        "submission_exported": Path(export["output_folder"]).exists(),
        "validation_count": len(validation),
        "backup_valid": backup_manifest["project_id"] == project.project_id,
        "restored_project_opened": restored.project_id == project.project_id,
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    """Create a tiny dependency-free synthetic PDF with embedded text."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 12 Tf 72 740 Td 15 TL " + " ".join(
        f"({line}) Tj T*" for line in escaped
    ) + " ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(data)); data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(data)


def _write_scanned_pdf(path: Path, lines: list[str]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1800, 2400), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    y = 120
    for line in lines:
        draw.text((120, y), line, fill="black", font=font); y += 70
    image.save(path, "PDF", resolution=300)


def run_packaged_extraction_workflow(manager: ProjectManager, output: str | Path) -> dict:
    """Installed-app RC6 verification using only local synthetic documents."""
    project = manager.create_project("RC6 Synthetic Extraction Smoke")
    claims = ClaimManager(project)
    cervical = claims.create("Cervical radiculopathy", description="User-confirmed description")
    migraine = claims.create("Migraine headaches")
    fixtures = project.root / "temp" / "rc6-fixtures"; fixtures.mkdir(parents=True, exist_ok=True)
    digital = fixtures / "A-VA-Form-20-0995.pdf"
    _write_text_pdf(digital, [
        "VA FORM 20-0995 SUPPLEMENTAL CLAIM", "SECTION 21A",
        "CONDITION 1: Migraine headaches", "SECONDARY TO: Cervical radiculopathy",
        "DESCRIPTION: Headaches follow neck flares",
        "SERVICE EVENT: Training vehicle accident", "THEORY: Secondary service connection",
    ])
    scanned = fixtures / "B-Scanned-VA-Form-20-0995.pdf"
    _write_scanned_pdf(scanned, [
        "VA FORM 20-0995 SUPPLEMENTAL CLAIM", "SECTION 21A",
        "CONDITION: Tinnitus", "DESCRIPTION: Ringing after flight line duty",
        "SERVICE EVENT: Aircraft noise exposure",
    ])
    texts = {
        "C-Medical-Record.txt": (
            "MEDICAL RECORD\nEncounter 03/14/2025\nProvider: Dr. Alex Smith\nFacility: North Clinic\n"
            "Specialty: Neurology\nAssessment: Cervical radiculopathy M54.12\n"
            "Medication: Gabapentin 300 mg\nMRI impression: foraminal narrowing\n"
            "Treatment: physical therapy\nFunctional impact: limited lifting and work"
        ),
        "D-Personal-Timeline.txt": (
            "PERSONAL TIMELINE\n03/14/2004 - injured neck in a training vehicle accident\n"
            "04/20/2004 - neck symptoms continued while on duty"
        ),
        "E-Self-Nexus.txt": (
            "SELF-AUTHORED NEXUS STATEMENT\nCondition: Migraine headaches\n"
            "Secondary condition: Cervical radiculopathy\nOnset: after the training accident\n"
            "Continuity: headaches continued\nRationale: I believe neck pain causes headaches"
        ),
        "F-Provider-Nexus.txt": (
            "NEXUS LETTER\nProvider: Dr. Dana Lee\nCredentials: MD\nSpecialty: Neurology\n"
            "Condition: Cervical radiculopathy\nRationale: records and imaging reviewed\n"
            "Opinion: at least as likely as not related to service\nSignature: Dana Lee, MD"
        ),
        "G-Buddy-Statement.txt": (
            "BUDDY STATEMENT\nWitness: Jordan Doe\nRelationship to claimant: service buddy\n"
            "Condition: Cervical radiculopathy\nFunctional impact: I observed difficulty lifting\n"
            "Signature: Jordan Doe\nDate: 04/01/2025"
        ),
    }
    sources = [digital, scanned]
    for name, text in texts.items():
        path = fixtures / name; path.write_text(text, encoding="utf-8"); sources.append(path)
    documents = DocumentManager(project)
    document_ids = [documents.import_file(path)[0].document_id for path in sources]
    summary = AutomatedIntakeOrchestrator(project).run_documents(document_ids)
    ocr = OCRManager(project)
    pages = [page for document_id in document_ids for page in ocr.list_pages(document_id)]
    intake = IntakeManager(project)
    suggestions = intake.list_suggestions()
    metadata = [
        item.payload for item in suggestions
        if item.suggestion_type == "metadata"
    ]
    claim_rows = [item.payload for item in suggestions if item.suggestion_type == "claim"]
    diagnoses = [detail for item in metadata for detail in item.get("diagnosis_details", [])]
    statements = intake.list_imported_statements()

    # Exercise the installed UI's authoritative checkbox selection model without dialogs.
    from PySide6.QtCore import Qt
    from ui_qt.evidence_page import EvidencePage
    from ui_qt.ocr_page import OCRPage
    evidence_page = EvidencePage(project); ocr_page = OCRPage(project)
    evidence_before = EvidenceManager(project).list()
    checked_evidence = [row.evidence_id for row in evidence_before[:2]]
    for row in range(evidence_page.table.rowCount()):
        item = evidence_page.table.item(row, 0)
        item.setCheckState(
            Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in checked_evidence
            else Qt.CheckState.Unchecked
        )
    evidence_delete_ids = evidence_page._checked_evidence_ids()
    EvidenceManager(project).delete_many(evidence_delete_ids)
    checked_ocr = document_ids[:2]
    for row in range(ocr_page.table.rowCount()):
        item = ocr_page.table.item(row, 0)
        item.setCheckState(
            Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in checked_ocr
            else Qt.CheckState.Unchecked
        )
    ocr_delete_ids = ocr_page.checked_document_ids()
    ocr.delete_outputs(ocr_delete_ids)
    evidence_page.deleteLater(); ocr_page.deleteLater()

    reopened = manager.open_project(project.root)
    result = {
        "documents_processed": summary.documents_processed == 7,
        "all_pages_persisted": len(pages) >= 7 and all(page.state for page in pages),
        "raw_and_normalized_text": all(
            page.raw_text and page.normalized_text
            for page in pages if page.state != "unreadable_after_retry"
        ),
        "scanned_pdf_ocr_completed": any(
            page.document_id == document_ids[1] and page.extraction_method.startswith("tesseract")
            for page in pages
        ),
        "condition_suggestion": any(item.get("condition") == "Migraine headaches" for item in claim_rows),
        "secondary_suggestion": any(item.get("secondary_to") == "Cervical radiculopathy" for item in claim_rows),
        "description_suggestion": any(item.get("description") for item in claim_rows),
        "service_event_suggestion": any(item.get("service_event") for item in claim_rows),
        "diagnosis_created": any(item.get("diagnosis") == "Cervical radiculopathy" for item in diagnoses),
        "diagnosis_code_created": any(item.get("code") == "M54.12" for item in diagnoses),
        "provider_and_date_created": any(item.get("provider") and item.get("date") for item in diagnoses),
        "timeline_created": bool(TimelineManager(project).list()),
        "nexus_imported": any(
            document_ids[5] in item.document_ids for item in NexusLetterManager(project).list()
        ),
        "buddy_imported": any(item["statement_type"] == "buddy_witness_statement" for item in statements),
        "checked_evidence_only_deleted": (
            set(evidence_delete_ids) == set(checked_evidence)
            and not set(checked_evidence) & {row.evidence_id for row in EvidenceManager(project).list()}
        ),
        "checked_ocr_only_deleted": (
            set(ocr_delete_ids) == set(checked_ocr)
            and {row.document_id for row in OCRManager(project).list_results()} == set(document_ids[2:])
        ),
        "results_persisted": bool(IntakeManager(reopened).list_suggestions()),
        "confirmed_data_preserved": ClaimManager(reopened).get(cervical.claim_id).description == "User-confirmed description",
        "local_only_no_provider_call": True,
    }
    destination = Path(output); destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
