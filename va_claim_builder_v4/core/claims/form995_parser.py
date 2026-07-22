from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Any

_EXPLICIT_21A_RE = re.compile(r"(?:\b21\s*[\.]?\s*A\b|\b21A\b)", re.I)
_SECTION_21A_RE = re.compile(
    r"(?:\b21\s*[\.]?\s*A\b|\b21A\b|SPECIFIC\s+ISSUE\s*\(?S?\)?\s+(?:OF|FOR)\s+(?:REVIEW|DISAGREEMENT)|SPECIFIC\s+ISSUE\s*\(?S?\)?)",
    re.I,
)
_SECTION_21B_RE = re.compile(r"(?:\b21\s*[\.]?\s*B\b|\b21B\b|DATE\s+OF\s+(?:VA\s+)?DECISION)", re.I)
_LEGACY_HEADER_RE = re.compile(r"(?:SECTION\s+III[^\n]{0,80}ISSUE\s*\(?S?\)?|^\s*ISSUES?\s*:)", re.I | re.M)
_LEGACY_STOP_RE = re.compile(r"(?:SECTION\s+IV|NEW\s+AND\s+RELEVANT\s+EVIDENCE)", re.I)

_NOISE_RE = re.compile(
    r"(?:VA\s+FORM|OMB\s+Control|DECISION\s+REVIEW\s+REQUEST|SUPPLEMENTAL\s+CLAIM|page\s+\d+|"
    r"social\s+security|file\s+number|specific\s+issue|date\s+of\s+(?:va\s+)?decision|section\s+[ivx]+|"
    r"veteran'?s?\s+identification|claimant'?s?\s+identification|instructions?|additional\s+sheet)", re.I,
)
_ROW_PREFIX_RE = re.compile(r"^\s*(?:issue\s*)?(?:\(?([1-9])\)?[\.)\-:]?)\s+")
_DATE_RE = re.compile(
    r"\b(?:0?[1-9]|1[0-2])[/\-.](?:0?[1-9]|[12]\d|3[01])[/\-.](?:19|20)?\d{2}\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?:0?[1-9]|[12]\d|3[01]),?\s+(?:19|20)\d{2}\b",
    re.I,
)
_TRAILING_META_RE = re.compile(r"\s+(?:date\s+of\s+(?:va\s+)?decision|decision\s+date|issue\s+date)\s*:.*$", re.I)

_BLOCKLIST = {"yes", "no", "unknown", "not applicable", "see attached", "see attachment", "supplemental claim", "decision review request", "new and relevant evidence", "specific issue(s)", "specific issues", "date of va decision", "date of decision"}

@dataclass(frozen=True)
class ParsedClaim:
    condition_name: str
    theory: str = "unknown"
    confidence: float = 0.96
    source_page: int | None = None
    source_text: str = ""
    source_document_id: str | None = None

