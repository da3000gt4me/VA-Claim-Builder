from __future__ import annotations
from collections import defaultdict
from typing import Any
from core.analysis.corroboration import CrossDocumentCorroborator
from core.analysis.timeline_consistency import TimelineConsistencyEngine

class ClaimSynthesisEngine:
    """Produces a conservative evidence synthesis from approved facts only."""
    def build(self, claim:dict[str,Any], annotations:list[dict[str,Any]], timeline:list[dict[str,Any]], contradictions:list[dict[str,Any]])->dict[str,Any]:
        claim_anns=[a for a in annotations if a.get('claim_id')==claim['id'] and a.get('review_status')=='approved']
        clusters=CrossDocumentCorroborator().build(claim_anns)
        favorable=[c for c in clusters if c['polarity']=='favorable']
        unfavorable=[c for c in clusters if c['polarity']=='unfavorable']
        by_element=defaultdict(list)
        for c in favorable: by_element[c['claim_element']].append(c)
        ties=[]
        for element,rows in by_element.items():
            best=max(rows,key=lambda x:x['corroboration_score'])
            ties.append({"claim_element":element,"proposition":best['proposition'],"strength":best['strength'],"score":best['corroboration_score'],"sources":best['source_names'],"why_it_matters":self._why(element)})
        timeline_result=TimelineConsistencyEngine().assess(claim['id'],timeline)
        open_conflicts=[c for c in contradictions if c.get('claim_id') in {None,claim['id']} and c.get('status')=='open']
        required=self._required(claim.get('theory','unknown'))
        present=set(by_element)
        missing=[x for x in required if x not in present]
        bridges=list(timeline_result['bridges'])
        if {'diagnosis','continuity'}<=present: bridges.append('Approved evidence connects a current diagnosed condition with documented persistence or progression over time.')
        if {'in_service_event','continuity'}<=present: bridges.append('Approved evidence links an in-service event/exposure to a continuing post-service symptom history, without treating lay evidence as a medical nexus opinion.')
        if {'primary_condition','causation'}<=present: bridges.append('The secondary theory has approved evidence identifying both the primary condition and a claimed causal relationship for clinician review.')
        return {"claim_id":claim['id'],"condition_name":claim['condition_name'],"theory":claim.get('theory'),"clear_ties":sorted(ties,key=lambda x:-x['score']),"timeline":timeline_result,"bridge_statements":bridges,"missing_elements":missing,"negative_context":unfavorable,"open_conflicts":open_conflicts,"drafting_status":"ready for evidence-grounded drafting" if not missing and not open_conflicts else "requires targeted development or reconciliation","guardrail":"This synthesis reports what approved evidence supports. It does not create a medical opinion or guarantee a VA outcome."}

    @staticmethod
    def _required(theory):
        return {'direct':['diagnosis','in_service_event','nexus'],'secondary':['diagnosis','primary_condition','causation'],'aggravation':['preexisting_condition','baseline','in_service_worsening','natural_progression_opinion'],'presumptive':['diagnosis','qualifying_service','timely_manifestation'],'multiple':['diagnosis','in_service_event','nexus'],'unknown':['diagnosis','nexus']}.get(theory,['diagnosis','nexus'])
    @staticmethod
    def _why(element):
        return {'diagnosis':'Establishes the current-disability element.','in_service_event':'Establishes the relevant event, injury, exposure, or symptom during service.','continuity':'Helps explain persistence between service, treatment, and current disability.','nexus':'Addresses the relationship between service and the current condition.','severity':'Documents frequency, duration, intensity, or measured severity.','functional_impact':'Shows occupational and social impairment or limits on daily activities.','treatment':'Shows clinical recognition and management over time.','objective_finding':'Provides measurable or diagnostic confirmation.','primary_condition':'Identifies the disability alleged to cause or aggravate the secondary condition.','causation':'Addresses secondary causation.','aggravation':'Addresses worsening beyond baseline.'}.get(element,'Supports a defined factual element of the claim.')
