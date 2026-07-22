from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class Citation(BaseModel):
    document_id: str
    filename: str
    page: int = Field(ge=1)
    encounter_date: str | None = None
    provider: str | None = None
    quote: str
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)

class EvidenceAnnotation(BaseModel):
    annotation_id: str
    claim: str
    claim_element: Literal["diagnosis","in_service_event","nexus","continuity","severity","functional_impact","treatment","negative_evidence","other"]
    polarity: Literal["favorable","unfavorable","neutral","ambiguous"]
    finding: str
    severity_indicator: str | None = None
    rating_criterion: str | None = None
    confidence: float = Field(ge=0, le=1)
    citations: list[Citation]
    requires_human_review: bool = True

class ClaimAssessment(BaseModel):
    claim: str
    theory: Literal["direct","secondary","aggravation","presumptive","multiple","unknown"]
    diagnosis_status: Literal["supported","partial","missing","conflicting"]
    in_service_status: Literal["supported","partial","missing","not_applicable","conflicting"]
    nexus_status: Literal["supported","partial","missing","conflicting"]
    severity_summary: str
    possible_rating_band: str | None = None
    evidence_strength: Literal["strong","moderate","limited","insufficient","conflicting"]
    annotations: list[EvidenceAnnotation]
    gaps: list[str]
    contradictions: list[str]
    recommended_actions: list[str]
    disclaimer: str = "Preliminary evidence analysis only; not an official VA rating or medical opinion."
