from core.analysis.semantic_evidence import SemanticEvidenceAnalyzer

def chunk(text, page=1):
    return {'id':f'pg1_{page}','document_id':'doc1','document_name':'record.pdf','page':page,'text':text,'ocr_confidence':.97}

def claim():
    return {'id':'clm1','condition_name':'Acquired psychiatric disorder with anxiety and depressive features','theory':'direct'}

def test_denial_is_not_favorable_autofill():
    rows=SemanticEvidenceAnalyzer().analyze_chunks(claim(),[chunk('Review of systems: patient denies anxiety and depression.')])
    assert rows
    assert all(r['auto_action']!='suggest_for_autofill' for r in rows)
    assert any(r['polarity']=='unfavorable' for r in rows)

def test_diagnosis_is_high_value_support():
    rows=SemanticEvidenceAnalyzer().analyze_chunks(claim(),[chunk('Assessment: major depressive disorder and anxiety disorder. Continue psychotherapy.')])
    assert any(r['claim_element']=='diagnosis' and r['auto_action']=='suggest_for_autofill' for r in rows)

def test_functional_impact_is_support():
    rows=SemanticEvidenceAnalyzer().analyze_chunks(claim(),[chunk('His anxiety causes difficulty concentrating at work and relationship strain at home.')])
    assert any(r['claim_element']=='functional_impact' and r['polarity']=='favorable' for r in rows)

def test_keyword_only_is_not_autofill():
    rows=SemanticEvidenceAnalyzer().analyze_chunks(claim(),[chunk('Past form contains the words anxiety depression in a templated list.')])
    assert rows
    assert all(r['auto_action']!='suggest_for_autofill' for r in rows)
