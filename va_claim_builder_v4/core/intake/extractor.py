
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import datetime

EXTRACTION_VERSION = "4.2.0-rc6-local-1"


def _unique(values):
    seen = set()
    return [value for value in values if value and not (value.casefold() in seen or seen.add(value.casefold()))]


@dataclass(slots=True)
class LocalExtraction:
    dates: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    facilities: list[str] = field(default_factory=list)
    specialties: list[str] = field(default_factory=list)
    diagnoses: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)
    imaging: list[str] = field(default_factory=list)
    laboratory_testing: list[str] = field(default_factory=list)
    functional_impacts: list[str] = field(default_factory=list)
    occupational_impacts: list[str] = field(default_factory=list)
    onset_statements: list[str] = field(default_factory=list)
    chronicity_statements: list[str] = field(default_factory=list)
    aggravation_statements: list[str] = field(default_factory=list)
    nexus_statements: list[str] = field(default_factory=list)
    contradictory_statements: list[str] = field(default_factory=list)
    relationship_statements: list[str] = field(default_factory=list)
    page_excerpts: list[dict] = field(default_factory=list)
    document_type: str = "other"
    document_type_confidence: float = 0.0
    form_revision: str = ""
    claim_suggestions: list[dict] = field(default_factory=list)
    diagnosis_details: list[dict] = field(default_factory=list)
    timeline_entries: list[dict] = field(default_factory=list)
    imported_statement: dict = field(default_factory=dict)

    def count(self) -> int:
        return sum(
            len(value) for descriptor in fields(self)
            if hasattr((value := getattr(self, descriptor.name)), "__len__")
        )


