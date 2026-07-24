# OCR and Structured Extraction

Version 4.2.0 RC6 processes PDFs per page. Embedded text is evaluated first
using character, word, alphanumeric, fragmentation, symbol, date, diagnosis
code, and provider indicators. Low-quality pages are rendered at 300 DPI and
sent to local Tesseract with bounded paragraph and sparse-text retries.

The OCR workspace shows raw, normalized, and corrected text, extraction method,
quality, page state, and failure reason. It repairs wrapped prose and line-wrap
hyphenation while preserving headings, bullets, labels, and table-like rows.
Corrections and readability overrides survive reanalysis until reverted.

Tesseract is an external local requirement for scans. Install it with
`brew install tesseract` on macOS or `choco install tesseract` on Windows.
Digital PDFs, DOCX, and text files use native extraction without Tesseract.
Release artifacts record the tested engine in `ocr-engine-report.txt`.

Automation creates reviewable Form 20-0995, diagnosis, provider, timeline,
nexus, and buddy/witness suggestions. AcroForm values precede OCR. Nothing is
confirmed automatically, and accepted extraction fills only blank claim fields.

Checked IDs—not row highlighting—control OCR and Evidence bulk actions. The
tri-state header selects visible rows. Source documents and claims are preserved.
