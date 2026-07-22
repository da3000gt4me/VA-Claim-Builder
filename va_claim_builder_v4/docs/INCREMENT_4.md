# Increment 4 — Semantic Evidence Review

This increment replaces keyword-driven evidence review with proposition-level classification.

## Core behavior
- Negated findings such as “denies anxiety/depression” are never offered as favorable evidence.
- Routine screening, review-of-systems, templated, and keyword-only passages are suppressed or routed to manual review.
- Auto-population requires an affirmative proposition supporting diagnosis, treatment, severity, functional impact, or continuity.
- Negative evidence remains visible as dated context but is kept out of favorable auto-fill.
- Every candidate explains why it was included, excluded, suppressed, or held for manual review.
- Only high-value candidates can create pending annotations; human approval remains mandatory.
