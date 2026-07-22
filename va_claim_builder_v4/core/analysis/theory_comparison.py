from __future__ import annotations

class ClaimTheoryComparisonEngine:
    THEORIES = {
        "direct": ("current_diagnosis", "in_service_event", "nexus"),
        "secondary": ("current_diagnosis", "primary_service_connected_condition", "nexus"),
        "aggravation": ("current_diagnosis", "baseline_severity", "worsening", "nexus"),
        "presumptive": ("current_diagnosis", "qualifying_service", "manifestation"),
    }
    def compare(self, claim: dict, annotations: list[dict]) -> dict:
        relevant = [a for a in annotations if a.get("claim_id") == claim.get("id") and a.get("review_status") == "approved" and a.get("polarity") == "favorable"]
        elements = {a.get("claim_element") for a in relevant}
        rows = []
        for theory, required in self.THEORIES.items():
            met = [e for e in required if e in elements]
            missing = [e for e in required if e not in elements]
            score = round(len(met) / len(required), 2)
            rows.append({"theory": theory, "score": score, "supported_elements": met, "missing_elements": missing, "status": "supported" if not missing else "partial" if met else "not_supported"})
        rows.sort(key=lambda r: r["score"], reverse=True)
        return {"claim_id": claim.get("id"), "condition": claim.get("condition_name"), "recommended_primary_theory": rows[0]["theory"] if rows and rows[0]["score"] else None, "theories": rows, "warning": "This compares evidence coverage only; legal and medical review remain required."}
