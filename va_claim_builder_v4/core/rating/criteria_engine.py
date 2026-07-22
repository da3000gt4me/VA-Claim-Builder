from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class CriterionLevel:
    percentage: int
    label: str
    required_concepts: tuple[str, ...]
    description: str

# Starter library only. Users must verify the currently applicable diagnostic code and criteria.
STARTER_CRITERIA: dict[str, dict[str, Any]] = {
    "migraine": {
        "diagnostic_code": "8100",
        "levels": [
            CriterionLevel(0, "Less frequent attacks", ("headache",), "Documented attacks do not meet compensable frequency."),
            CriterionLevel(10, "Characteristic prostrating attacks", ("prostrating", "two months"), "Characteristic prostrating attacks averaging one in two months."),
            CriterionLevel(30, "Monthly prostrating attacks", ("prostrating", "monthly"), "Characteristic prostrating attacks occurring about monthly."),
            CriterionLevel(50, "Very frequent, prolonged, economically impairing", ("very frequent", "prostrating", "prolonged", "economic"), "Very frequent completely prostrating and prolonged attacks with severe occupational/economic impact."),
        ],
    },
    "tinnitus": {
        "diagnostic_code": "6260",
        "levels": [CriterionLevel(10, "Recurrent tinnitus", ("recurrent tinnitus",), "Recurrent tinnitus is documented.")],
    },

    "sleep_apnea": {
        "diagnostic_code": "6847",
        "levels": [
            CriterionLevel(0, "Documented but asymptomatic", ("sleep apnea",), "Diagnosis is documented without the configured compensable manifestations."),
            CriterionLevel(30, "Persistent daytime hypersomnolence", ("daytime hypersomnolence",), "Persistent daytime hypersomnolence is documented."),
            CriterionLevel(50, "Requires breathing-assistance device", ("cpap",), "Use of a prescribed breathing-assistance device is documented."),
            CriterionLevel(100, "Severe respiratory complications", ("chronic respiratory failure", "carbon dioxide retention"), "Severe respiratory complications are documented."),
        ],
    },
    "ibs": {
        "diagnostic_code": "7319",
        "levels": [
            CriterionLevel(0, "Mild disturbance", ("bowel disturbance",), "Mild bowel disturbance is documented."),
            CriterionLevel(10, "Frequent bowel disturbance", ("frequent", "abdominal distress"), "Frequent episodes with abdominal distress are documented."),
            CriterionLevel(30, "Severe near-constant distress", ("diarrhea", "constipation", "constant abdominal distress"), "Severe manifestations with near-constant abdominal distress are documented."),
        ],
    },
    "allergic_rhinitis": {
        "diagnostic_code": "6522",
        "levels": [
            CriterionLevel(10, "Obstruction without polyps", ("nasal obstruction",), "Qualifying nasal obstruction is documented."),
            CriterionLevel(30, "With polyps", ("nasal polyps",), "Nasal polyps are documented."),
        ],
    },
    "sinusitis": {
        "diagnostic_code": "6510-6514",
        "levels": [
            CriterionLevel(10, "Documented episodes", ("incapacitating episode", "antibiotic"), "Qualifying treatment episodes require verification."),
            CriterionLevel(30, "Frequent qualifying episodes", ("recurrent sinusitis", "headache", "purulent discharge"), "Frequent qualifying episodes require verification."),
            CriterionLevel(50, "Near-constant or post-surgical severe disease", ("near constant sinusitis", "radical surgery"), "Severe or post-surgical findings require verification."),
        ],
    },
    "voiding_dysfunction": {
        "diagnostic_code": "Voiding Dysfunction",
        "levels": [
            CriterionLevel(10, "Urinary frequency", ("daytime voiding", "nighttime awakening"), "Frequency measurements are documented."),
            CriterionLevel(20, "Increased frequency or absorbent materials", ("one to two hours",), "Configured frequency threshold is documented."),
            CriterionLevel(40, "Severe frequency or absorbent materials", ("less than one hour",), "Configured severe frequency threshold is documented."),
        ],
    },
    "spine": {
        "diagnostic_code": "General Rating Formula for the Spine",
        "levels": [
            CriterionLevel(10, "Limited motion or painful motion", ("painful motion",), "Objective or functionally limiting painful motion is documented."),
            CriterionLevel(20, "Moderate limitation", ("forward flexion", "muscle spasm"), "Measurements and associated findings require verification."),
            CriterionLevel(30, "Cervical severe limitation", ("cervical flexion", "15 degrees"), "Cervical measurement threshold requires verification."),
            CriterionLevel(40, "Severe limitation or ankylosis", ("ankylosis",), "Ankylosis or qualifying severe limitation is documented."),
        ],
    },
    "tmj": {
        "diagnostic_code": "9905",
        "levels": [
            CriterionLevel(10, "Limited interincisal range", ("interincisal", "millimeters"), "Measured jaw-opening limitation requires verification."),
            CriterionLevel(20, "Greater limitation", ("interincisal", "dietary restrictions"), "Measurement plus dietary restrictions require verification."),
        ],
    },
    "erectile_dysfunction": {
        "diagnostic_code": "7522 / SMC-K review",
        "levels": [CriterionLevel(0, "Loss of erectile function documented", ("erectile dysfunction",), "Evaluate applicable schedular and special monthly compensation provisions separately.")],
    },
    "mental_health": {
        "diagnostic_code": "General Rating Formula",
        "levels": [
            CriterionLevel(10, "Mild or transient impairment", ("mild", "occupational impairment"), "Symptoms cause mild/transient occupational and social impairment or are controlled by medication."),
            CriterionLevel(30, "Occasional decrease in work efficiency", ("depressed mood", "anxiety", "sleep impairment"), "Symptoms produce occasional decrease in work efficiency with generally satisfactory functioning."),
            CriterionLevel(50, "Reduced reliability and productivity", ("reduced reliability", "productivity", "relationship difficulty"), "Symptoms produce reduced reliability/productivity and meaningful social or occupational impairment."),
            CriterionLevel(70, "Deficiencies in most areas", ("deficiencies", "work", "family", "judgment", "mood"), "Symptoms produce deficiencies in most areas with serious functional impairment."),
            CriterionLevel(100, "Total occupational and social impairment", ("total occupational", "total social"), "Evidence documents total occupational and social impairment."),
        ],
    },
}

