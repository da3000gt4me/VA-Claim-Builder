from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

DATE_PATTERNS = [
    # ISO / common numeric dates
    re.compile(r"\b(?P<y>19\d{2}|20\d{2})[-/](?P<m>0?[1-9]|1[0-2])[-/](?P<d>0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(?P<m>0?[1-9]|1[0-2])[-/](?P<d>0?[1-9]|[12]\d|3[01])[-/](?P<y>19\d{2}|20\d{2})\b"),
]
MONTHS = {m.lower(): i for i, m in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
], start=1)}
MONTH_RE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?[,]?\s+)?(?P<year>19\d{2}|20\d{2})\b",
    re.I,
)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
RANGE_RE = re.compile(r"\b(19\d{2}|20\d{2})\s*(?:-|–|—|to|through)\s*(19\d{2}|20\d{2})\b", re.I)

NEGATION_RE = re.compile(r"\b(denies|denied|no evidence of|without|negative for|resolved|rule out|history denied)\b", re.I)

EVENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("onset", re.compile(r"\b(began|beginning|started|onset|first noticed|first experienced|developed)\b", re.I)),
    ("worsening", re.compile(r"\b(worsened|worsening|increased|progressed|became worse|exacerbat|aggravat)\w*\b", re.I)),
    ("diagnosis", re.compile(r"\b(diagnosed|diagnosis|assessment|impression|confirmed)\b", re.I)),
    ("treatment", re.compile(r"\b(treated|treatment|prescribed|started on|therapy|procedure|surgery|medication|referred)\b", re.I)),
    ("exposure", re.compile(r"\b(exposed|exposure|noise|weapons fire|rifle salute|dust|chemical|server room|crawlspace|shift work)\b", re.I)),
    ("incident", re.compile(r"\b(injury|injured|incident|accident|fall|carried|lifting|struck|sprain|strain)\b", re.I)),
    ("functional_impact", re.compile(r"\b(missed work|unable to|difficulty|limited|interfered|functional impact|occupational|relationship|daily activities|sleep disruption)\b", re.I)),
    ("continuity", re.compile(r"\b(continued|persistent|ongoing|since service|ever since|chronic|recurrent)\b", re.I)),
]

SOURCE_BY_CATEGORY = {
    "03_medical_records": "medical_verified",
    "08_military_records": "military_verified",
    "09_dd214": "administrative_verified",
    "07_smart_transcript": "administrative_verified",
    "10_personal_statements_historical_timelines": "veteran_reported",
    "02_statements_in_support_of_claim": "veteran_reported",
    "06_draft_buddy_lay_letters": "witness_reported",
    # Backward-compatible aliases for projects created by earlier builds.
    "medical_records": "medical_verified", "military_records": "military_verified",
    "dd214": "administrative_verified", "smart_transcript": "administrative_verified",
    "personal_timelines": "veteran_reported", "statements_support_claim": "veteran_reported",
    "buddy_letters": "witness_reported",
}