class LocalMedicalExtractor:
    """Conservative rules that produce review candidates, never medical conclusions."""

    DATE = re.compile(
        r"\b((?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])|"
        r"(?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])[-/](?:19|20)?\d{2}|"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+(?:19|20)\d{2})\b",
        re.I,
    )
    LAB_TERMS = r"(?:CBC|CMP|A1C|ESR|CRP|blood test|laboratory|lab result|urinalysis)"
    IMAGE_TERMS = r"(?:MRI|CT scan|X[- ]?ray|ultrasound|radiograph|imaging)"
    PROCEDURE_TERMS = r"(?:surgery|injection|physical therapy|procedure|arthroscopy|fusion|biopsy)"

    def extract(self, text: str, *, filename: str = "", acroform_fields: dict | None = None) -> LocalExtraction:
        from .structured import (
            classify_document, extract_diagnoses, extract_provider, parse_20_0995,
            parse_statement, personal_timeline_events,
        )
        result = LocalExtraction()
        pages = self._pages(text)
        for page, page_text in pages:
            for sentence in self._sentences(page_text):
                lower = sentence.casefold()
                dates = [self._date(value) for value in self.DATE.findall(sentence)]
                result.dates.extend(dates)
                self._labels(sentence, result)
                if re.search(r"\b(diagnos(?:is|ed)|assessment|impression)\s*[:\-]", sentence, re.I):
                    result.diagnoses.extend(self._value(sentence))
                if re.search(r"\b(symptoms?|complains? of|reports?|endorses?)\s*[:\-]", sentence, re.I):
                    result.symptoms.extend(self._value(sentence))
                if re.search(r"\b(medications?|meds?|prescribed|started)\s*[:\-]", sentence, re.I):
                    result.medications.extend(self._value(sentence))
                if re.search(self.PROCEDURE_TERMS, sentence, re.I):
                    result.procedures.append(sentence)
                if re.search(self.IMAGE_TERMS, sentence, re.I):
                    result.imaging.append(sentence)
                if re.search(self.LAB_TERMS, sentence, re.I):
                    result.laboratory_testing.append(sentence)
                if any(term in lower for term in ("limits ", "difficulty ", "unable to ", "interferes with", "functional impact")):
                    result.functional_impacts.append(sentence)
                if any(term in lower for term in ("work", "occupation", "job", "missed shifts", "absent from")):
                    result.occupational_impacts.append(sentence)
                if any(term in lower for term in ("began", "onset", "started in", "since ")):
                    result.onset_statements.append(sentence)
                if any(term in lower for term in ("chronic", "persistent", "ongoing", "recurrent", "continuous")):
                    result.chronicity_statements.append(sentence)
                if any(term in lower for term in ("aggravated", "worsened by", "made worse", "baseline")):
                    result.aggravation_statements.append(sentence)
                if any(term in lower for term in ("due to", "caused by", "secondary to", "associated with")):
                    result.relationship_statements.append(sentence)
                if any(term in lower for term in ("at least as likely", "more likely than not", "related to service")):
                    result.nexus_statements.append(sentence)
                if any(term in lower for term in ("denies", "no evidence of", "normal examination", "resolved")):
                    result.contradictory_statements.append(sentence)
                if dates or self._is_medical(sentence):
                    result.page_excerpts.append({"page": page, "text": sentence[:500]})
        for descriptor in fields(result):
            name = descriptor.name
            values = getattr(result, name)
            if name != "page_excerpts" and isinstance(values, list) and (
                not values or isinstance(values[0], str)
            ):
                setattr(result, name, _unique(values))
        seen = set()
        result.page_excerpts = [
            item for item in result.page_excerpts
            if not ((item["page"], item["text"].casefold()) in seen or seen.add((item["page"], item["text"].casefold())))
        ]
        classification = classify_document(text, filename=filename, fields=acroform_fields)
        result.document_type = classification.document_type
        result.document_type_confidence = classification.confidence
        result.form_revision = classification.revision
        provider = extract_provider(text)
        for key, target in (("provider", result.providers), ("facility", result.facilities), ("specialty", result.specialties)):
            if provider.get(key):
                target[:] = _unique([*target, provider[key]])
        result.diagnosis_details = extract_diagnoses(
            pages, provider=provider["provider"], facility=provider["facility"], specialty=provider["specialty"]
        )
        result.diagnoses = _unique([
            *result.diagnoses,
            *(item["diagnosis"] for item in result.diagnosis_details if item["status"] == "confirmed"),
        ])
        if classification.document_type == "va_form_20_0995":
            result.claim_suggestions = parse_20_0995(pages, fields=acroform_fields)
        if classification.document_type == "personal_timeline":
            result.timeline_entries = personal_timeline_events(pages)
        if classification.document_type in {
            "claimant_nexus_statement", "provider_nexus_letter", "buddy_witness_statement"
        }:
            result.imported_statement = parse_statement(classification, text)
        return result

    @staticmethod
    def _pages(text):
        matches = list(re.finditer(r"^--- PAGE (\d+) ---\s*$", text, re.M))
        if not matches:
            return [(1, text)]
        pages = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            pages.append((int(match.group(1)), text[match.end():end]))
        return pages

    @staticmethod
    def _sentences(text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        output = []
        for line in lines:
            output.extend(part.strip() for part in re.split(r"(?<!Dr\.)(?<=[.!?])\s+", line) if part.strip())
        return output

    @staticmethod
    def _value(sentence):
        value = re.split(r"[:\-]", sentence, maxsplit=1)[-1].strip(" .")
        return [part.strip(" .") for part in re.split(r"[,;]", value) if 2 < len(part.strip()) < 120]

    @staticmethod
    def _labels(sentence, result):
        patterns = {
            "providers": r"\b(?:Provider|Clinician|Examiner|Physician)\s*[:\-]?\s*(?:Dr\.\s*)?([A-Z][A-Za-z '-]{2,60})",
            "facilities": r"\b(?:Facility|Clinic|Hospital|Medical Center)\s*[:\-]\s*([^.;]{3,80})",
            "specialties": r"\b(?:Specialty|Department)\s*[:\-]\s*([^.;]{3,60})",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, sentence)
            if match:
                getattr(result, field).append(match.group(1).strip())

    @staticmethod
    def _date(value):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                pass
        return value

    @staticmethod
    def _is_medical(sentence):
        return bool(re.search(
            r"\b(diagnos|symptom|pain|medication|treatment|exam|imaging|MRI|X-ray|laboratory|"
            r"provider|clinic|hospital|function|work|aggravat|secondary)\b", sentence, re.I
        ))
