from __future__ import annotations
from typing import Any

class EvidenceAutofillService:
    """Creates pending annotations only from high-value, proposition-based candidates."""
    def __init__(self, db): self.db=db

    def populate(self, project_id: str, candidates: list[dict[str, Any]], min_score: float = 0.72) -> dict[str, int]:
        created=skipped=0
        existing={(a.get('document_id'),a.get('page'),a.get('claim_id'),a.get('claim_element'),(a.get('quote') or '')[:160]) for a in self.db.list_annotations(project_id)}
        for c in candidates:
            key=(c['document_id'],c['page'],c['claim_id'],c['claim_element'],(c.get('quote') or '')[:160])
            eligible=(c.get('auto_action')=='suggest_for_autofill' and c.get('polarity')=='favorable' and float(c.get('relevance_score',0))>=min_score and c.get('copy_forward_risk')!='high')
            if key in existing or not eligible:
                skipped+=1; continue
            note=(f"WHY INCLUDED: {c.get('supports_because','')}\n"
                  f"PROPOSITION: {c.get('proposition','')}\n"
                  f"LIMITATIONS: {c.get('limitations','')}\n"
                  f"SOURCE AUTHORITY: {c.get('source_authority','unknown')}\n"
                  f"COPY-FORWARD RISK: {c.get('copy_forward_risk','unknown')} (repeat count {c.get('repeat_count',1)})")
            self.db.add_annotation(project_id,{
                'claim_id':c['claim_id'],'document_id':c['document_id'],'page':c['page'],
                'claim_element':c['claim_element'],'polarity':c['polarity'],
                'finding':c.get('proposition') or c['finding'],'quote':c['quote'],
                'confidence':c['relevance_score'],'ai_provider':'local_semantic_rules',
                'ai_model':'semantic-evidence-v2','review_status':'pending','reviewer_note':note
            }); created+=1
        return {'created':created,'skipped':skipped}
