from __future__ import annotations
import json
from pydantic import ValidationError
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.analysis.schemas import ClaimAssessment

SYSTEM = """You are an evidence extraction engine for a U.S. Department of Veterans Affairs disability claim support application.
Use only facts in the supplied evidence chunks. Never invent diagnoses, dates, exposures, medical opinions, rating criteria, quotations, or page numbers.
Distinguish medical evidence from lay testimony. Do not issue a medical opinion or promise a benefit outcome.
Every substantive finding must cite at least one supplied source. Mark uncertainty and contradictions. Return JSON only."""

class EvidenceEngine:
    def __init__(self, router: AIRouter):
        self.router = router

    def build_request(self, claim: str, theory: str, evidence_chunks: list[dict]) -> AIRequest:
        schema = ClaimAssessment.model_json_schema()
        prompt = f"""CLAIM: {claim}\nTHEORY: {theory}\n\nEVIDENCE CHUNKS:\n{json.dumps(evidence_chunks, ensure_ascii=False)}\n\nReturn one JSON object matching this schema exactly:\n{json.dumps(schema)}"""
        return AIRequest(task="claim_assessment", system_prompt=SYSTEM, user_prompt=prompt,
                         json_schema=schema, metadata={"claim": claim, "theory": theory})

    def assess_claim(self, claim: str, theory: str, evidence_chunks: list[dict]) -> ClaimAssessment:
        response = self.router.generate(self.build_request(claim, theory, evidence_chunks))
        if response.parsed is None:
            raise RuntimeError("AI provider returned no structured output")
        try:
            return ClaimAssessment.model_validate(response.parsed)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid AI assessment: {exc}") from exc
