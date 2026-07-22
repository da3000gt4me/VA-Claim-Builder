from __future__ import annotations
class FinalCloseoutChecklist:
    def assess(self, health: dict, security: dict, claims: list[dict], gates: list[dict], audit: dict) -> dict:
        blockers=[]
        if health.get("overall") != "ready": blockers.append("System health is not ready.")
        if security.get("status") in {"fail","blocked"}: blockers.append("Security review failed.")
        if not claims: blockers.append("No active claims exist.")
        blockers += [f"Claim blocked: {g.get('condition') or g.get('claim_id')}" for g in gates if g.get("status") == "blocked"]
        if audit and not audit.get("all_present", True): blockers.append("One or more final files are missing.")
        return {"ready_to_close": not blockers, "blockers": blockers, "remaining_recommendations": ["Obtain clinician signatures where required.", "Have a VA-accredited representative perform an optional final review.", "Re-run legal and regulatory verification immediately before filing.", "Preserve the final checksum-backed archive and VA submission receipt."]}
