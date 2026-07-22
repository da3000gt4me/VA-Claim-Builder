from __future__ import annotations
from dataclasses import dataclass, asdict
import re
from typing import Iterable, Any

@dataclass(frozen=True)
class ConditionProfile:
    name: str
    current_terms: tuple[str, ...]
    service_terms: tuple[str, ...]
    possible_theories: tuple[str, ...]
    specialist: str
    rationale: str

PROFILES = (
    ConditionProfile("Lumbar spine condition", ("lumbar", "low back", "back pain", "spondylosis", "disc protrusion", "radiculopathy"), ("lifting", "carrying", "ruck", "mountain", "fall", "physical training", "heavy equipment"), ("direct", "secondary/aggravation"), "Orthopedics or PM&R", "Current lumbar pathology may be relevant when service records or credible history document heavy lifting, falls, repetitive load, or persistent back symptoms."),
    ConditionProfile("Bilateral knee condition", ("knee pain", "meniscus", "patellofemoral", "chondromalacia", "arthritis", "knee mri"), ("running", "marching", "stairs", "kneeling", "physical training", "carrying", "mountain"), ("direct", "secondary/aggravation"), "Orthopedics", "Current knee findings may be traceable to repetitive impact, load-bearing activity, or documented in-service symptoms."),
    ConditionProfile("Shoulder condition", ("shoulder pain", "rotator cuff", "impingement", "labral", "shoulder mri", "ac joint"), ("lifting", "carrying", "overhead", "weapons", "physical training", "fall"), ("direct", "secondary/aggravation"), "Orthopedics", "Shoulder pathology may be relevant where military duties involved repetitive lifting, carrying, overhead work, weapons handling, or injury."),
    ConditionProfile("Upper-extremity radiculopathy or neuropathy", ("radiculopathy", "neuropathy", "numbness", "tingling", "paresthesia", "weakness"), ("neck injury", "cervical", "lifting", "carrying", "repetitive"), ("secondary to cervical spine", "direct"), "Neurology or PM&R", "Neurologic symptoms in an arm or hand may be separately ratable or secondary to a cervical-spine disorder when objectively supported."),
    ConditionProfile("Lower-extremity radiculopathy or neuropathy", ("sciatica", "lumbar radiculopathy", "leg numbness", "leg tingling", "foot numbness", "weakness"), ("back injury", "lumbar", "lifting", "carrying", "fall"), ("secondary to lumbar spine", "direct"), "Neurology or PM&R", "Neurologic leg symptoms may be separately ratable or secondary to a lumbar-spine disorder when supported by examination or testing."),
    ConditionProfile("Bruxism / dental residuals", ("bruxism", "grinding", "clenching", "cracked molar", "tooth fracture", "night guard"), ("stress", "operational pressure", "shift work", "jaw pain"), ("secondary to psychiatric condition or TMJ", "direct"), "Dentistry or Oral Surgery", "Documented grinding, clenching, or dental damage may support residuals associated with TMJ or a psychiatric/sleep condition, although dental compensation rules require careful review."),
    ConditionProfile("Chronic fatigue or daytime somnolence", ("fatigue", "daytime sleepiness", "somnolence", "nonrestorative sleep", "hypersomnolence"), ("rotating shift", "12-hour shift", "circadian", "sleep disruption"), ("secondary to sleep disorder", "direct"), "Sleep Medicine", "Persistent fatigue or hypersomnolence may be relevant as a symptom, residual, or separate diagnosis depending on the medical record and avoidance of pyramiding."),
    ConditionProfile("Dermatologic condition", ("dermatitis", "eczema", "rash", "urticaria", "contact dermatitis", "skin lesion"), ("chemical exposure", "oc spray", "dust", "humidity", "uniform", "protective equipment"), ("direct", "secondary/aggravation"), "Dermatology or Allergy", "Current chronic skin disease may warrant review when service records or credible history show onset, recurrent rash, or relevant exposures."),
    ConditionProfile("GERD or reflux disorder", ("gerd", "reflux", "heartburn", "esophagitis", "acid reflux"), ("stress", "shift work", "medication", "gastrointestinal symptoms"), ("direct", "secondary/aggravation"), "Gastroenterology", "Current reflux disease may be relevant when records show onset or worsening during service, medication effects, or a medically supported relationship to another condition."),
    ConditionProfile("Hypertension", ("hypertension", "high blood pressure", "elevated blood pressure"), ("elevated blood pressure", "stress", "shift work"), ("direct", "secondary/aggravation"), "Primary Care or Cardiology", "Repeated elevated readings during service or a clinician-supported secondary/aggravation theory may justify review."),
)

