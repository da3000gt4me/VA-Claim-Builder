from __future__ import annotations
import json
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.drafting.schemas import DraftRevisionResult

SYSTEM = """You revise draft VA-claim support documents using only approved evidence supplied by the application.
Preserve useful first-person wording. Never invent facts, quotations, diagnoses, dates, witness knowledge, or clinician conclusions.
A doctor nexus draft is a proposed starting point only: do not impersonate a doctor, do not create a signature, and leave the final opinion to the clinician.
A lay witness may state only firsthand observations. Clearly flag unresolved timeline conflicts. Return JSON only."""

class DraftUpdater:
    def __init__(self, router: AIRouter): self.router = router

    def revise(self, document_type: str, original_text: str, approved_annotations: list[dict], timeline_events: list[dict], conflicts: list[dict]) -> DraftRevisionResult:
        schema = DraftRevisionResult.model_json_schema()
        prompt = {
            "document_type": document_type,
            "original_draft": original_text,
            "approved_evidence_annotations": approved_annotations,
            "approved_or_reported_timeline_events": timeline_events,
            "timeline_conflicts_requiring_clarification": conflicts,
            "requirements": [
                "Treat the uploaded draft as the starting point.",
                "Update it with verified medical findings and appropriate lay observations.",
                "Preserve distinctions between medical evidence, veteran report, and witness report.",
                "Cite source annotation IDs in the change log, but keep the final prose readable.",
                "Do not silently resolve conflicts; place them in unresolved_questions."
            ],
            "json_schema": schema,
        }
        response = self.router.generate(AIRequest(task="draft_revision", system_prompt=SYSTEM,
            user_prompt=json.dumps(prompt, ensure_ascii=False), json_schema=schema,
            metadata={"document_type": document_type}))
        if response.parsed is None: raise RuntimeError("AI provider returned no structured draft revision")
        return DraftRevisionResult.model_validate(response.parsed)
