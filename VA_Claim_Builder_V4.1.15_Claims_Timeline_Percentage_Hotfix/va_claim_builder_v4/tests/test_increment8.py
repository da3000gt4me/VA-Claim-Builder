from core.rating.criteria_engine import RatingCriteriaEngine
from core.rating.staged_severity import StagedSeverityAnalyzer
from core.decisions.denial_response import DenialDecisionAnalyzer
from core.analysis.submission_gate import SubmissionReadinessGate

CLAIM={"id":"c1","condition_name":"Migraine headaches","theory":"direct"}

def ann(text):
    return {"claim_id":"c1","review_status":"approved","finding":text,"quote":text,"reviewer_note":"","created_at":"2025-01-01"}

def test_rating_engine_does_not_promote_partial_criteria():
    result=RatingCriteriaEngine().evaluate(CLAIM,[ann("Monthly headaches")],[])
    thirty=[x for x in result["levels"] if x["percentage"]==30][0]
    assert thirty["status"]=="partially_supported"
    assert result["best_supported_level"] is None

def test_rating_engine_supports_only_when_all_concepts_are_present():
    result=RatingCriteriaEngine().evaluate(CLAIM,[ann("Characteristic prostrating attacks occur monthly")],[])
    assert result["best_supported_level"]==30

def test_denial_parser_extracts_missing_nexus():
    result=DenialDecisionAnalyzer().analyze_text("Service connection is denied because there is no nexus and the condition is not related to service.")
    assert "nexus" in result["missing_elements"]

def test_staged_severity_detects_change():
    timeline=[{"claim_id":"c1","event_date_start":"2020","description":"Mild headaches"},{"claim_id":"c1","event_date_start":"2024","description":"Severe prostrating headaches"}]
    assert StagedSeverityAnalyzer().analyze("c1",[],timeline)["possible_staged_severity"] is True

def test_submission_gate_blocks_missing_elements():
    gate=SubmissionReadinessGate().assess(CLAIM,{"missing_elements":["nexus"]},{"profile":"migraine"},[],[])
    assert gate["blocked"] is True
