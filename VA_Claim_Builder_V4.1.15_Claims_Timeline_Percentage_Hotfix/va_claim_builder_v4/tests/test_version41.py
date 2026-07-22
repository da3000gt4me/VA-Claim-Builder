from pathlib import Path
from core.analysis.adversarial_review import AdversarialReviewEngine
from core.analysis.theory_comparison import ClaimTheoryComparisonEngine
from core.analysis.factual_audit import FinalFactualAudit
from core.workflow.final_closeout import FinalCloseoutChecklist

def claim(theory='direct'):
    return {'id':'c1','condition_name':'Migraine','theory':theory}

def ann(element,polarity='favorable',authority='medical_record'):
    return {'claim_id':'c1','review_status':'approved','polarity':polarity,'claim_element':element,'finding':element,'source_authority':authority,'document_name':'r.pdf','page':1}

def test_adversarial_flags_missing_nexus():
    result=AdversarialReviewEngine().review(claim(),[ann('current_diagnosis'),ann('in_service_event')],[],[])
    assert any(x['category']=='missing_element' and 'nexus' in x['issue'] for x in result['findings'])

def test_adversarial_retains_unfavorable():
    result=AdversarialReviewEngine().review(claim(),[ann('current_diagnosis'),ann('in_service_event'),ann('nexus'),ann('severity','unfavorable')],[],[])
    assert any(x['category']=='unfavorable_evidence' for x in result['findings'])

def test_theory_comparison_prefers_direct():
    rows=[ann('current_diagnosis'),ann('in_service_event'),ann('nexus')]
    result=ClaimTheoryComparisonEngine().compare(claim(),rows)
    assert result['recommended_primary_theory']=='direct'

def test_factual_file_audit(tmp_path: Path):
    p=tmp_path/'x.txt'; p.write_text('ok')
    result=FinalFactualAudit().audit_files([str(p),str(tmp_path/'missing')])
    assert result['all_present'] is False

def test_closeout_blocks_unready():
    result=FinalCloseoutChecklist().assess({'overall':'not_ready'},{'status':'pass'},[claim()],[{'status':'blocked','claim_id':'c1'}],{'all_present':True})
    assert result['ready_to_close'] is False
