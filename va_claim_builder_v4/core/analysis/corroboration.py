from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

SOURCE_WEIGHTS={
    "medical_records":1.0,"military_records":.95,"dd214":.9,"smart_transcript":.85,
    "personal_timelines":.65,"buddy_letters":.7,"statement_support":.65,
    "doctor_nexus_drafts":.45,"self_nexus_drafts":.35,"unknown":.5,
}

@dataclass
class EvidenceCluster:
    claim_id:str; claim_element:str; proposition:str; polarity:str
    independent_documents:int; independent_source_types:int; evidence_items:int
    corroboration_score:float; strength:str; source_names:list[str]; annotation_ids:list[str]
    repeated_same_source:int; explanation:str
    def model_dump(self)->dict[str,Any]: return asdict(self)

class CrossDocumentCorroborator:
    """Groups approved evidence by the proposition it actually establishes.

    Duplicate/copy-forward entries from one document cannot inflate corroboration. The
    score rewards independent documents and different source classes, especially when
    medical/military evidence aligns with competent lay observations.
    """
    def build(self, annotations:list[dict[str,Any]])->list[dict[str,Any]]:
        approved=[a for a in annotations if a.get("review_status")=="approved" and a.get("polarity") in {"favorable","unfavorable"}]
        buckets=defaultdict(list)
        for a in approved:
            buckets[(a.get("claim_id") or "",a.get("claim_element") or "other",a.get("polarity") or "ambiguous")].append(a)
        result=[]
        for (claim_id,element,polarity),items in buckets.items():
            semantic_groups=[]
            for item in items:
                tokens=self._tokens(item.get("finding") or item.get("quote") or "")
                matched=None
                for group in semantic_groups:
                    if self._similar(tokens,group[0]) >= .18:
                        matched=group; break
                if matched is None: semantic_groups.append([tokens,[item]])
                else: matched[1].append(item); matched[0] |= tokens
            for _,group_items in semantic_groups:
                docs={a.get("document_id") for a in group_items if a.get("document_id")}
                types={a.get("category") or "unknown" for a in group_items}
                names=sorted({a.get("document_name") or a.get("document_id") or "Unknown source" for a in group_items})
                unique_docs=len(docs); unique_types=len(types)
                avg_conf=sum(float(a.get("confidence") or .5) for a in group_items)/len(group_items)
                authority=sum(SOURCE_WEIGHTS.get(t,.5) for t in types)/max(1,len(types))
                score=min(1.0,.34*avg_conf+.30*min(unique_docs,3)/3+.24*min(unique_types,3)/3+.12*authority)
                if unique_docs>=3 and unique_types>=2 and score>=.72: strength="strongly corroborated"
                elif unique_docs>=2 and score>=.58: strength="corroborated"
                elif unique_docs==1: strength="single-source support"
                else: strength="limited"
                proposition=max(group_items,key=lambda x:len(x.get("finding") or "")).get("finding") or "Evidence proposition"
                repeated=max(0,len(group_items)-unique_docs)
                explanation=(f"{unique_docs} independent document(s) across {unique_types} source type(s). "
                             f"{repeated} repeated item(s) from already-counted sources were not treated as independent corroboration.")
                result.append(EvidenceCluster(claim_id,element,proposition,polarity,unique_docs,unique_types,len(group_items),round(score,3),strength,names,[a['id'] for a in group_items if a.get('id')],repeated,explanation).model_dump())
        return sorted(result,key=lambda x:(x['claim_id'],x['claim_element'],-x['corroboration_score']))

    @staticmethod
    def _tokens(text:str)->set[str]:
        stop={"the","and","was","were","with","that","this","from","patient","veteran","documented","observed","current","recurring","chronic"}
        return {w for w in re.findall(r"[a-z]+",text.lower()) if len(w)>3 and w not in stop}

    @staticmethod
    def _similar(a:set[str],b:set[str])->float:
        if not a or not b:return 0.0
        return len(a & b)/len(a | b)

    @staticmethod
    def _fingerprint(text:str)->str:
        text=text.lower()
        text=re.sub(r"\b(?:19|20)\d{2}\b","<date>",text)
        text=re.sub(r"\d+","<n>",text)
        words=[w for w in re.findall(r"[a-z]+",text) if w not in {"the","and","was","were","with","that","this","from","patient","veteran"}]
        return " ".join(words[:22])