NEGATIVE = re.compile(r"\b(denies?|no evidence of|negative for|without|resolved|rule out)\b", re.I)

class PotentialClaimDiscoveryEngine:
    """Conservative discovery aid. It finds traceable hypotheses, not diagnoses or nexus opinions."""

    def _text(self, rows: Iterable[dict[str, Any]]) -> str:
        parts=[]
        for row in rows:
            for key in ("finding","quote","description","text","proposition","diagnosis","condition_name"):
                value=row.get(key)
                if value: parts.append(str(value))
        return "\n".join(parts)

    def discover(self, existing_claims: list[dict[str, Any]], military_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]) -> dict[str, Any]:
        claimed=" ".join(c.get("condition_name","").lower() for c in existing_claims)
        military=self._text(military_rows).lower()
        current=self._text(current_rows).lower()
        candidates=[]
        for profile in PROFILES:
            if any(term in claimed for term in profile.current_terms) or profile.name.lower() in claimed:
                continue
            current_hits=[t for t in profile.current_terms if t in current]
            service_hits=[t for t in profile.service_terms if t in military]
            # Require affirmative present-day evidence and at least one service anchor.
            affirmative=[]
            for row in current_rows:
                text=self._text([row])
                if any(t in text.lower() for t in profile.current_terms) and not NEGATIVE.search(text):
                    affirmative.append(row)
            if not affirmative or not service_hits:
                continue
            score=min(1.0, .35 + .12*len(set(current_hits)) + .10*len(set(service_hits)) + .05*min(len(affirmative),4))
            candidates.append({
                "condition": profile.name,
                "possible_theories": list(profile.possible_theories),
                "recommended_specialty": profile.specialist,
                "current_evidence_terms": sorted(set(current_hits)),
                "service_anchor_terms": sorted(set(service_hits)),
                "why_review": profile.rationale,
                "confidence": round(score,2),
                "status": "potential_additional_claim_for_human_review",
                "limitations": "This is a discovery hypothesis only. Confirm a current diagnosis, an applicable service-connection theory, competent nexus evidence, and anti-pyramiding considerations before filing.",
            })
        candidates.sort(key=lambda x:(-x["confidence"],x["condition"]))
        return {"candidates":candidates,"prompt":self.build_user_prompt(candidates),"disclaimer":"The module does not diagnose conditions or recommend filing solely from keyword matches. It requires affirmative current evidence plus a service-history anchor and excludes negated passages."}

    def build_user_prompt(self, candidates: list[dict[str, Any]]) -> str:
        if not candidates:
            return ("I compared the currently identified claims with the available military-history, military-medical, and current-medical evidence. "
                    "I did not find an additional condition with both affirmative current evidence and a plausible service anchor strong enough to recommend adding at this stage. "
                    "Continue reviewing new records as they are added.")
        lines=["I found the following potential additional condition(s) that may warrant inclusion in your VA package after human and clinician review:"]
        for i,c in enumerate(candidates,1):
            theories=", ".join(c["possible_theories"])
            lines.append(f"{i}. {c['condition']} — Possible theory: {theories}. Why it may be relevant: {c['why_review']} Current-record indicators: {', '.join(c['current_evidence_terms']) or 'affirmative findings located'}. Military/service anchors: {', '.join(c['service_anchor_terms'])}.")
        lines.append("These are potential claims, not confirmed service-connected disabilities. Before adding them, verify the diagnosis, avoid duplicate compensation for the same manifestations, and obtain any needed medical opinion.")
        lines.append("Would you like me to build the same full set of associated documents for these additional claim(s)—including the evidence map, personal statement, historical timeline, draft clinician nexus packet, tailored buddy-letter prompts, rating-criteria review, evidence-gap plan, and final-package integration?")
        return "\n\n".join(lines)
