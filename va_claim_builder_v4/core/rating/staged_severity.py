from __future__ import annotations
from collections import defaultdict
from typing import Any

SEVERITY_TERMS = {
    "mild": 1, "occasional": 1, "moderate": 2, "monthly": 2, "frequent": 3,
    "severe": 4, "prostrating": 4, "incapacitating": 4, "total": 5,
}

class StagedSeverityAnalyzer:
    def analyze(self, claim_id: str, annotations: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> dict[str, Any]:
        periods: dict[str,list[dict[str,Any]]] = defaultdict(list)
        for event in timeline:
            if event.get("claim_id") != claim_id: continue
            date=str(event.get("event_date_start") or "unknown")
            period=date[:4] if len(date)>=4 and date[:4].isdigit() else "unknown"
            periods[period].append({"source":"timeline","text":event.get("description","")})
        for ann in annotations:
            if ann.get("claim_id") != claim_id or ann.get("review_status") != "approved": continue
            date=str(ann.get("encounter_date") or ann.get("created_at") or "unknown")
            period=date[:4] if len(date)>=4 and date[:4].isdigit() else "unknown"
            periods[period].append({"source":ann.get("document_name",ann.get("document_id")),"text":ann.get("finding","")})
        stages=[]
        for period,items in sorted(periods.items(), key=lambda x:(x[0]=="unknown",x[0])):
            joined=" ".join(i["text"].lower() for i in items)
            hits={term:score for term,score in SEVERITY_TERMS.items() if term in joined}
            stages.append({"period":period,"severity_index":max(hits.values(),default=0),"severity_terms":sorted(hits),"evidence_count":len(items),"evidence":items})
        changed=len({s["severity_index"] for s in stages if s["severity_index"]>0})>1
        return {"claim_id":claim_id,"stages":stages,"possible_staged_severity":changed,
                "warning":"Severity stages are a review aid, not an effective-date or rating determination."}