ALIASES = {
    "migraine headaches": "migraine", "migraines": "migraine", "migraine": "migraine",
    "tinnitus": "tinnitus",
    "anxiety": "mental_health", "depression": "mental_health", "anxiety and depression": "mental_health",
    "acquired psychiatric disorder": "mental_health", "mental health": "mental_health",
    "sleep apnea": "sleep_apnea", "obstructive sleep apnea": "sleep_apnea", "sleep disorder": "sleep_apnea",
    "irritable bowel syndrome": "ibs", "ibs": "ibs",
    "allergic rhinitis": "allergic_rhinitis", "rhinitis": "allergic_rhinitis",
    "chronic sinusitis": "sinusitis", "sinusitis": "sinusitis",
    "urinary frequency": "voiding_dysfunction", "voiding dysfunction": "voiding_dysfunction",
    "cervical spine": "spine", "lumbar spine": "spine", "back strain": "spine",
    "tmj": "tmj", "temporomandibular": "tmj",
    "erectile dysfunction": "erectile_dysfunction",
}

class RatingCriteriaEngine:
    def identify_profile(self, condition_name: str) -> str | None:
        name = condition_name.lower().strip()
        for alias, profile in ALIASES.items():
            if alias in name:
                return profile
        return None

    def evaluate(self, claim: dict[str, Any], approved_annotations: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> dict[str, Any]:
        profile_name = self.identify_profile(claim.get("condition_name", ""))
        if not profile_name:
            return {"claim_id": claim["id"], "condition_name": claim["condition_name"], "profile": None,
                    "status": "criteria_profile_needed", "levels": [], "best_supported_level": None,
                    "warning": "No starter rating profile is mapped. Add and verify the applicable criteria before relying on this analysis."}
        profile = STARTER_CRITERIA[profile_name]
        text = " ".join(str(a.get(k, "")) for a in approved_annotations if a.get("claim_id") == claim["id"] and a.get("review_status") == "approved" for k in ("finding", "quote", "reviewer_note")).lower()
        text += " " + " ".join(str(e.get("description", "")) for e in timeline if e.get("claim_id") == claim["id"]).lower()
        rows=[]
        best=None
        for level in profile["levels"]:
            matches=[concept for concept in level.required_concepts if concept.lower() in text]
            missing=[concept for concept in level.required_concepts if concept.lower() not in text]
            ratio=len(matches)/max(1,len(level.required_concepts))
            status="supported" if not missing else ("partially_supported" if matches else "not_documented")
            if status=="supported" and level.percentage > 0 and (best is None or level.percentage>best): best=level.percentage
            rows.append({**asdict(level),"matched_concepts":matches,"missing_concepts":missing,"coverage":round(ratio,2),"status":status})
        return {"claim_id":claim["id"],"condition_name":claim["condition_name"],"profile":profile_name,
                "diagnostic_code":profile["diagnostic_code"],"levels":rows,"best_supported_level":best,
                "status":"review_required","warning":"Preliminary evidence-to-criteria comparison only. Verify the current regulation, diagnostic code, medical findings, and effective-date rules before filing."}
