from __future__ import annotations
from collections import defaultdict

ELEMENTS={
 'direct':['diagnosis','in_service_event','nexus','continuity','severity','functional_impact','treatment','objective_finding'],
 'secondary':['diagnosis','primary_service_connected_condition','causation','aggravation','nexus','severity','functional_impact','treatment','objective_finding'],
 'aggravation':['preexisting_condition','baseline','in_service_worsening','natural_progression','nexus','severity','functional_impact'],
 'presumptive':['diagnosis','qualifying_service','manifestation','severity','functional_impact'],
 'multiple':['diagnosis','in_service_event','nexus','continuity','severity','functional_impact','treatment','objective_finding'],
 'unknown':['diagnosis','event_or_primary_condition','nexus','continuity','severity','functional_impact']}

class ClaimElementSummary:
    def build(self, claim:dict, annotations:list[dict], candidates:list[dict]|None=None):
        theory=claim.get('theory','unknown'); required=ELEMENTS.get(theory,ELEMENTS['unknown']); grouped=defaultdict(list)
        for a in annotations:
            if a.get('claim_id')==claim.get('id') and a.get('polarity')=='favorable': grouped[a.get('claim_element')].append(a)
        suggested=defaultdict(list)
        for c in candidates or []:
            if c.get('auto_action')=='suggest_for_autofill' and c.get('polarity')=='favorable': suggested[c.get('claim_element')].append(c)
        rows=[]
        for e in required:
            approved=[x for x in grouped[e] if x.get('review_status')=='approved']; pending=[x for x in grouped[e] if x.get('review_status')=='pending']
            status='supported' if approved else ('pending_review' if pending or suggested[e] else 'not_found')
            rows.append({'claim_element':e,'status':status,'approved_count':len(approved),'pending_count':len(pending),'suggested_count':len(suggested[e]),'best_support':(approved or pending or suggested[e] or [{}])[0].get('finding') or (approved or pending or suggested[e] or [{}])[0].get('proposition','')})
        return rows
