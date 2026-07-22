from __future__ import annotations
from typing import Any
from core.analysis.readiness import ReadinessEngine
from core.analysis.submission_gate import SubmissionReadinessGate
from core.rating.criteria_engine import RatingCriteriaEngine

class ProjectOrchestrator:
    """Produces a deterministic project-wide next-action plan from current reviewed data."""
    def build_plan(self, db, project_id: str) -> dict[str, Any]:
        claims=db.list_claims(project_id); docs=db.list_documents(project_id)
        anns=db.list_annotations(project_id); approved=db.list_annotations_enriched(project_id,status="approved")
        timeline=db.list_timeline(project_id); conflicts=db.list_contradictions(project_id)
        ready_engine=ReadinessEngine(); rating_engine=RatingCriteriaEngine(); gate_engine=SubmissionReadinessGate()
        rows=[]; required=[]
        for claim in claims:
            readiness=ready_engine.assess(claim,anns,timeline,conflicts)
            rating=rating_engine.evaluate(claim,approved,timeline)
            gate=gate_engine.assess(claim,readiness,rating,conflicts,docs)
            rows.append({"claim_id":claim["id"],"condition":claim["condition_name"],"readiness":readiness,"rating":rating,"gate":gate})
            if gate.get("status") == "blocked":
                required.append({"claim":claim["condition_name"],"action":"Resolve blocking readiness items","details":gate.get("blockers",[])})
            elif gate.get("status") != "ready_for_human_final_review":
                required.append({"claim":claim["condition_name"],"action":"Complete final human review","details":gate.get("warnings",[])})
        low_ocr=[x for x in db.list_chunks(project_id,needs_review=True)]
        pending=[x for x in anns if x.get("review_status")=="pending"]
        if low_ocr: required.insert(0,{"claim":"Project-wide","action":"Review low-confidence OCR pages","details":[f"{len(low_ocr)} page(s) require review"]})
        if pending: required.insert(0,{"claim":"Project-wide","action":"Review pending evidence annotations","details":[f"{len(pending)} finding(s) await approval"]})
        return {"claims":rows,"next_actions":required,"summary":{"claim_count":len(claims),"document_count":len(docs),"approved_findings":len(approved),"pending_findings":len(pending),"low_confidence_pages":len(low_ocr),"open_conflicts":len([c for c in conflicts if c.get('status')=='open'])},"ready_for_final_assembly":bool(claims) and not required}
