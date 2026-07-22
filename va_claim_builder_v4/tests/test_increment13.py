from pathlib import Path
from core.storage.project_db import ProjectDB
from core.workflow.migrations import MigrationManager
from core.workflow.recovery import WorkflowRecoveryService
from core.workflow.system_health import SystemHealthChecker
from core.workflow.one_click import OneClickProjectProcessor
from core.workflow.security_review import SecurityReview

def test_migration_and_recovery(tmp_path):
    db=ProjectDB(tmp_path/'p.db'); pid=db.ensure_default_project()
    result=MigrationManager(db.path).migrate(); assert result['to']==13
    svc=WorkflowRecoveryService(db.path); rid=svc.start(pid,'test'); svc.checkpoint(rid,.5,{'x':1})
    assert svc.resumable(pid)[0]['checkpoint']['x']==1
    svc.complete(rid); assert svc.resumable(pid)==[]

def test_health_and_security(tmp_path):
    db=ProjectDB(tmp_path/'p.db'); db.ensure_default_project()
    MigrationManager(db.path).migrate()
    health=SystemHealthChecker(tmp_path).run(db.path)
    assert health['overall'] in {'ready','blocked'}
    assert any(c['name']=='Database integrity' and c['status']=='pass' for c in health['checks'])
    assert SecurityReview().run(tmp_path)['status'] in {'pass','review_required'}

def test_one_click(tmp_path):
    db=ProjectDB(tmp_path/'p.db'); pid=db.ensure_default_project(); MigrationManager(db.path).migrate()
    db.add_claim(pid,'Migraine headaches','direct')
    result=OneClickProjectProcessor(db,pid,tmp_path).run()
    assert result['status']=='complete'
    assert len(result['stages'])==6
