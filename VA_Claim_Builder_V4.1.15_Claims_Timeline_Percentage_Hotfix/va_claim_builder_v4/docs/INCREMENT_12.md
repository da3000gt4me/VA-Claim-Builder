# Increment 12 — Integrated Automation, Candidate Promotion, and Recovery

This increment closes the gap between discovering a potential unclaimed condition and building the full associated claim workstream.

## Added

- Reviewed-candidate promotion into the active claim list
- Idempotent protection against duplicate claim creation
- Automatic eight-product document plan for each promoted claim
- Project-wide orchestration report showing exact remaining blockers
- Checksum-backed portable project backups with validation
- Streamlit workspace for promotion, automation status, and backup download

A discovery candidate is never filed automatically. The user must select it for promotion, and all generated documents remain subject to evidence approval and clinician/witness review.
