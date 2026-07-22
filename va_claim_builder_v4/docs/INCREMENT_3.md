# Version 4.0.0 — Increment 3

Adds page-level extraction, OCR confidence scoring, low-confidence review queues, local claim-specific retrieval, contradiction detection and resolution, claim readiness scoring, and a downloadable readiness package with a machine-readable manifest.

## Safety design
- Original uploads remain unchanged.
- Full records remain local unless the user explicitly runs a cloud AI task.
- Low-confidence pages are flagged for review.
- Only approved evidence contributes to readiness and generated review products.
- Contradictions are surfaced, not hidden or deleted.
