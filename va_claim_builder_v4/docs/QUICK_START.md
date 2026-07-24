
# Quick Start

## RC6 document processing

Import documents, open **OCR & Text Extraction**, check documents, and choose
**Process Checked**. Correct flagged pages as needed. Use **Automation Review
Center** to accept or reject extracted fields. Imported provider letters appear
in **Nexus Letters** when a claim matches; lay statements appear in
**Buddy / Witness**.

## RC4 automatic intake

Import documents with **Automatically analyze imported documents** selected for
the normal import-to-prepopulation workflow, or clear it to import only. The
background job creates source-linked draft evidence, timeline events, claim
matches, and suggestions. Open **Automation Review** to accept, reject, defer, or
reprocess items. Use **Reanalyze Failed** or **Resume Interrupted** after fixing
an OCR or source-file problem.

Local rules require no API key. Optional cloud enhancement remains off until
explicitly enabled; redact-before-cloud remains enabled.

Install the runtime dependencies, launch `python desktop_app.py`, and choose **Create Project** or **Open Project**. Import source files in Documents, run OCR locally, create claims, review evidence, and use each workspace in order as needed. Cloud AI is optional; enable **Local-only** in Settings to prohibit provider calls. Before major testing, use **Project > Create Backup**.
