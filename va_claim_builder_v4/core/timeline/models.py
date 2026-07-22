from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class TimelineEventInput(BaseModel):
    claim_id: str | None = None
    event_date_start: str | None = None
    event_date_end: str | None = None
    date_precision: Literal["exact", "month", "year", "range", "approximate", "unknown"] = "unknown"
    event_type: Literal["onset", "worsening", "diagnosis", "treatment", "exposure", "incident", "functional_impact", "continuity", "gap_explanation", "other"]
    description: str = Field(min_length=3)
    source_type: Literal["medical_verified", "military_verified", "administrative_verified", "veteran_reported", "witness_reported", "ai_extracted"]
    source_document_id: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    reporter: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)

class TimelineConflict(BaseModel):
    conflict_type: str
    event_ids: list[str]
    summary: str
    resolution_prompt: str
    severity: Literal["low", "medium", "high"]