@dataclass(frozen=True)
class ProposedTimelineEvent:
    claim_id: str | None
    event_date_start: str | None
    event_date_end: str | None
    date_precision: str
    event_type: str
    description: str
    source_type: str
    source_document_id: str | None
    source_page: int | None
    reporter: str | None
    confidence: float
    verification_status: str = "proposed"
    reconciliation_status: str = "unreviewed"

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class HistoricalTimelineAutoPopulator:
    """Creates editable proposed timeline entries from existing project evidence.

    It deliberately proposes rather than approves events. Dates, event type, and wording
    remain editable, and uncertain/relative dates are flagged with lower confidence.
    """

    def propose(
        self,
        claims: Iterable[dict[str, Any]],
        annotations: Iterable[dict[str, Any]],
        chunks: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        claims = list(claims)
        claim_by_id = {c["id"]: c for c in claims}
        proposals: list[ProposedTimelineEvent] = []

        # Evidence annotations are the highest-value source because they already carry claim mapping.
        for ann in annotations:
            text = self._clean(ann.get("quote") or ann.get("finding") or "")
            if not text or ann.get("polarity") == "unfavorable" or NEGATION_RE.search(text):
                continue
            event_type = self._event_type(text, ann.get("claim_element"))
            if not event_type:
                continue
            start, end, precision = self._date(text)
            # A dated record can still be useful when the proposition describes onset/diagnosis/etc.
            confidence = min(float(ann.get("confidence") or .65), .95)
            proposals.append(ProposedTimelineEvent(
                claim_id=ann.get("claim_id"),
                event_date_start=start,
                event_date_end=end,
                date_precision=precision,
                event_type=event_type,
                description=self._description(text, ann.get("finding")),
                source_type=SOURCE_BY_CATEGORY.get(ann.get("category", ""), "ai_extracted"),
                source_document_id=ann.get("document_id"),
                source_page=ann.get("page"),
                reporter=None,
                confidence=confidence,
            ))

        # Page text captures personal timelines and lay statements that may not yet be annotated.
        for chunk in chunks:
            category = chunk.get("category", "")
            if category not in {
                "10_personal_statements_historical_timelines", "02_statements_in_support_of_claim", "06_draft_buddy_lay_letters",
                "03_medical_records", "08_military_records", "09_dd214", "07_smart_transcript",
                "personal_timelines", "statements_support_claim", "buddy_letters",
                "medical_records", "military_records", "dd214", "smart_transcript",
            }:
                continue
            claim_ids = [x for x in (chunk.get("linked_claim_ids") or "").split(",") if x]
            if not claim_ids:
                claim_ids = self._claims_mentioned(chunk.get("text", ""), claims)
            for sentence in self._sentences(chunk.get("text", "")):
                if NEGATION_RE.search(sentence):
                    continue
                event_type = self._event_type(sentence)
                if not event_type:
                    continue
                start, end, precision = self._date(sentence)
                # Do not flood the timeline with undated generic chart text.
                # Undated medical and military events remain useful as proposed entries;
                # the reviewer can supply or correct the date from the source page.
                selected_claim_ids = claim_ids or [None]
                for claim_id in selected_claim_ids:
                    if claim_id is not None and claim_id not in claim_by_id:
                        continue
                    proposals.append(ProposedTimelineEvent(
                        claim_id=claim_id,
                        event_date_start=start,
                        event_date_end=end,
                        date_precision=precision,
                        event_type=event_type,
                        description=self._description(sentence),
                        source_type=SOURCE_BY_CATEGORY.get(category, "ai_extracted"),
                        source_document_id=chunk.get("document_id"),
                        source_page=chunk.get("page"),
                        reporter=None,
                        confidence=self._chunk_confidence(chunk, bool(start)),
                    ))

        return [p.as_dict() for p in self._dedupe(proposals)]

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", str(text)).strip()

    @staticmethod
    def _sentences(text: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", str(text)).strip()
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", cleaned) if 20 <= len(s.strip()) <= 700]

    @staticmethod
    def _claims_mentioned(text: str, claims: list[dict[str, Any]]) -> list[str]:
        low = text.lower()
        return [c["id"] for c in claims if c.get("condition_name", "").lower() in low]

    @staticmethod
    def _event_type(text: str, claim_element: str | None = None) -> str | None:
        element = (claim_element or "").lower()
        element_map = {
            "in_service_event": "incident", "event": "incident", "exposure": "exposure",
            "diagnosis": "diagnosis", "current_diagnosis": "diagnosis",
            "continuity": "continuity", "severity": "worsening",
            "functional_impact": "functional_impact", "treatment": "treatment",
        }
        for key, value in element_map.items():
            if key in element:
                return value
        for event_type, pattern in EVENT_PATTERNS:
            if pattern.search(text):
                return event_type
        return None

    @staticmethod
    def _date(text: str) -> tuple[str | None, str | None, str]:
        match = RANGE_RE.search(text)
        if match:
            return match.group(1), match.group(2), "range"
        for pattern in DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    return datetime(int(match.group("y")), int(match.group("m")), int(match.group("d"))).date().isoformat(), None, "exact"
                except ValueError:
                    pass
        match = MONTH_RE.search(text)
        if match:
            month = MONTHS[match.group("month").lower()]
            year = int(match.group("year"))
            if match.group("day"):
                try:
                    return datetime(year, month, int(match.group("day"))).date().isoformat(), None, "exact"
                except ValueError:
                    pass
            return f"{year:04d}-{month:02d}", None, "month"
        match = YEAR_RE.search(text)
        if match:
            return match.group(1), None, "year"
        if re.search(r"\b(during service|while serving|on active duty|in the navy)\b", text, re.I):
            return None, None, "service_period"
        return None, None, "unknown"

    @staticmethod
    def _description(text: str, finding: str | None = None) -> str:
        base = HistoricalTimelineAutoPopulator._clean(finding or text)
        if len(base) > 600:
            base = base[:597].rstrip() + "..."
        return base

    @staticmethod
    def _chunk_confidence(chunk: dict[str, Any], dated: bool) -> float:
        ocr = chunk.get("ocr_confidence")
        value = float(ocr) if ocr is not None else .65
        if value > 1:
            value /= 100
        value = max(.35, min(value, .9))
        return min(.9, value + (.05 if dated else 0))

    @staticmethod
    def _dedupe(items: list[ProposedTimelineEvent]) -> list[ProposedTimelineEvent]:
        seen: set[tuple[Any, ...]] = set()
        output: list[ProposedTimelineEvent] = []
        for item in sorted(items, key=lambda x: (x.event_date_start or "9999", x.claim_id or "", x.event_type, x.description)):
            normalized = re.sub(r"\W+", " ", item.description.lower()).strip()[:240]
            key = (item.claim_id, item.event_date_start, item.event_date_end, item.event_type, normalized, item.source_document_id, item.source_page)
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output
