from __future__ import annotations
from typing import Any

ELEMENT_ACTIONS = {
    "diagnosis": ("Obtain or identify a current diagnosis from an appropriate clinician.", "required"),
    "in_service_event": ("Identify service records or firsthand lay evidence documenting the in-service event, symptoms, duty, or exposure.", "required"),
    "nexus": ("Obtain a clinician-reviewed opinion that addresses the verified facts, competing causes, and the applicable causal or aggravation theory.", "required"),
    "continuity": ("Add a dated symptom timeline and independent lay or medical anchors explaining continuity and treatment gaps.", "high_value"),
    "functional_impairment": ("Document frequency, duration, limitations, accommodations, missed activities, and occupational or social effects.", "high_value"),
    "severity": ("Obtain condition-specific measurements, frequency logs, standardized scores, or functional findings needed to distinguish rating levels.", "high_value"),
    "primary_service_connected_condition": ("Verify the primary service-connected condition and include the controlling decision or rating documentation.", "required"),
    "aggravation": ("Request an opinion distinguishing causation from permanent or measurable worsening beyond baseline.", "required"),
    "baseline": ("Locate evidence describing severity before aggravation or explain why a reliable baseline cannot be established.", "required"),
}

class EvidenceGapActionPlanner:
    def build(self, claim: dict[str,Any], readiness: dict[str,Any], rating: dict[str,Any], denial: dict[str,Any] | None = None, dbq: dict[str,Any] | None = None) -> dict[str,Any]:
        missing=list(dict.fromkeys(readiness.get("missing_elements",[])+(denial or {}).get("missing_elements",[])))
        actions=[]
        for element in missing:
            text,priority=ELEMENT_ACTIONS.get(element,(f"Develop evidence addressing the missing element: {element.replace('_',' ')}.","high_value"))
            actions.append({"claim_element":element,"priority":priority,"action":text,"source":"readiness_or_denial"})
        if rating.get("profile") and rating.get("levels"):
            partial=[x for x in rating["levels"] if x.get("status")=="partially_supported"]
            for level in partial[-2:]:
                if level.get("missing_concepts"):
                    actions.append({"claim_element":"severity","priority":"high_value","action":f"To evaluate the {level['percentage']}% level, document: "+", ".join(level["missing_concepts"]),"source":"rating_criteria"})
        if dbq:
            for section in dbq.get("missing_core_sections",[]):
                actions.append({"claim_element":section,"priority":"high_value","action":f"The DBQ/C&P extraction did not locate a clear {section.replace('_',' ')} section; verify the original examination and obtain clarification if omitted.","source":"dbq_cp_review"})
        rank={"required":0,"high_value":1,"optional":2}
        actions.sort(key=lambda x:(rank.get(x["priority"],9),x["claim_element"]))
        return {"claim_id":claim["id"],"condition_name":claim["condition_name"],"actions":actions,"ready_when":sorted(set(x["claim_element"] for x in actions if x["priority"]=="required")),"warning":"Recommendations are evidence-development prompts, not a prediction of VA adjudication."}
