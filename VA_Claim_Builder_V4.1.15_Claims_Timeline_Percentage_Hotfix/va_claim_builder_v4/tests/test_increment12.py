from pathlib import Path
from core.storage.project_db import ProjectDB
from core.workflow.candidate_promotion import CandidateClaimPromotionService
from core.workflow.project_backup import ProjectBackupService
from core.workflow.orchestrator import ProjectOrchestrator


def test_candidate_promotion_creates_claim_and_full_plan(tmp_path):
    db=ProjectDB(tmp_path/'p.db'); pid=db.ensure_default_project()
    candidate={"condition":"GERD or reflux disorder","possible_theories":["direct","secondary/aggravation"],"recommended_specialty":"Gastroenterology"}
    result=CandidateClaimPromotionService().promote(db,pid,candidate)
    assert result.created is True
    assert len(result.document_plan)==8
    assert any(x['output_type']=='clinician_nexus_packet' and x['recommended_specialty']=='Gastroenterology' for x in result.document_plan)


def test_candidate_promotion_is_idempotent(tmp_path):
    db=ProjectDB(tmp_path/'p.db'); pid=db.ensure_default_project()
    c={"condition":"Hypertension","possible_theories":["direct"]}
    one=CandidateClaimPromotionService().promote(db,pid,c)
    two=CandidateClaimPromotionService().promote(db,pid,c)
    assert one.claim_id==two.claim_id
    assert two.created is False
    assert len(db.list_claims(pid))==1


def test_backup_roundtrip_validation(tmp_path):
    root=tmp_path/'project'; root.mkdir(); (root/'a.txt').write_text('alpha'); (root/'nested').mkdir(); (root/'nested'/'b.txt').write_text('beta')
    svc=ProjectBackupService(); result=svc.create(root,tmp_path/'exports')
    validation=svc.validate(result['backup_zip'])
    assert validation['valid'] is True
    assert validation['file_count']==2


def test_orchestrator_reports_pending_review(tmp_path):
    db=ProjectDB(tmp_path/'p.db'); pid=db.ensure_default_project(); db.add_claim(pid,'Migraine headaches','direct')
    plan=ProjectOrchestrator().build_plan(db,pid)
    assert plan['summary']['claim_count']==1
    assert plan['ready_for_final_assembly'] is False
    assert plan['next_actions']
