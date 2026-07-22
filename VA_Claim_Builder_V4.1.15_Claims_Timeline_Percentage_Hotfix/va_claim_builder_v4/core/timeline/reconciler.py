from __future__ import annotations
from datetime import date
from core.timeline.models import TimelineConflict

ONSET_TYPES = {"onset", "diagnosis"}

def _year(value: str | None) -> int | None:
    if not value: return None
    try: return int(value[:4])
    except (ValueError, TypeError): return None

def reconcile_events(events: list[dict]) -> list[TimelineConflict]:
    conflicts: list[TimelineConflict] = []
    by_claim: dict[str, list[dict]] = {}
    for event in events:
        by_claim.setdefault(event.get("claim_id") or "unassigned", []).append(event)
    for claim_id, group in by_claim.items():
        onset = [e for e in group if e.get("event_type") in ONSET_TYPES and _year(e.get("event_date_start"))]
        if len(onset) >= 2:
            years = [_year(e.get("event_date_start")) for e in onset]
            if max(years) - min(years) >= 3:
                veteran = [e for e in onset if e.get("source_type") == "veteran_reported"]
                clinical = [e for e in onset if e.get("source_type") == "medical_verified"]
                wording = "Clarify whether the later date reflects first treatment or formal diagnosis rather than true symptom onset."
                if veteran and clinical:
                    wording = "The veteran-reported onset predates the medical-record date. Clarify whether the medical date is first documented treatment, specialist evaluation, or formal diagnosis."
                conflicts.append(TimelineConflict(conflict_type="onset_date_discrepancy", event_ids=[e["id"] for e in onset],
                    summary=f"Claim {claim_id} contains materially different onset/diagnosis years: {sorted(set(years))}.",
                    resolution_prompt=wording, severity="high"))
        for event in group:
            if event.get("date_precision") == "exact" and not event.get("event_date_start"):
                conflicts.append(TimelineConflict(conflict_type="missing_exact_date", event_ids=[event["id"]],
                    summary="An event marked exact has no date.", resolution_prompt="Enter the exact date or change the precision to approximate/unknown.", severity="medium"))
    return conflicts
