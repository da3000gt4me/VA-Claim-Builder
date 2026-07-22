from __future__ import annotations
from typing import Any

REQUIRED = {
    "direct": ["diagnosis", "in_service_event", "nexus"],
    "secondary": ["diagnosis", "primary_service_connected_condition", "nexus"],
    "aggravation": ["diagnosis", "baseline", "worsening", "nexus"],
    "presumptive": ["diagnosis", "qualifying_service", "manifestation"],
    "unknown": ["diagnosis", "nexus"],
    "multiple": ["diagnosis", "nexus"],
}

class ReadinessEngine:
    def assess(self, claim: dict[str, Any], annotations: list[dict[str, Any]], timeline: list[dict[str, Any]], contradictions: list[dict[str, Any]]) -> dict[str, Any]:
        approved = [a for a in annotations if a.get("review_status") == "approved" and a.get("claim_id") == claim["id"]]
        elements = {a.get("claim_element") for a in approved if a.get("polarity") == "favorable"}
        required = REQUIRED.get(claim.get("theory", "unknown"), REQUIRED["unknown"])
        missing = [e for e in required if e not in elements]
        claim_contras = [c for c in contradictions if c.get("claim_id") == claim["id"]]
        timeline_count = len([e for e in timeline if e.get("claim_id") == claim["id"]])
        score = max(0, 100 - 25*len(missing) - 10*len(claim_contras) + min(10, timeline_count*2))
        return {"claim_id": claim["id"], "condition_name": claim["condition_name"], "theory": claim.get("theory"),
                "score": score, "required_elements": required, "supported_elements": sorted(elements), "missing_elements": missing,
                "approved_evidence_count": len(approved), "timeline_event_count": timeline_count,
                "contradiction_count": len(claim_contras), "status": "ready_for_final_review" if score >= 80 and not missing else "development_needed"}
