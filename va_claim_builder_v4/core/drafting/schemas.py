from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class DraftChange(BaseModel):
    change_type: Literal["add", "remove", "clarify", "correct", "flag"]
    section: str
    original_text: str | None = None
    revised_text: str | None = None
    rationale: str
    source_annotation_ids: list[str] = []

class DraftRevisionResult(BaseModel):
    document_type: Literal["self_nexus", "doctor_nexus", "buddy_letter", "personal_statement", "timeline_narrative"]
    title: str
    revised_text: str
    unresolved_questions: list[str]
    changes: list[DraftChange]
    requires_author_review: bool = True
    requires_clinician_signature: bool = False
    disclaimer: str
