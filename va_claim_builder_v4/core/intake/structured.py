from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Classification:
    document_type: str
    confidence: float
    revision: str = ""
    author_type: str = ""


_ICD10 = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,4})?)\b", re.I)
_ICD9 = re.compile(r"\b(\d{3}(?:\.\d{1,2})?)\b")
_DATE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)


def classify_document(text: str, *, filename: str = "", fields: dict | None = None) -> Classification:
    sample = f"{filename}\n{text[:12000]}".casefold()
    field_names = " ".join((fields or {}).keys()).casefold()
    if "20-0995" in sample or (
        "supplemental claim" in sample and ("section 21a" in sample or "issues for review" in sample)
    ) or "0995" in field_names:
        revision = ""
        match = re.search(r"(?:rev(?:ision)?\.?\s*|version\s*)(\d{1,2}/\d{4})", sample)
        if match:
            revision = match.group(1)
        return Classification("va_form_20_0995", .99, revision)
    if re.search(r"\b(?:buddy|witness|spouse|coworker|supervisor) statement\b", sample):
        return Classification("buddy_witness_statement", .94, author_type="lay witness")
    nexus = any(term in sample for term in (
        "nexus letter", "nexus statement", "medical opinion", "at least as likely as not",
    ))
    if nexus:
        signed_provider = bool(re.search(r"\b(?:md|m\.d\.|do|d\.o\.|np|pa-c|phd|psy\.d\.)\b", sample))
        return Classification(
            "provider_nexus_letter" if signed_provider else "claimant_nexus_statement",
            .92 if signed_provider else .82,
            author_type="provider" if signed_provider else "claimant",
        )
    if any(term in sample for term in ("personal timeline", "service history", "my military service")):
        return Classification("personal_timeline", .88, author_type="claimant")
    if any(term in sample for term in ("diagnosis", "assessment", "encounter", "medical record", "patient")):
        return Classification("medical_record", .78, author_type="medical")
    if any(term in sample for term in ("radiology", "impression:", "mri", "ct scan", "x-ray")):
        return Classification("imaging_report", .82, author_type="medical")
    if any(term in sample for term in ("laboratory", "reference range", "specimen")):
        return Classification("laboratory_report", .82, author_type="medical")
    if "disability benefits questionnaire" in sample or re.search(r"\bdbq\b", sample):
        return Classification("dbq", .9, author_type="provider")
    return Classification("other", .35)


def parse_20_0995(
    pages: list[tuple[int, str]], *, fields: dict[str, object] | None = None
) -> list[dict[str, object]]:
    """Extract Section 21A issues from AcroForm values first, then page text anchors."""
    suggestions: list[dict[str, object]] = []
    field_values = fields or {}
    grouped: dict[str, dict[str, tuple[str, str]]] = {}
    for name, raw_value in field_values.items():
        value = str(raw_value).strip()
        if not value:
            continue
        lower = str(name).casefold()
        if not ("21" in lower or any(token in lower for token in ("issue", "condition", "secondary"))):
            continue
        row_match = re.search(r"(\d+)(?!.*\d)", lower)
        row = row_match.group(1) if row_match else "1"
        target = (
            "decision_date" if "decision" in lower and "date" in lower else
            "secondary_to" if "secondary" in lower or "primarycondition" in lower else
            "description" if "description" in lower or "explanation" in lower else
            "service_event" if any(token in lower for token in ("event", "injury", "exposure")) else
            "theory" if "theory" in lower or "serviceconnection" in lower else
            "condition" if any(token in lower for token in ("condition", "issue", "disability")) else
            ""
        )
        if target:
            grouped.setdefault(row, {})[target] = (value, f"AcroForm:{name}")
    for row, values in grouped.items():
        condition = values.get("condition", ("", ""))[0]
        if condition:
            suggestions.append(_claim_payload(values, page=1, method="acroform", row=row))

    label_pattern = re.compile(
        r"(?:SECTION\s+21A.*?\n)?(?:ISSUE|CONDITION)(?:\s+\d+)?\s*[:\-]\s*(?P<condition>[^\n]+)"
        r"(?:\n(?:DATE OF (?:VA )?DECISION|DECISION DATE)\s*[:\-]\s*(?P<decision>[^\n]+))?"
        r"(?:\nSECONDARY TO(?: CONDITION)?\s*[:\-]\s*(?P<secondary>[^\n]+))?"
        r"(?:\n(?:DESCRIPTION|CLAIM DESCRIPTION)\s*[:\-]\s*(?P<description>[^\n]+))?"
        r"(?:\n(?:SERVICE EVENT|EVENT,? INJURY,? OR EXPOSURE|EVENT OR EXPOSURE)\s*[:\-]\s*(?P<event>[^\n]+))?"
        r"(?:\n(?:THEORY|THEORY OF SERVICE CONNECTION)\s*[:\-]\s*(?P<theory>[^\n]+))?",
        re.I,
    )
    seen = {str(item["condition"]).casefold() for item in suggestions}
    for page_number, text in pages:
        for index, match in enumerate(label_pattern.finditer(text), start=1):
            values = {
                "condition": (match.group("condition").strip(), "text:Condition"),
                "decision_date": ((match.group("decision") or "").strip(), "text:Decision date"),
                "secondary_to": ((match.group("secondary") or "").strip(), "text:Secondary to"),
                "description": ((match.group("description") or "").strip(), "text:Description"),
                "service_event": ((match.group("event") or "").strip(), "text:Service event"),
                "theory": ((match.group("theory") or "").strip(), "text:Theory"),
            }
            if values["condition"][0].casefold() not in seen:
                suggestions.append(_claim_payload(values, page_number, "embedded-text-or-ocr", str(index)))
                seen.add(values["condition"][0].casefold())
    return suggestions