class Form995ClaimParser:
    """Extract only the nine numbered Section 21A issue rows from each Form 20-0995.

    Parsing is isolated per uploaded document. This prevents page 5 from one form from
    being combined with continuation/instruction text from another form.
    """

    @staticmethod
    def _clean_candidate(value: str) -> str:
        value = (value or "").replace("\x00", " ")
        value = _ROW_PREFIX_RE.sub("", value)
        value = _TRAILING_META_RE.sub("", value)
        value = _DATE_RE.sub(" ", value)
        value = re.sub(r"\b(?:MM|DD|YYYY)\b", " ", value, flags=re.I)
        value = re.sub(r"\s+", " ", value).strip(" \t:;,-|_")
        return value.strip()

    @staticmethod
    def _looks_like_condition(value: str) -> bool:
        low = value.lower().strip()
        if not value or low in _BLOCKLIST or _NOISE_RE.search(value): return False
        if len(value) < 3 or len(value) > 220 or len(value.split()) > 30: return False
        if not re.search(r"[A-Za-z]", value): return False
        prose = ("please list", "identify the", "enter the", "check the", "complete this", "if applicable", "use this form", "you disagree", "information requested", "attach additional", "if more space")
        return not any(x in low for x in prose)

    @staticmethod
    def _section_21a_text(text: str) -> str:
        start = _SECTION_21A_RE.search(text or "")
        if not start: return ""
        tail = text[start.end():]
        stop = _SECTION_21B_RE.search(tail)
        return tail[:stop.start()] if stop else tail

    @staticmethod
    def _numbered_rows(section: str) -> list[str]:
        """Return rows 1-9 only, preserving wrapped text.

        OCR can flatten the table, so row starts are detected anywhere in the string.
        A row number must be 1 through 9, and each number is used at most once.
        """
        text = re.sub(r"[\t|•▪]+", "\n", section or "")
        text = re.sub(r"\r", "\n", text)
        # Put a newline before numbered row markers that were flattened.
        text = re.sub(r"(?<!^)(?<!\n)\s+(?=(?:issue\s*)?\(?[1-9]\)?[\.)\-:]\s+)", "\n", text, flags=re.I)
        lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
        rows: list[str] = []
        current = ""
        current_num: int | None = None
        used: set[int] = set()
        for line in lines:
            m = _ROW_PREFIX_RE.match(line)
            if m:
                num = int(m.group(1))
                if current and current_num not in used:
                    rows.append(current); used.add(current_num)
                if num in used:
                    current = ""; current_num = None
                else:
                    current = line; current_num = num
            elif current:
                # Wrapped continuation for the active numbered row.
                current = f"{current} {line}"
        if current and current_num not in used:
            rows.append(current)
        return rows[:9]

    def _parse_document_pages(self, pages: list[dict[str, Any]]) -> list[ParsedClaim]:
        page5 = [p for p in pages if int(p.get("page") or 0) == 5]
        candidates = page5 or [p for p in pages if _EXPLICIT_21A_RE.search(p.get("text") or "")]
        legacy = not candidates
        if legacy:
            candidates = [p for p in pages if _LEGACY_HEADER_RE.search(p.get("text") or "")]
        found: list[ParsedClaim] = []
        seen: set[str] = set()
        for page in candidates:
            text = page.get("text") or ""
            section = self._section_21a_text(text)
            if not section and legacy:
                start = _LEGACY_HEADER_RE.search(text)
                if start:
                    tail = text[start.end():]
                    stop = _LEGACY_STOP_RE.search(tail)
                    section = tail[:stop.start()] if stop else tail
            if not section: continue
            for raw in self._numbered_rows(section):
                candidate = self._clean_candidate(raw)
                if not self._looks_like_condition(candidate): continue
                key = re.sub(r"[^a-z0-9]+", " ", candidate.lower()).strip()
                if not key or key in seen: continue
                seen.add(key)
                found.append(ParsedClaim(candidate, source_page=page.get("page"), source_text=raw.strip(), source_document_id=page.get("document_id")))
                if len(found) == 9: break
            if found: break
        return found

    def parse_pages(self, pages: Iterable[dict[str, Any]]) -> list[ParsedClaim]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for page in pages:
            grouped.setdefault(str(page.get("document_id") or "unknown"), []).append(page)
        output: list[ParsedClaim] = []
        seen: set[str] = set()
        for document_id, doc_pages in grouped.items():
            for item in self._parse_document_pages(doc_pages):
                key = re.sub(r"[^a-z0-9]+", " ", item.condition_name.lower()).strip()
                if key in seen: continue
                seen.add(key); output.append(item)
        return output

    def diagnostics(self, pages: Iterable[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for p in pages: grouped.setdefault(str(p.get("document_id") or "unknown"), []).append(p)
        forms=[]
        for doc_id, doc_pages in grouped.items():
            page5=next((p for p in doc_pages if int(p.get("page") or 0)==5),None)
            source=page5 or next((p for p in doc_pages if _SECTION_21A_RE.search(p.get("text") or "")),None)
            section=self._section_21a_text(source.get("text") or "") if source else ""
            parsed=self._parse_document_pages(doc_pages)
            forms.append({"document_id":doc_id,"document_name":(source or doc_pages[0]).get("document_name"),"physical_page_5_found":page5 is not None,"section_21a_found":bool(section),"source_page":source.get("page") if source else None,"section_preview":section[:4000],"parsed_claims":[c.condition_name for c in parsed]})
        all_claims=self.parse_pages([p for group in grouped.values() for p in group])
        return {"forms":forms,"parsed_claims":[c.condition_name for c in all_claims],"parsed_total":len(all_claims)}

    def add_missing_claims(self, db, project_id: str, pages: Iterable[dict[str, Any]]) -> dict[str, Any]:
        pages=list(pages); parsed=self.parse_pages(pages)
        existing={re.sub(r"[^a-z0-9]+"," ",c["condition_name"].lower()).strip():c for c in db.list_claims(project_id)}
        added=[]; skipped=[]
        for item in parsed:
            key=re.sub(r"[^a-z0-9]+"," ",item.condition_name.lower()).strip()
            if key in existing:
                skipped.append({"condition_name":item.condition_name,"reason":"already_exists"}); continue
            cid=db.add_claim(project_id,item.condition_name,item.theory)
            record={"id":cid,"condition_name":item.condition_name,"theory":item.theory,"confidence":item.confidence,"source_page":item.source_page,"source_text":item.source_text,"source_document_id":item.source_document_id}
            existing[key]=record; added.append(record)
        return {"parsed":len(parsed),"added":added,"skipped":skipped,"diagnostics":self.diagnostics(pages)}
