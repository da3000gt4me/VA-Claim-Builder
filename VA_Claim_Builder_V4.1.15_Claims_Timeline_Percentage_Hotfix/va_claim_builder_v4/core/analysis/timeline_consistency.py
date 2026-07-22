from __future__ import annotations
from collections import Counter
from datetime import datetime
from typing import Any

SOURCE_TRUST={"medical_verified":1.0,"military_verified":1.0,"administrative_verified":.95,"witness_reported":.72,"veteran_reported":.68,"ai_extracted":.45}

class TimelineConsistencyEngine:
    def assess(self, claim_id:str, events:list[dict[str,Any]])->dict[str,Any]:
        rows=[e for e in events if e.get("claim_id")==claim_id]
        if not rows:
            return {"claim_id":claim_id,"score":0.0,"status":"no timeline","earliest_supported_onset":None,"supporting_sources":0,"issues":["No claim-specific timeline events recorded."],"bridges":[]}
        issues=[]; bridges=[]
        onset=[e for e in rows if e.get('event_type')=='onset']
        years=[self._year(e.get('event_date_start')) for e in onset]; years=[y for y in years if y]
        if len(set(years))>1 and max(years)-min(years)>3:
            issues.append(f"Reported onset years vary from {min(years)} to {max(years)}; clarify whether later dates refer to diagnosis or treatment rather than first symptoms.")
        types={e.get('source_type','unknown') for e in rows}
        verified=sum(1 for e in rows if SOURCE_TRUST.get(e.get('source_type'),.4)>=.9)
        observed=sum(1 for e in rows if e.get('source_type') in {'veteran_reported','witness_reported'})
        event_types=Counter(e.get('event_type') for e in rows)
        if onset and not any(e.get('event_type') in {'continuity','treatment','worsening','diagnosis'} for e in rows):
            issues.append("Onset is described, but the timeline lacks later continuity, treatment, worsening, or diagnosis events.")
        if observed and verified:
            bridges.append("Lay-reported onset or progression is independently anchored by dated medical, military, or administrative evidence.")
        if event_types['onset'] and event_types['diagnosis']:
            bridges.append("The timeline distinguishes first symptoms from the later formal diagnosis date.")
        trust=sum(SOURCE_TRUST.get(e.get('source_type'),.4)*float(e.get('confidence') or .5) for e in rows)/len(rows)
        completeness=min(1.0,len(event_types)/5)
        diversity=min(1.0,len(types)/3)
        penalty=min(.45,.12*len(issues))
        score=max(0,min(1,.48*trust+.27*completeness+.25*diversity-penalty))
        status='consistent' if score>=.72 and not issues else ('usable with clarification' if score>=.48 else 'insufficient or conflicting')
        return {"claim_id":claim_id,"score":round(score,3),"status":status,"earliest_supported_onset":str(min(years)) if years else None,"supporting_sources":len(types),"issues":issues,"bridges":bridges}

    @staticmethod
    def _year(value):
        if not value:return None
        s=str(value)
        try:return int(s[:4]) if len(s)>=4 and s[:4].isdigit() else None
        except:return None