def _claim_payload(values, page: int, method: str, row: str) -> dict[str, object]:
    def value(name):
        return values.get(name, ("", ""))[0]

    refs = {name: item[1] for name, item in values.items() if item[0]}
    condition = value("condition")
    return {
        "condition": condition,
        "secondary_to": value("secondary_to"),
        "description": value("description"),
        "service_event": value("service_event"),
        "theory": value("theory") or ("secondary" if value("secondary_to") else "direct"),
        "prior_decision_date": value("decision_date"),
        "source_page": page,
        "extraction_method": method,
        "field_references": refs,
        "confidence": .96 if method == "acroform" else .82,
        "supporting_text": f"Section 21A row {row}: {condition}"[:500],
    }


def extract_diagnoses(
    pages: list[tuple[int, str]], *, provider: str = "", facility: str = "", specialty: str = ""
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    seen: set[tuple[str, str, int]] = set()
    label = re.compile(
        r"\b(?:diagnosis|diagnoses|assessment|impression|problem(?: list)?|operative diagnosis|"
        r"discharge diagnosis)\s*[:\-]\s*([^\n.;]{2,150})",
        re.I,
    )
    for page, text in pages:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            lower = line.casefold()
            for match in label.finditer(line):
                diagnosis = match.group(1).strip(" :-")
                context = line[:500]
                uncertain = bool(re.search(r"\b(?:rule out|r/o|possible|suspected|differential|screening for)\b", lower))
                family = "family history" in lower
                status = "family_history" if family else ("suspected" if uncertain else (
                    "resolved" if re.search(r"\b(?:resolved|inactive|history of)\b", lower) else "confirmed"
                ))
                codes = _ICD10.findall(line)
                if not codes:
                    codes = _ICD9.findall(line)
                code = codes[0].upper() if codes else ""
                system = "ICD-10-CM" if code and re.match(r"[A-Z]", code) else ("ICD-9" if code else "")
                diagnosis = re.sub(r"\s*\(?\b(?:ICD(?:-10|-9)?\s*)?[A-TV-Z]?\d{2,3}(?:\.\d{1,4})?\)?\s*$", "", diagnosis, flags=re.I).strip(" ,-") or match.group(1)
                key = (diagnosis.casefold(), code, page)
                if key in seen:
                    continue
                seen.add(key)
                date = (_DATE.search(line) or _DATE.search(text[:1200]))
                output.append({
                    "diagnosis": diagnosis, "normalized_diagnosis": diagnosis.casefold(),
                    "code": code, "coding_system": system, "date": date.group(0) if date else "",
                    "provider": provider, "facility": facility, "specialty": specialty,
                    "status": status, "source_page": page, "context": context,
                    "confidence": .9 if status == "confirmed" else .68,
                })
            if (_ICD10.search(line) or _ICD9.search(line)) and not label.search(line):
                match = re.match(r"\s*([A-TV-Z]?\d{2,3}(?:\.\d{1,4})?)\s*[-:]\s*(.{3,120})", line, re.I)
                if match:
                    code, diagnosis = match.groups()
                    key = (diagnosis.casefold(), code.upper(), page)
                    if key not in seen:
                        seen.add(key)
                        output.append({
                            "diagnosis": diagnosis.strip(), "normalized_diagnosis": diagnosis.casefold(),
                            "code": code.upper(), "coding_system": "ICD-10-CM" if code[0].isalpha() else "ICD-9",
                            "date": "", "provider": provider, "facility": facility, "specialty": specialty,
                            "status": "confirmed", "source_page": page, "context": line[:500], "confidence": .84,
                        })
    return output


def extract_provider(text: str) -> dict[str, str]:
    patterns = {
        "provider": r"(?:Provider|Clinician|Physician|Examiner|Signed by|Electronically signed by)\s*[:\-]\s*(?:Dr\.\s*)?([A-Z][A-Za-z .,'-]{2,70})",
        "facility": r"(?:Facility|Clinic|Hospital|Medical Center)\s*[:\-]\s*([^\n;]{3,100})",
        "specialty": r"(?:Specialty|Department|Service)\s*[:\-]\s*([^\n;]{3,80})",
    }
    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        result[key] = match.group(1).strip() if match else ""
    return result


def parse_statement(classification: Classification, text: str) -> dict[str, object]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields: dict[str, object] = {
        "document_type": classification.document_type,
        "author_type": classification.author_type,
        "author": _label(text, "Author|From|Provider|Witness"),
        "credentials": _label(text, "Credentials"),
        "specialty": _label(text, "Specialty"),
        "condition": _label(text, "Condition|Claimed condition"),
        "primary_condition": _label(text, "Primary condition"),
        "secondary_condition": _label(text, "Secondary condition"),
        "relationship": _label(text, "Relationship to claimant"),
        "event_or_exposure": _label(text, "Service event|Event or exposure|Incident"),
        "onset": _label(text, "Onset"),
        "continuity": _label(text, "Continuity|Progression"),
        "functional_impact": _label(text, "Functional impact"),
        "occupational_impact": _label(text, "Occupational impact"),
        "rationale": _label(text, "Rationale"),
        "signature": _label(text, "Signature|Signed"),
        "date": _label(text, "Date|Signature date"),
        "opinion_language": next(
            (line for line in lines if re.search(r"at least as likely|more likely than not|less likely than not", line, re.I)),
            "",
        ),
    }
    fields["signed"] = bool(fields["signature"] or re.search(r"\belectronically signed\b", text, re.I))
    fields["status"] = "final" if fields["signed"] else "draft"
    fields["source_excerpt"] = "\n".join(lines[:12])[:1000]
    return fields


def personal_timeline_events(pages: list[tuple[int, str]]) -> list[dict[str, object]]:
    events = []
    for page, text in pages:
        for line in (line.strip() for line in text.splitlines() if line.strip()):
            date = _DATE.search(line)
            if not date:
                continue
            event_type = "exposure" if re.search(r"\bexpos", line, re.I) else (
                "incident" if re.search(r"\b(?:injur|incident|accident)\b", line, re.I) else (
                    "onset" if re.search(r"\b(?:onset|began|started)\b", line, re.I) else "continuity"
                )
            )
            events.append({
                "event_date": date.group(0), "event_type": event_type, "title": line[:100],
                "description": line, "source_page": page, "source_type": "veteran_reported",
                "confidence": .78,
            })
    return events


def _label(text: str, names: str) -> str:
    match = re.search(rf"^(?:{names})\s*[:\-]\s*(.+)$", text, re.I | re.M)
    return match.group(1).strip() if match else ""
