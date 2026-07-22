from pathlib import Path
from core.analysis.semantic_evidence import SemanticEvidenceAnalyzer
from core.analysis.evidence_autofill import EvidenceAutofillService
from core.analysis.claim_element_summary import ClaimElementSummary
from core.storage.project_db import ProjectDB

def claim(theory='direct'):
    return {'id':'clm1','condition_name':'Acquired psychiatric disorder with anxiety and depressive features','theory':theory}

def chunk(text,page=1,doc='doc1'):
    return {'id':f'pg_{doc}_{page}','document_id':doc,'document_name':'record.pdf','category':'medical_records','page':page,'text':text,'ocr_confidence':.98}

def test_explanation_fields_present():
    rows=SemanticEvidenceAnalyzer().analyze_chunks(claim(),[chunk('Assessment: major depressive disorder. Anxiety causes difficulty concentrating at work.')])
    support=[r for r in rows if r['auto_action']=='suggest_for_autofill']
    assert support and support[0]['proposition'] and support[0]['supports_because'] and support[0]['limitations']

def test_copy_forward_is_not_auto_suggested():
    text='Assessment: anxiety disorder, stable. Continue current plan.'
    rows=SemanticEvidenceAnalyzer().analyze_chunks(claim(),[chunk(text,1),chunk(text,2),chunk(text,3)])
    assert rows and all(r['copy_forward_risk']=='high' for r in rows)
    assert all(r['auto_action']!='suggest_for_autofill' for r in rows)

def test_negative_cannot_autofill(tmp_path:Path):
    db=ProjectDB(tmp_path/'db.sqlite'); pid=db.create_project('x'); cid=db.add_claim(pid,'Anxiety and depression','direct')
    did=db.add_document({'project_id':pid,'category':'medical_records','original_name':'x.pdf','original_path':'x.pdf','sha256':'abc'})
    c=SemanticEvidenceAnalyzer().analyze_chunks({'id':cid,'condition_name':'Anxiety and depression','theory':'direct'},[{'id':'p1','document_id':did,'document_name':'x.pdf','category':'medical_records','page':1,'text':'Patient denies anxiety and depression.','ocr_confidence':.99}])
    result=EvidenceAutofillService(db).populate(pid,c,.60)
    assert result['created']==0

def test_claim_element_coverage():
    rows=ClaimElementSummary().build(claim(),[{'claim_id':'clm1','claim_element':'diagnosis','polarity':'favorable','review_status':'approved','finding':'MDD diagnosed'}])
    diag=next(x for x in rows if x['claim_element']=='diagnosis')
    assert diag['status']=='supported'
