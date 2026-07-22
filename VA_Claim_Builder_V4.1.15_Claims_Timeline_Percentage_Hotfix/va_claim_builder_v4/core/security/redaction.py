from __future__ import annotations
import re

PATTERNS = {
    "ssn": re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "dob": re.compile(r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"),
}

def redact_identifiers(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for label, pattern in PATTERNS.items():
        text, count = pattern.subn(f"[REDACTED_{label.upper()}]", text)
        counts[label] = count
    return text, counts
