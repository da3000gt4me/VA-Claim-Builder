from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class DocumentCategory(StrEnum):
    VA_DENIAL_LETTERS = "00_va_denial_letters"
    FORM_995 = "01_form_20_0995_submissions"
    SUPPORT_STATEMENTS = "02_statements_in_support_of_claim"
    MEDICAL_RECORDS = "03_medical_records"
    SELF_NEXUS_DRAFTS = "04_draft_self_nexus_letters"
    DOCTOR_NEXUS_DRAFTS = "05_draft_doctor_nexus_letters"
    BUDDY_LETTER_DRAFTS = "06_draft_buddy_lay_letters"
    SMART_TRANSCRIPT = "07_smart_transcript"
    MILITARY_RECORDS = "08_military_records"
    DD214 = "09_dd214"
    PERSONAL_TIMELINES = "10_personal_statements_historical_timelines"
    UNCLASSIFIED = "99_unclassified"

@dataclass(frozen=True)
class CategoryDefinition:
    category: DocumentCategory
    title: str
    purpose: str
    editable_starting_point: bool = False

CATEGORY_DEFINITIONS = [
    CategoryDefinition(DocumentCategory.VA_DENIAL_LETTERS, "0. VA Denial Letters", "Extract favorable findings, denial reasons, missing elements, and evidence considered."),
    CategoryDefinition(DocumentCategory.FORM_995, "1. VA Form 20-0995 Submission(s)", "Track submitted issues, dates, and asserted new and relevant evidence."),
    CategoryDefinition(DocumentCategory.SUPPORT_STATEMENTS, "2. Statements in Support of Claim", "Map statements to conditions and reconcile factual assertions."),
    CategoryDefinition(DocumentCategory.MEDICAL_RECORDS, "3. Medical Record(s)", "OCR, deduplicate, chronologically index, and annotate medical evidence."),
    CategoryDefinition(DocumentCategory.SELF_NEXUS_DRAFTS, "4. Draft Self-Nexus Letter(s)", "Editable starting points for revised veteran-authored causal narratives.", True),
    CategoryDefinition(DocumentCategory.DOCTOR_NEXUS_DRAFTS, "5. Draft Doctor Nexus Letter(s)", "Editable starting points for clinician-review drafts; never treated as signed opinions.", True),
    CategoryDefinition(DocumentCategory.BUDDY_LETTER_DRAFTS, "6. Draft Buddy/Lay Letter(s)", "Editable starting points limited to each witness's firsthand knowledge.", True),
    CategoryDefinition(DocumentCategory.SMART_TRANSCRIPT, "7. SMART Transcript", "Extract training, qualifications, occupational duties, and exposure corroboration."),
    CategoryDefinition(DocumentCategory.MILITARY_RECORDS, "8. Military Record(s)", "Extract assignments, duties, incidents, evaluations, treatment, and exposure evidence."),
    CategoryDefinition(DocumentCategory.DD214, "9. DD-214", "Verify service dates, branch, specialty, awards, training, and discharge information."),
    CategoryDefinition(DocumentCategory.PERSONAL_TIMELINES, "10. Personal Statements and Historical Timelines", "Capture onset, worsening, continuity, treatment gaps, functional impact, and witnesses.", True),
    CategoryDefinition(DocumentCategory.UNCLASSIFIED, "Unclassified Documents", "Temporary holding area pending human classification."),
]

DRAFT_CATEGORIES = {
    DocumentCategory.SELF_NEXUS_DRAFTS,
    DocumentCategory.DOCTOR_NEXUS_DRAFTS,
    DocumentCategory.BUDDY_LETTER_DRAFTS,
    DocumentCategory.PERSONAL_TIMELINES,
}
