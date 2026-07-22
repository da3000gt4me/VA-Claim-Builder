from core.analysis.schemas import ClaimAssessment

def test_minimal_assessment():
    value = ClaimAssessment(
        claim="Migraine", theory="aggravation", diagnosis_status="supported",
        in_service_status="partial", nexus_status="missing", severity_summary="Needs review",
        evidence_strength="limited", annotations=[], gaps=["Signed opinion"], contradictions=[], recommended_actions=[])
    assert value.claim == "Migraine"
