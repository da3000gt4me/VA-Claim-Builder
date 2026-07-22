from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class PromotionResult:
    claim_id: str
    created: bool
    condition_name: str
    theory: str
    document_plan: list[dict[str, Any]]

class CandidateClaimPromotionService:
    """Promotes a reviewed discovery candidate into a claim and creates a full-document work plan."""

    DOCUMENT_SET = (
        ("evidence_map", "Claim-specific evidence map"),
        ("personal_statement", "Veteran personal statement"),
        ("historical_timeline", "Historical symptom timeline"),
        ("clinician_nexus_packet", "Specialist nexus review packet"),
        ("buddy_prompts", "Tailored buddy/witness prompts"),
        ("rating_review", "Preliminary rating-criteria review"),
        ("evidence_gap_plan", "Evidence-development action plan"),
        ("submission_integration", "Final-package integration checklist"),
    )

    def promote(self, db, project_id: str, candidate: dict[str, Any], selected_theory: str | None = None) -> PromotionResult:
        name = (candidate.get("condition") or "").strip()
        if not name:
            raise ValueError("Candidate condition is required")
        existing = db.list_claims(project_id)
        for claim in existing:
            if claim["condition_name"].strip().lower() == name.lower():
                return PromotionResult(claim["id"], False, name, claim.get("theory", "unknown"), self._plan(claim["id"], candidate))
        theories = candidate.get("possible_theories") or ["unknown"]
        theory = selected_theory or theories[0]
        claim_id = db.add_claim(project_id, name, theory)
        return PromotionResult(claim_id, True, name, theory, self._plan(claim_id, candidate))

    def _plan(self, claim_id: str, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        return [{
            "claim_id": claim_id,
            "output_type": key,
            "title": title,
            "status": "planned",
            "requires_approved_evidence": True,
            "recommended_specialty": candidate.get("recommended_specialty") if key == "clinician_nexus_packet" else None,
        } for key, title in self.DOCUMENT_SET]
