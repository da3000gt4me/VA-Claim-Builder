from __future__ import annotations
import re
from typing import Any

FAVORABLE_MARKERS=("favorable finding", "diagnosed", "current disability", "qualifying event", "exposure conceded")
DENIAL_MARKERS=("denied because", "service connection is denied", "no nexus", "not related to service", "no evidence", "did not occur in service")

class DenialDecisionAnalyzer:
    def analyze_text(self, text: str, claim_name: str = "") -> dict[str, Any]:
        sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+",text) if s.strip()]
        favorable=[s for s in sentences if any(m in s.lower() for m in FAVORABLE_MARKERS)]
        denial=[s for s in sentences if any(m in s.lower() for m in DENIAL_MARKERS)]
        missing=[]
        low=" ".join(denial).lower()
        if "no nexus" in low or "not related" in low: missing.append("nexus")
        if "no current" in low or "no diagnosis" in low: missing.append("diagnosis")
        if "did not occur in service" in low or "no in-service" in low: missing.append("in_service_event")
        actions=[]
        for element in missing:
            actions.append({"element":element,"recommended_response":{
                "nexus":"Obtain a clinician-reviewed opinion that addresses the denial rationale, relevant favorable evidence, competing causes, and the complete timeline.",
                "diagnosis":"Provide current diagnostic evidence and identify the date, provider, and objective basis for the diagnosis.",
                "in_service_event":"Corroborate the event, duty, exposure, symptoms, or circumstances through military records and competent lay evidence.",
            }[element]})
        return {"claim_name":claim_name,"favorable_findings":favorable,"denial_reasons":denial,"missing_elements":sorted(set(missing)),"response_actions":actions,
                "warning":"Heuristic extraction. Compare every item to the original decision letter before use."}
