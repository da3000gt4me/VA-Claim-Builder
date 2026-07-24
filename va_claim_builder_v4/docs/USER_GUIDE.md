
# User Guide — Version 4.2.0 RC6

## RC6 OCR review and structured import

Checkboxes are authoritative for OCR and Evidence bulk actions; highlighting
only opens a preview. The header checkbox selects visible rows. Deleting checked
OCR outputs or evidence preserves uploaded documents and claims.

Each OCR page exposes raw, normalized, and corrected text. Low-quality native
text triggers local OCR instead of being skipped. Rotate/retry and readability
overrides persist. Confirmed claim text is never overwritten.

## Projects and documents

Create or open a project from the welcome screen. A project is a local folder containing `manifest.json`, `project.db`, source uploads, OCR artifacts, generated reports, and temporary work areas. Import documents without modifying originals. The OCR workspace records pending, completed, failed, cancelled, and no-text outcomes.

## Claims and evidence

Create claims, then create or review evidence and link it to one or more claims. Evidence review supports relevance states, reviewer notes, claim-specific relevance notes, duplicate references, OCR preview, search, and filtering. Links can be changed without deleting the evidence or its source document.

## Advisory preparation workspaces

Evidence Analyzer produces structured, historical advisory analyses. Medical Timeline stores confirmed chronological events and separately reviews AI-extracted candidates. Nexus Letters and DBQ Assistant create review drafts with source traceability and revision history; examiner-only measurements and findings are not invented. Rating Strategy estimates non-guaranteed ranges and identifies gaps or contradictions. Claim Optimizer turns those findings into readiness explanations and trackable actions. AI suggestions require confirmation.

## Submission Builder

Create a package, select confirmed claims and sources, configure sections and exhibits, validate, then export. Blocking validation issues must be resolved or explicitly exported as an incomplete draft. Available outputs include a DOCX summary binder, DOCX/CSV evidence indexes, JSON manifest, companion files, ZIP, and consolidated PDF when source PDFs can be read safely. Originals are never modified.

## AI and privacy

Open Settings to choose OpenAI or xAI, select models, and enable Local-only or Redact-before-cloud. Local-only prevents cloud calls and needs no cloud credentials. Redaction is applied before provider invocation when enabled but cannot guarantee anonymity. Provider failures and malformed responses are recorded without logging medical content or secrets.

## Backup, validation, and recovery

Use the Project menu to create a checksum-validated backup, restore it into a new folder, validate the active project, apply listed safe repairs, or export sanitized diagnostics. Opening an older schema automatically creates a database backup before migration. On restart, interrupted job states are recovered and incomplete outputs are not presented as completed. Repair does not delete evidence.

## Everyday safety

Keep an independent backup before large imports or maintenance. Review every generated draft, confirm source citations, obtain required signatures and professional findings, and retain originals. Do not rely on scores, analyses, or package organization as advice or an outcome prediction.
## RC4 automated intake and approval

RC4 treats import as the beginning of a persistent background workflow:
validation, fingerprinting, text/OCR extraction, classification, local medical
fact extraction, draft evidence, claim matching, timeline construction,
relationship indicators, and contradiction/gap review.

Drafts are separate from confirmed content. Existing user-written claim fields
are never overwritten. A claim suggestion becomes a claim only after acceptance.
Relationship language is presented as a possibility and states when a qualified
provider opinion may still be needed. **Automation Review** centralizes the
queue, failures, suggestions, evidence/timeline review items, and bulk decisions.
Reanalysis deduplicates unchanged output and preserves prior decisions.
