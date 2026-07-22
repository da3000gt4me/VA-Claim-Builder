from __future__ import annotations
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Any

NEGATIVE_PATTERNS = [
    r"\bdenies?\b.{0,60}\b(anxiety|depression|depressed mood|panic|suicidal ideation)\b",
    r"\bno\b.{0,45}\b(anxiety|depression|depressed mood|panic|psychiatric symptoms)\b",
    r"\bnegative for\b.{0,45}\b(anxiety|depression|psychiatric symptoms)\b",
    r"\bwithout\b.{0,45}\b(anxiety|depression|psychiatric symptoms)\b",
]
SCREENING_PATTERNS = [r"\bphq[- ]?2\b", r"\bdepression screen\b", r"\breview of systems\b", r"\bros\b", r"\bpsychiatric:\s*(negative|normal)\b"]
AFFIRMATIVE_PATTERNS = {
    "diagnosis": [
        r"\bdiagnos(?:is|ed|es)\b.{0,55}\b(anxiety|depression|depressive disorder|adjustment disorder|panic disorder)\b",
        r"\b(anxiety disorder|major depressive disorder|persistent depressive disorder|depressive disorder|adjustment disorder|panic disorder)\b",
        r"\bassessment\b.{0,45}\b(anxiety|depression|depressive disorder)\b",
    ],
    "treatment": [
        r"\b(started|continues?|prescribed|taking|treated with|therapy|counseling|increased|decreased)\b.{0,80}\b(sertraline|zoloft|escitalopram|lexapro|fluoxetine|prozac|bupropion|wellbutrin|venlafaxine|effexor|duloxetine|cymbalta|buspirone|anxiety|depression)\b",
        r"\b(psychiatry|psychology|mental health|behavioral health|counseling|psychotherapy)\b.{0,55}\b(follow[- ]?up|treatment|visit|referral|session)\b",
    ],
    "severity": [
        r"\b(mild|moderate|severe)\b.{0,35}\b(anxiety|depression|depressive symptoms)\b",
        r"\b(phq[- ]?9|gad[- ]?7)\b.{0,25}\b(score|=|:)\s*\d+",
        r"\b(panic attacks?|sleep disturbance|impaired concentration|low motivation|anhedonia|irritability|social withdrawal|suicidal ideation)\b",
    ],
    "functional_impact": [
        r"\b(anxiety|depression|mood|panic)\b.{0,120}\b(work|attendance|productivity|relationships?|marriage|family|social|concentration|sleep|daily activities)\b",
        r"\b(missed work|unable to work|difficulty working|reduced productivity|isolat(?:es|ion)|avoids? people|relationship strain)\b",
    ],
    "continuity": [
        r"\b(since|began|started|ongoing|chronic|persistent|continued|worsened)\b.{0,90}\b(anxiety|depression|depressed mood|panic|mental health symptoms)\b",
        r"\b(anxiety|depression|depressed mood|panic)\b.{0,90}\b(since|began|started|ongoing|chronic|persistent|continued|worsened)\b",
    ],
}
BOILERPLATE_HINTS = ["review of systems", "all other systems", "psychiatric: negative", "normal mood and affect", "template"]
NEW_INFORMATION_PATTERNS = [r"\b(score|measured|today|currently|worsened|improved|started|stopped|increased|decreased|referred|plan)\b", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"]

@dataclass
class SemanticCandidate:
    page_id: str; document_id: str; document_name: str; page: int
    claim_id: str; claim_name: str; claim_element: str; polarity: str
    finding: str; quote: str; relevance_score: float; evidentiary_weight: str
    context_type: str; auto_action: str; reason: str
    proposition: str; supports_because: str; limitations: str
    source_authority: str; temporal_context: str
    copy_forward_risk: str = "low"; repeat_count: int = 1
    ocr_confidence: float | None = None

    def model_dump(self) -> dict[str, Any]: return asdict(self)

class SemanticEvidenceAnalyzer:
    """Conservative proposition-based classifier.

    It only suggests passages that assert a fact relevant to a claim element. Negated,
    templated, copied, incidental, and keyword-only text stays visible but cannot become
    favorable support automatically.
    """
    def analyze_chunks(self, claim: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        passage_counts = Counter()
        prepared=[]
        for chunk in chunks:
            text=self._normalize(chunk.get("text", ""))
            passages=self._passages(text)
            prepared.append((chunk,passages))
            passage_counts.update(self._fingerprint(p) for p in passages if len(p)>35)
        candidates=[]; mental=self._is_mental_health_claim(claim.get("condition_name", ""))
        for chunk, passages in prepared:
            for passage in passages:
                repeat_count=passage_counts[self._fingerprint(passage)]
                item=(self._mental_health_candidate if mental else self._generic_candidate)(claim,chunk,passage,repeat_count)
                if item: candidates.append(item)
        candidates.sort(key=lambda x:(self._action_rank(x.auto_action),x.relevance_score,x.ocr_confidence or 0),reverse=True)
        return [c.model_dump() for c in self._dedupe(candidates)]

    def _mental_health_candidate(self, claim: dict, chunk: dict, passage: str, repeat_count: int):
        low=passage.lower(); name=claim.get("condition_name",""); cid=claim["id"]
        if not re.search(r"\b(anxiety|depression|depressed|depressive|panic|mental health|psychiatr)\w*\b",low): return None
        negated=any(re.search(p,low,re.I|re.S) for p in NEGATIVE_PATTERNS)
        screening=any(re.search(p,low,re.I) for p in SCREENING_PATTERNS)
        boilerplate=screening or any(h in low for h in BOILERPLATE_HINTS)
        element=next((k for k,patterns in AFFIRMATIVE_PATTERNS.items() if any(re.search(p,low,re.I|re.S) for p in patterns)),None)
        copy_risk="high" if repeat_count>=3 and not any(re.search(p,low,re.I) for p in NEW_INFORMATION_PATTERNS) else ("medium" if repeat_count==2 else "low")
        if negated:
            return self._candidate(cid,name,chunk,"negative_evidence","unfavorable","Negative mental-health finding documented for this encounter.",passage,.58 if not boilerplate else .22,"limited" if boilerplate else "moderate","negative_clinical_finding","exclude_from_favorable_autofill","The passage explicitly negates symptoms.","Symptoms were denied or recorded as absent at this encounter.","This is not evidence that the claimed disorder is present or service connected.","Encounter-limited; it may not describe symptoms outside this visit.",repeat_count,copy_risk)
        if boilerplate and element!="diagnosis":
            return self._candidate(cid,name,chunk,element or "other","neutral","Routine screening or templated language without an affirmative supporting fact.",passage,.16,"none","screening_or_boilerplate","suppress","Condition words appear, but the passage proves no claim element.","No affirmative proposition.","It cannot establish diagnosis, nexus, continuity, severity, or impairment.","Likely templated or screening context.",repeat_count,copy_risk)
        if not element:
            return self._candidate(cid,name,chunk,"other","ambiguous","Mental-health terminology appears without a clear supporting proposition.",passage,.30,"low","ambiguous_mention","manual_review_only","The mention may be historical, copied, or incidental.","The record mentions mental-health terminology.","It does not clearly establish a diagnosis, treatment, severity, continuity, or functional impact.","Needs human interpretation of the surrounding encounter.",repeat_count,copy_risk)
        score={"diagnosis":.94,"treatment":.83,"severity":.86,"functional_impact":.91,"continuity":.84}[element]
        action="suggest_for_autofill"; reason="The passage states an affirmative fact tied to a defined claim element."
        limitations="Does not independently establish medical nexus or an official VA rating."
        if copy_risk=="high": score-=.28; action="manual_review_only"; reason="Affirmative language is repeated across multiple pages without clear new information; possible copy-forward."
        return self._candidate(cid,name,chunk,element,"favorable",self._finding_for(element),passage,score,"high" if element in {"diagnosis","functional_impact"} else "moderate","affirmative_clinical_or_lay_evidence",action,reason,self._proposition_for(element,passage),self._supports_for(element),limitations,repeat_count,copy_risk)

    def _generic_candidate(self, claim: dict, chunk: dict, passage: str, repeat_count: int):
        name=claim.get("condition_name",""); cid=claim["id"]; low=passage.lower()
        terms=[t for t in re.findall(r"[a-z0-9]+",name.lower()) if len(t)>3 and t not in {"chronic","bilateral","disorder","condition","strain","with"}]
        if not terms or not any(t in low for t in terms): return None
        neg=bool(re.search(r"\b(denies|no evidence of|negative for|without|resolved)\b",low))
        copy_risk="high" if repeat_count>=3 and not any(re.search(p,low,re.I) for p in NEW_INFORMATION_PATTERNS) else ("medium" if repeat_count==2 else "low")
        if neg:
            return self._candidate(cid,name,chunk,"negative_evidence","unfavorable",f"Negative finding related to {name} documented.",passage,.52,"moderate","negative_clinical_finding","exclude_from_favorable_autofill","Negated findings are not favorable evidence.",f"The encounter records the relevant symptom or condition as absent.","It may be relevant negative/context evidence only.","Limited to this encounter and wording.",repeat_count,copy_risk)
        element=self._generic_element(low)
        if not element:
            return self._candidate(cid,name,chunk,"other","ambiguous",f"The condition is mentioned without a clear supporting fact for {name}.",passage,.24,"low","keyword_only","manual_review_only","Condition-name overlap alone is insufficient.",f"The passage mentions terminology associated with {name}.","No required claim element is clearly established.","Could be a copied problem list, header, history, or unrelated mention.",repeat_count,copy_risk)
        score={"diagnosis":.90,"treatment":.78,"severity":.82,"functional_impact":.86,"continuity":.78,"objective_finding":.88}.get(element,.72)
        action="suggest_for_autofill"
        reason="Contains an affirmative clinical, objective, treatment, continuity, or functional proposition."
        if copy_risk=="high": score-=.25; action="manual_review_only"; reason="Repeated language may be copied forward and does not clearly add a new finding."
        return self._candidate(cid,name,chunk,element,"favorable",f"Affirmative {element.replace('_',' ')} evidence concerning {name}.",passage,score,"high" if element in {"diagnosis","objective_finding"} else "moderate","affirmative_clinical_or_lay_evidence",action,reason,self._extract_proposition(passage),f"Supports the {element.replace('_',' ')} element through an affirmative dated statement.","Does not by itself prove every required service-connection or rating element.",repeat_count,copy_risk)

    @staticmethod
    def _generic_element(low: str) -> str | None:
        patterns=[("diagnosis",r"\b(diagnosed|diagnosis|assessment|impression)\b"),("objective_finding",r"\b(mri|x[- ]?ray|ct|ultrasound|laboratory|exam showed|range of motion|audiogram|sleep study|test showed)\b"),("treatment",r"\b(treated|prescribed|medication|therapy|procedure|injection|surgery|referred)\b"),("functional_impact",r"\b(limits?|unable|difficulty|missed work|interferes with|impairs?)\b"),("continuity",r"\b(chronic|persistent|ongoing|since|worsened|continued)\b"),("severity",r"\b(severe|moderate|frequent|daily|weekly|episodes?|flare[- ]?ups?)\b")]
        return next((e for e,p in patterns if re.search(p,low)),None)

    def _candidate(self,cid,name,chunk,element,polarity,finding,quote,score,weight,context,action,reason,proposition,supports,limitations,repeat_count,copy_risk):
        category=(chunk.get("category") or "").lower()
        authority="medical_record" if "medical" in category else ("military_record" if "military" in category or "dd" in category else "lay_or_administrative_record")
        return SemanticCandidate(chunk["id"],chunk["document_id"],chunk.get("document_name",chunk["document_id"]),int(chunk.get("page") or 1),cid,name,element,polarity,finding,quote[:1600],max(0,min(1,score)),weight,context,action,reason,proposition,supports,limitations,authority,self._temporal_context(quote),copy_risk,repeat_count,chunk.get("ocr_confidence"))

    @staticmethod
    def _proposition_for(element,p):
        labels={"diagnosis":"A clinician documented a mental-health diagnosis or assessment.","treatment":"Mental-health treatment, medication, referral, or follow-up was documented.","severity":"A symptom or standardized severity measure was documented.","functional_impact":"Mental-health symptoms were linked to work, relationship, social, sleep, concentration, or daily-function impairment.","continuity":"The record described onset, persistence, worsening, or continuity of symptoms."}
        return labels[element]
    @staticmethod
    def _supports_for(element): return {"diagnosis":"Supports current-disability/diagnosis evidence.","treatment":"Supports ongoing condition and treatment history.","severity":"Supports symptom severity, frequency, or duration.","functional_impact":"Supports occupational and social impairment.","continuity":"Supports onset, chronicity, continuity, or worsening history."}[element]
    @staticmethod
    def _finding_for(element): return SemanticEvidenceAnalyzer._proposition_for(element,"")
    @staticmethod
    def _extract_proposition(p): return re.sub(r"\s+"," ",p).strip()[:360]
    @staticmethod
    def _temporal_context(p):
        m=re.search(r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b",p)
        return m.group(0) if m else "encounter date/page context required"
    @staticmethod
    def _is_mental_health_claim(n): return bool(re.search(r"anxiety|depress|psychi|mental|adjustment|panic",n,re.I))
    @staticmethod
    def _normalize(t): return re.sub(r"[ \t]+"," ",t.replace("\x00"," ")).strip()
    @staticmethod
    def _passages(t): return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n{2,}",t) if len(x.strip())>=20]
    @staticmethod
    def _fingerprint(p):
        s=re.sub(r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b","<date>",p.lower()); s=re.sub(r"\s+"," ",s); return hashlib.sha1(s[:800].encode()).hexdigest()
    @staticmethod
    def _action_rank(a): return {"suggest_for_autofill":4,"manual_review_only":3,"exclude_from_favorable_autofill":2,"suppress":1}.get(a,0)
    @staticmethod
    def _dedupe(items):
        seen=set(); out=[]
        for item in items:
            key=(item.document_id,item.page,item.claim_element,SemanticEvidenceAnalyzer._fingerprint(item.quote))
            if key not in seen: seen.add(key); out.append(item)
        return out
