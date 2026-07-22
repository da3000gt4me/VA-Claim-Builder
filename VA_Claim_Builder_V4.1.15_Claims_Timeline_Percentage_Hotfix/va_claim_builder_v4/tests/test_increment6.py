from core.analysis.corroboration import CrossDocumentCorroborator
from core.analysis.timeline_consistency import TimelineConsistencyEngine
from core.analysis.claim_synthesis import ClaimSynthesisEngine

def ann(i,doc,cat,finding,element='diagnosis',pol='favorable'):
    return {'id':i,'claim_id':'c1','document_id':doc,'document_name':doc,'category':cat,'finding':finding,'quote':finding,'claim_element':element,'polarity':pol,'confidence':.9,'review_status':'approved'}

def test_repeated_same_chart_does_not_inflate_independence():
    rows=[ann('1','d1','medical_records','Diagnosed major depressive disorder.'),ann('2','d1','medical_records','Diagnosed major depressive disorder.'),ann('3','d1','medical_records','Diagnosed major depressive disorder.')]
    c=CrossDocumentCorroborator().build(rows)[0]
    assert c['independent_documents']==1 and c['repeated_same_source']==2
    assert c['strength']=='single-source support'

def test_independent_medical_and_lay_sources_corroborate():
    rows=[ann('1','d1','medical_records','Chronic migraines documented.', 'continuity'),ann('2','d2','buddy_letters','Witness observed recurring migraines.', 'continuity')]
    c=CrossDocumentCorroborator().build(rows)[0]
    assert c['independent_documents']==2 and c['independent_source_types']==2
    assert c['strength'] in {'corroborated','strongly corroborated'}

def test_timeline_distinguishes_onset_from_diagnosis():
    events=[{'claim_id':'c1','event_type':'onset','event_date_start':'2004','source_type':'veteran_reported','confidence':.8},{'claim_id':'c1','event_type':'diagnosis','event_date_start':'2015','source_type':'medical_verified','confidence':1.0},{'claim_id':'c1','event_type':'continuity','event_date_start':'2006','source_type':'witness_reported','confidence':.8}]
    result=TimelineConsistencyEngine().assess('c1',events)
    assert any('distinguishes first symptoms' in x for x in result['bridges'])
    assert result['earliest_supported_onset']=='2004'

def test_synthesis_uses_only_approved_evidence_and_identifies_gap():
    rows=[ann('1','d1','medical_records','Current migraine diagnosis established.'),{**ann('2','d2','military_records','In-service headache documented.','in_service_event'), 'review_status':'pending'}]
    claim={'id':'c1','condition_name':'Migraines','theory':'direct'}
    result=ClaimSynthesisEngine().build(claim,rows,[],[])
    assert len(result['clear_ties'])==1
    assert 'in_service_event' in result['missing_elements'] and 'nexus' in result['missing_elements']
