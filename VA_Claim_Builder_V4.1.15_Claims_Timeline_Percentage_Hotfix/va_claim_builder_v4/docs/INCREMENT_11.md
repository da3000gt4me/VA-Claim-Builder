# Increment 11 — Potential Unclaimed Conditions Discovery

Adds a conservative cross-record discovery module that compares existing claims, military duties/exposures, military medical history, current diagnoses/findings, and approved lay timelines.

## Guardrails
- Requires affirmative current evidence and a service-history anchor.
- Negated findings are excluded.
- Existing claimed conditions are not re-suggested.
- Results are hypotheses for human review, not diagnoses or nexus opinions.
- The generated prompt asks whether the user wants the complete document set built for selected additional claims.
