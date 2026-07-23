
# VA Claim Builder Version 4.2.0 RC4

RC4 is a functional-correction release candidate. RC3 imported and cataloged
files but did not connect import to the existing OCR, evidence, timeline, claim,
nexus, rating, optimizer, and submission workspaces.

RC4 adds a persistent local-first intake orchestrator, per-document state,
conservative medical metadata extraction, source-linked draft evidence and
timeline events, claim matching and field drafts, claim/relationship
suggestions, contradiction/gap review, deduplication, cancellation/recovery, and
the Automation Review workspace.

No suggestion is a confirmed medical fact. Confirmed user content is not
overwritten. Import makes no cloud call, and tests use no real medical records.

