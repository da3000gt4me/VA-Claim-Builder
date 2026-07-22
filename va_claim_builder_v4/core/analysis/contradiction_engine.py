from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class Contradiction:
    claim_id: str | None
    kind: str
    severity: str
    summary: str
    left_source: str
    right_source: str
    resolution_prompt: str

class ContradictionEngine:
    NEGATORS = {"denies", "no", "without", "negative for", "resolved"}
    SEVERITY = {"mild": 1, "moderate": 2, "severe": 3, "prostrating": 4}

    def analyze(self, annotations: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found: list[Contradiction] = []
        by_claim: dict[str | None, list[dict[str, Any]]] = {}
        for item in annotations: by_claim.setdefault(item.get("claim_id"), []).append(item)
        for claim_id, items in by_claim.items():
            positives = [x for x in items if x.get("polarity") == "favorable"]
            negatives = [x for x in items if x.get("polarity") == "unfavorable"]
            for p in positives:
                for n in negatives:
                    if p.get("claim_element") == n.get("claim_element"):
                        found.append(Contradiction(claim_id, "evidence_polarity", "high",
                            f"Conflicting {p.get('claim_element')} evidence.", p.get("id","positive"), n.get("id","negative"),
                            "Explain whether the records describe different dates, contexts, treatment states, or an actual inconsistency."))
        onset = [e for e in timeline if e.get("event_type") == "onset" and e.get("event_date_start")]
        for i, left in enumerate(onset):
            for right in onset[i+1:]:
                if left.get("claim_id") == right.get("claim_id") and left["event_date_start"] != right["event_date_start"]:
                    found.append(Contradiction(left.get("claim_id"), "onset_date", "high",
                        f"Different onset dates: {left['event_date_start']} and {right['event_date_start']}.", left.get("id","timeline"), right.get("id","timeline"),
                        "Clarify whether one date is symptom onset, worsening, first treatment, or formal diagnosis."))
        return [asdict(x) for x in found]
