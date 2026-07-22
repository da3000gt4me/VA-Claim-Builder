from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable

@dataclass
class AdversarialFinding:
    category: str
    severity: str
    claim_id: str
    issue: str
    why_it_matters: str
    recommended_fix: str
    source_refs: list[str]

class AdversarialReviewEngine:
    """Challenges the package instead of trying to strengthen it."""
    def review(self, claim: dict, annotations: Iterable[dict], timeline: Iterable[dict], contradictions: Iterable[dict]) -> dict:
        cid = claim.get("id", "")
        relevant = [a for a in annotations if a.get("claim_id") == cid and a.get("review_status") == "approved"]
        favorable = [a for a in relevant if a.get("polarity") == "favorable"]
        unfavorable = [a for a in relevant if a.get("polarity") == "unfavorable"]
        findings: list[AdversarialFinding] = []
        required = {
            "direct": ["current_diagnosis", "in_service_event", "nexus"],
            "secondary": ["current_diagnosis", "primary_service_connected_condition", "nexus"],
            "aggravation": ["current_diagnosis", "baseline_severity", "worsening", "nexus"],
            "presumptive": ["current_diagnosis", "qualifying_service", "manifestation"],
        }.get(claim.get("theory"), ["current_diagnosis", "in_service_event", "nexus"])
        elements = {a.get("claim_element") for a in favorable}
        for element in required:
            if element not in elements:
                findings.append(AdversarialFinding("missing_element", "high", cid, f"No approved favorable evidence for {element.replace('_',' ')}.", "A rater may find a required service-connection element unproven.", f"Obtain or identify competent evidence addressing {element.replace('_',' ')}.", []))
        for a in unfavorable:
            findings.append(AdversarialFinding("unfavorable_evidence", "medium", cid, a.get("finding", "Unfavorable evidence exists."), "Unaddressed negative evidence can undermine credibility or medical reasoning.", "Reconcile this finding with dates, context, and competent evidence; do not omit it.", [self._ref(a)]))
        open_conflicts = [c for c in contradictions if c.get("status", "open") == "open" and (not c.get("claim_id") or c.get("claim_id") == cid)]
        for c in open_conflicts:
            findings.append(AdversarialFinding("contradiction", c.get("severity", "medium"), cid, c.get("summary", "Open contradiction"), "Inconsistent histories may reduce probative value.", c.get("resolution_prompt", "Resolve and document the discrepancy."), []))
        medical_nexus = [a for a in favorable if a.get("claim_element") == "nexus" and a.get("source_authority") in {"clinician", "medical_record", "specialist"}]
        if claim.get("theory") in {"direct", "secondary", "aggravation", "multiple"} and not medical_nexus:
            findings.append(AdversarialFinding("competency", "high", cid, "No approved competent medical nexus finding was located.", "Lay belief or AI-generated rationale generally cannot replace a qualified medical opinion on complex causation.", "Obtain an independently reviewed and signed clinician opinion with a reasoned rationale.", []))
        unsupported_precision = []
        for t in timeline:
            if t.get("claim_id") == cid and t.get("source_type") in {"veteran_reported", "witness_reported"} and t.get("date_precision") == "exact" and not t.get("corroborated"):
                unsupported_precision.append(t)
        if unsupported_precision:
            findings.append(AdversarialFinding("timeline_precision", "low", cid, "Exact dates are asserted from recollection without identified corroboration.", "Overprecision can create avoidable inconsistencies with treatment records.", "Use an honest approximate range unless the exact date is supported.", [str(x.get("source_ref", "")) for x in unsupported_precision if x.get("source_ref")]))
        score = max(0, 100 - sum({"high": 22, "medium": 10, "low": 4}.get(f.severity, 6) for f in findings))
        return {"claim_id": cid, "condition": claim.get("condition_name"), "defensibility_score": score, "findings": [asdict(f) for f in findings], "status": "pass" if not findings else "requires_review"}

    @staticmethod
    def _ref(a: dict) -> str:
        name = a.get("document_name") or a.get("filename") or "source"
        page = a.get("page")
        return f"{name} p.{page}" if page else name
