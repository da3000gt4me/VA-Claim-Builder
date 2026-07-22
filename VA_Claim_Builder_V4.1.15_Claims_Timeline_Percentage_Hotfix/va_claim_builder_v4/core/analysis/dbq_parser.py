from __future__ import annotations
import re
from typing import Any

SECTION_PATTERNS = {
    "diagnosis": (r"diagnos(?:is|es)|current diagnosis",),
    "medical_history": (r"medical history|history of present illness|onset",),
    "symptoms": (r"symptoms?|signs?",),
    "flare_ups": (r"flare[- ]?ups?|repeated use",),
    "functional_impact": (r"functional impact|occupational impact|ability to work",),
    "measurements": (r"range of motion|rom\b|degrees|puretone|speech discrimination|blood pressure",),
    "nexus_opinion": (r"at least as likely as not|less likely than not|medical opinion",),
    "rationale": (r"rationale|reasoning",),
}
NEGATIVE_OPINION = re.compile(r"less likely than not|not at least as likely as not", re.I)
POSITIVE_OPINION = re.compile(r"at least as likely as not", re.I)

class DBQCPParser:
    """Conservative parser for extracted DBQ/C&P text. It never invents missing fields."""
    def parse(self, text: str, source_name: str = "") -> dict[str, Any]:
        clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        lines = clean.splitlines()
        sections: dict[str, list[str]] = {k: [] for k in SECTION_PATTERNS}
        current: str | None = None
        heading_order = ["rationale", "nexus_opinion", "functional_impact", "flare_ups", "measurements", "medical_history", "diagnosis", "symptoms"]
        for line in lines:
            matched = None
            heading = line.split(":", 1)[0].strip() if ":" in line else line[:80]
            for name in heading_order:
                if any(re.search(p, heading, re.I) for p in SECTION_PATTERNS[name]):
                    matched = name; break
            if matched:
                current = matched
            if current:
                sections[current].append(line)
        joined = clean.lower()
        opinion = "not_located"
        if NEGATIVE_OPINION.search(clean): opinion = "unfavorable"
        elif POSITIVE_OPINION.search(clean): opinion = "favorable"
        required = ["diagnosis","medical_history","symptoms","functional_impact"]
        missing = [name for name in required if not sections[name]]
        flags=[]
        if opinion != "not_located" and not sections["rationale"]:
            flags.append("A nexus conclusion was located, but a distinct rationale section was not identified.")
        if "flare" in joined and not sections["flare_ups"]:
            flags.append("Flare-up language may be present but was not confidently assigned to a flare-up section.")
        return {
            "source_name": source_name,
            "document_type": "dbq_or_cp_exam",
            "sections": {k:"\n".join(v[:30]) for k,v in sections.items() if v},
            "opinion_polarity": opinion,
            "missing_core_sections": missing,
            "review_flags": flags,
            "requires_human_verification": True,
        }
