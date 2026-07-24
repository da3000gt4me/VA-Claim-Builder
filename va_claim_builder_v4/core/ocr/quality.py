from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class TextQuality:
    score: float
    character_count: int
    meaningful_words: int
    alphanumeric_ratio: float
    fragmentation_ratio: float
    repeated_symbol_ratio: float
    date_count: int
    diagnosis_code_count: int
    provider_indicator_count: int
    review_required: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_WORD = re.compile(r"[A-Za-z][A-Za-z'-]{1,}")
_DATE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)
_ICD = re.compile(r"\b(?:[A-TV-Z]\d{2}(?:\.\d{1,4})?|\d{3}(?:\.\d{1,2})?)\b", re.I)
_PROVIDER = re.compile(
    r"\b(?:Dr\.?|MD|M\.D\.|DO|D\.O\.|NP|PA-C|provider|physician|clinician|examiner|"
    r"radiologist|therapist|clinic|hospital|medical center)\b",
    re.I,
)


def evaluate_text(text: str, *, engine_confidence: float | None = None) -> TextQuality:
    """Score extraction quality without treating one OCR confidence value as a verdict."""
    stripped = text.strip()
    characters = len(stripped)
    words = _WORD.findall(stripped)
    meaningful = [word for word in words if len(word) > 2]
    non_space = [char for char in stripped if not char.isspace()]
    alpha_numeric = sum(char.isalnum() for char in non_space)
    alphanumeric_ratio = alpha_numeric / max(1, len(non_space))
    fragments = sum(len(word) <= 2 for word in words)
    fragmentation = fragments / max(1, len(words))
    symbols = sum(not char.isalnum() and not char.isspace() for char in stripped)
    repeated = len(re.findall(r"([^\w\s])\1{2,}", stripped))
    repeated_ratio = (symbols + repeated * 3) / max(1, characters)
    dates = len(_DATE.findall(stripped))
    codes = len(_ICD.findall(stripped))
    providers = len(_PROVIDER.findall(stripped))

    score = 0.0
    score += min(characters / 180.0, 1.0) * 0.18
    score += min(len(meaningful) / 28.0, 1.0) * 0.25
    score += min(alphanumeric_ratio / 0.82, 1.0) * 0.22
    score += max(0.0, 1.0 - fragmentation * 2.3) * 0.14
    score += max(0.0, 1.0 - repeated_ratio * 7.0) * 0.09
    score += min((dates + codes + providers) / 4.0, 1.0) * 0.07
    if engine_confidence is not None and engine_confidence >= 0:
        score += min(engine_confidence / 100.0, 1.0) * 0.05
    score = round(max(0.0, min(score, 1.0)), 3)

    reasons: list[str] = []
    if characters == 0:
        reasons.append("no text returned")
    elif characters < 20:
        reasons.append("very little text")
    if meaningful and fragmentation > 0.28:
        reasons.append("many fragmented words")
    if alphanumeric_ratio < 0.55 and characters:
        reasons.append("low alphanumeric balance")
    if repeated_ratio > 0.09:
        reasons.append("repeated or corrupt glyphs")
    if score < 0.48 and characters:
        reasons.append("low composite extraction quality")
    return TextQuality(
        score, characters, len(meaningful), round(alphanumeric_ratio, 3),
        round(fragmentation, 3), round(repeated_ratio, 3), dates, codes,
        providers, score < 0.58, tuple(dict.fromkeys(reasons)),
    )
