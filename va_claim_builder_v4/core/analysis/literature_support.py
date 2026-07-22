from __future__ import annotations
import re
from typing import Any

class LiteratureSupportEngine:
    """Conservative literature intake and relevance screening.

    This module does not assert patient-specific causation. It validates citation
    completeness and maps a study only to the general medical proposition it may support.
    """
    REQUIRED = ("title", "year", "source")

    def assess_candidate(self, candidate: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
        missing = [k for k in self.REQUIRED if not str(candidate.get(k, "")).strip()]
        identifier = str(candidate.get("doi") or candidate.get("pmid") or candidate.get("url") or "").strip()
        if not identifier:
            missing.append("doi_or_pmid_or_url")
        abstract = str(candidate.get("abstract") or candidate.get("summary") or "")
        condition = claim.get("condition_name", "")
        terms = {t.lower() for t in re.findall(r"[A-Za-z]{4,}", condition)}
        haystack = f"{candidate.get('title','')} {abstract}".lower()
        overlap = sorted(t for t in terms if t in haystack)
        study_type = self._study_type(haystack)
        quality = self._quality(study_type, missing, bool(abstract.strip()))
        return {
            "citation_complete": not missing,
            "missing_fields": missing,
            "claim_relevance": "potentially_relevant" if overlap else "manual_review",
            "matched_condition_terms": overlap,
            "study_type": study_type,
            "quality_tier": quality,
            "patient_specific_causation": False,
            "allowed_use": "General medical background for clinician review; not proof that this veteran's condition was caused by service.",
            "verification_status": candidate.get("verification_status", "unverified"),
            "review_flags": (["Citation metadata is incomplete."] if missing else []) + (["No condition-specific term overlap was detected."] if not overlap else []),
        }

    @staticmethod
    def _study_type(text: str) -> str:
        for key, value in (
            ("systematic review", "systematic_review"), ("meta-analysis", "meta_analysis"),
            ("randomized", "randomized_trial"), ("cohort", "cohort_study"),
            ("case-control", "case_control"), ("guideline", "clinical_guideline"),
            ("review", "narrative_review"), ("case report", "case_report"),
        ):
            if key in text: return value
        return "unspecified"

    @staticmethod
    def _quality(study_type: str, missing: list[str], has_abstract: bool) -> str:
        if missing: return "insufficient_metadata"
        if study_type in {"systematic_review", "meta_analysis", "clinical_guideline"}: return "higher"
        if study_type in {"randomized_trial", "cohort_study", "case_control"}: return "moderate"
        return "preliminary" if has_abstract else "metadata_only"
