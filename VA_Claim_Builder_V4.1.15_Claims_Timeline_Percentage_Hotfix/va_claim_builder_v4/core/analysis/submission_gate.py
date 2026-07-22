from __future__ import annotations
from typing import Any

class SubmissionReadinessGate:
    def assess(self, claim: dict[str,Any], readiness: dict[str,Any], rating: dict[str,Any], contradictions: list[dict[str,Any]], documents: list[dict[str,Any]]) -> dict[str,Any]:
        blockers=[]; warnings=[]
        if readiness.get("missing_elements"): blockers.append("Required claim elements remain unsupported: "+", ".join(readiness["missing_elements"]))
        open_conf=[c for c in contradictions if c.get("claim_id")==claim["id"] and c.get("status","open")=="open"]
        if open_conf: blockers.append(f"{len(open_conf)} unresolved contradiction(s)")
        unsigned=[d for d in documents if d.get("signed_status") in {"unsigned","draft"} and d.get("include_in_final")]
        if unsigned: blockers.append(f"{len(unsigned)} draft/unsigned document(s) are marked for final inclusion")
        low_ocr=[d for d in documents if d.get("ocr_confidence") is not None and float(d["ocr_confidence"])<0.65 and d.get("include_in_final")]
        if low_ocr: warnings.append(f"{len(low_ocr)} included document(s) have low OCR confidence")
        if rating.get("profile") is None: warnings.append("No verified rating-criteria profile is mapped")
        return {"claim_id":claim["id"],"condition_name":claim["condition_name"],"blocked":bool(blockers),"blockers":blockers,"warnings":warnings,
                "status":"blocked" if blockers else ("review_with_warnings" if warnings else "ready_for_human_final_review")}
