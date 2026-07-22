from __future__ import annotations
import re
from typing import Any

DATE_RE = re.compile(r"\b(?:19|20)\d{2}\b")
MEDICAL_CONCLUSION_RE = re.compile(r"\b(caused by|due to|secondary to|aggravated by|at least as likely as not|nexus)\b", re.I)
DIAGNOSIS_RE = re.compile(r"\b(diagnosed|diagnosis|assessment)\b", re.I)

class DraftFactValidator:
    """Flags draft assertions that are not traceable to the approved fact matrix."""

    def validate(self, draft_text: str, fact_matrix: dict[str, Any], document_type: str) -> dict[str, Any]:
        searchable = " ".join(
            f.get("proposition", "") + " " + f.get("quote", "")
            for rows in fact_matrix.get("facts_by_element", {}).values() for f in rows
        ).lower()
        timeline_text = " ".join(str(e.get("event_date_start") or "") + " " + e.get("description", "") for e in fact_matrix.get("verified_timeline", []) + fact_matrix.get("reported_timeline", [])).lower()
        warnings: list[dict[str, Any]] = []

        for year in sorted(set(DATE_RE.findall(draft_text))):
            if year not in timeline_text and year not in searchable:
                warnings.append({"kind": "unsupported_date", "text": year, "message": f"The year {year} was not found in approved evidence or the historical timeline."})

        if document_type in {"buddy_letter", "personal_statement", "self_nexus"} and MEDICAL_CONCLUSION_RE.search(draft_text):
            warnings.append({"kind": "medical_conclusion_in_lay_draft", "text": MEDICAL_CONCLUSION_RE.search(draft_text).group(0), "message": "Lay-authored text should describe observations and history, not make a medical causation opinion."})

        if DIAGNOSIS_RE.search(draft_text) and not fact_matrix.get("facts_by_element", {}).get("diagnosis"):
            warnings.append({"kind": "unsupported_diagnosis", "text": "diagnosis", "message": "The draft refers to a diagnosis, but no approved diagnosis evidence is available for this claim."})

        open_medical = [f for rows in fact_matrix.get("facts_by_element", {}).values() for f in rows if not f.get("medical_qualified", True)]
        return {
            "valid": not warnings,
            "warnings": warnings,
            "approved_fact_count": fact_matrix.get("draftable_fact_count", 0),
            "nonmedical_facts_requiring_care": len(open_medical),
        }
