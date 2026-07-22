from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable

BINDING_LEVELS = {
    "statute": 100,
    "regulation": 95,
    "federal_circuit_precedential": 90,
    "cavc_precedential": 85,
    "va_general_counsel_precedent": 80,
    "cavc_nonprecedential": 35,
    "bva_decision": 20,
    "secondary_summary": 10,
}

@dataclass
class LegalAuthority:
    title: str
    citation: str
    authority_type: str
    source_url: str
    proposition: str
    quoted_text: str = ""
    current_as_of: str = ""
    verified: bool = False
    negative_treatment: str = ""

    @property
    def weight(self) -> int:
        return BINDING_LEVELS.get(self.authority_type, 0)

    @property
    def binding_label(self) -> str:
        if self.authority_type in {"statute", "regulation", "federal_circuit_precedential", "cavc_precedential", "va_general_counsel_precedent"}:
            return "binding_or_controlling"
        if self.authority_type == "bva_decision":
            return "nonprecedential_fact_pattern_only"
        return "persuasive_or_research_only"

class CaseLawEngine:
    """Validates, ranks, and maps legal authorities to claim propositions.

    The engine never treats a citation as proof of a factual or medical premise.
    It requires a verified source URL and stores adverse/limiting treatment.
    """
    def validate(self, authority: LegalAuthority) -> list[str]:
        issues = []
        if not authority.title.strip(): issues.append("missing_title")
        if not authority.citation.strip(): issues.append("missing_citation")
        if not authority.source_url.startswith("https://"): issues.append("missing_official_https_source")
        if authority.authority_type not in BINDING_LEVELS: issues.append("unknown_authority_type")
        if not authority.proposition.strip(): issues.append("missing_holding_or_proposition")
        if authority.authority_type == "bva_decision" and "nonprecedential" not in authority.negative_treatment.lower():
            issues.append("bva_nonprecedential_warning_required")
        if not authority.verified: issues.append("human_verification_required")
        return issues

    def rank(self, authorities: Iterable[LegalAuthority]) -> list[LegalAuthority]:
        return sorted(authorities, key=lambda a: (a.verified, a.weight), reverse=True)

    def build_issue_map(self, claim_elements: list[str], authorities: Iterable[LegalAuthority]) -> dict:
        ranked = self.rank(authorities)
        return {
            "claim_elements": claim_elements,
            "authorities": [{**asdict(a), "weight": a.weight, "binding_label": a.binding_label,
                              "validation_issues": self.validate(a)} for a in ranked],
            "guardrails": [
                "Legal authority explains the governing rule; it does not establish the veteran-specific medical facts.",
                "Use precedential CAVC/Federal Circuit decisions and current statutes/regulations before nonprecedential decisions.",
                "Board decisions are nonprecedential and may be used only as fact-pattern research, not as binding authority.",
                "Verify subsequent history, amendments, and negative treatment before inclusion.",
                "An accredited representative or attorney should review legal argument before filing.",
            ],
        }

    def research_queries(self, condition: str, theory: str, denial_reasons: list[str]) -> list[str]:
        topics = [condition, theory] + denial_reasons
        base = " ".join(x for x in topics if x)
        return [
            f'site:uscourts.cavc.gov {base} precedential opinion',
            f'site:law.cornell.edu/cfr/text/38 {base}',
            f'site:va.gov/ogc precedent opinion {base}',
            f'site:va.gov/vetapp {base}',
        ]
