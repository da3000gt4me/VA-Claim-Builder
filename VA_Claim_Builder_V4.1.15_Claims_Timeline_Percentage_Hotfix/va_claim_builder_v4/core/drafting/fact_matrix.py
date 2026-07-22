from __future__ import annotations
from collections import defaultdict
from typing import Any

MEDICAL_ONLY_ELEMENTS = {"diagnosis", "nexus", "causation", "aggravation", "baseline_severity"}

class ApprovedFactMatrix:
    """Build a conservative, source-traceable fact set for drafting."""

    def build(self, claim: dict[str, Any], annotations: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> dict[str, Any]:
        claim_id = claim["id"]
        approved = [a for a in annotations if a.get("claim_id") == claim_id and a.get("review_status") == "approved"]
        favorable = [a for a in approved if a.get("polarity") == "favorable"]
        limiting = [a for a in approved if a.get("polarity") in {"unfavorable", "ambiguous"}]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for a in favorable:
            grouped[a.get("claim_element", "other")].append(self._normalize_fact(a))

        events = [e for e in timeline if e.get("claim_id") == claim_id]
        verified_events = [e for e in events if e.get("source_type") in {"medical_verified", "military_verified", "administrative_verified"}]
        reported_events = [e for e in events if e.get("source_type") in {"veteran_reported", "witness_reported"}]

        return {
            "claim_id": claim_id,
            "condition_name": claim.get("condition_name", ""),
            "theory": claim.get("theory", "unknown"),
            "facts_by_element": dict(grouped),
            "verified_timeline": sorted(verified_events, key=lambda x: x.get("event_date_start") or "9999"),
            "reported_timeline": sorted(reported_events, key=lambda x: x.get("event_date_start") or "9999"),
            "limiting_evidence": [self._normalize_fact(a) for a in limiting],
            "draftable_fact_count": len(favorable),
            "guardrails": [
                "Use only approved evidence and identified reported history.",
                "Do not convert veteran or witness observations into a medical diagnosis or medical nexus opinion.",
                "A clinician must independently select, revise, and sign any medical opinion.",
                "Preserve uncertainty when dates are approximate or conflicting.",
            ],
        }

    def _normalize_fact(self, a: dict[str, Any]) -> dict[str, Any]:
        category = a.get("category", "unknown")
        element = a.get("claim_element", "other")
        authority = "medical" if category == "medical_records" else "lay" if category in {"buddy_letters", "personal_timelines", "statements_support_claim"} else "administrative"
        medical_qualified = authority == "medical" or element not in MEDICAL_ONLY_ELEMENTS
        return {
            "annotation_id": a.get("id"),
            "element": element,
            "proposition": a.get("finding", ""),
            "quote": a.get("quote") or "",
            "document_name": a.get("document_name") or "",
            "page": a.get("page"),
            "category": category,
            "authority": authority,
            "medical_qualified": medical_qualified,
            "confidence": float(a.get("confidence", 0.0)),
            "citation": self._citation(a),
        }

    @staticmethod
    def _citation(a: dict[str, Any]) -> str:
        page = a.get("page")
        return f"{a.get('document_name') or 'Source document'}" + (f", p. {page}" if page else "")
