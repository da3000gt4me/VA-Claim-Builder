from core.analysis.dbq_parser import DBQCPParser
from core.analysis.evidence_gap_planner import EvidenceGapActionPlanner
from core.analysis.package_assembly import FinalPackageAssemblyValidator
from core.rating.criteria_engine import RatingCriteriaEngine


def test_dbq_parser_extracts_opinion_and_rationale():
    text='''Diagnosis: Migraine headaches\nMedical History: onset in service\nSymptoms: prostrating attacks\nFunctional Impact: missed work\nMedical Opinion: at least as likely as not\nRationale: symptoms began after documented exposure.'''
    result=DBQCPParser().parse(text,'exam.txt')
    assert result['opinion_polarity']=='favorable'
    assert 'rationale' in result['sections']
    assert result['missing_core_sections']==[]


def test_dbq_parser_flags_opinion_without_rationale():
    result=DBQCPParser().parse('Diagnosis: tinnitus\nMedical Opinion: less likely than not\nFunctional Impact: difficulty concentrating')
    assert result['opinion_polarity']=='unfavorable'
    assert result['review_flags']


def test_gap_planner_prioritizes_required_elements():
    claim={'id':'c1','condition_name':'Migraine'}
    plan=EvidenceGapActionPlanner().build(claim,{'missing_elements':['nexus','diagnosis']},{'profile':None})
    assert plan['actions'][0]['priority']=='required'
    assert set(plan['ready_when'])=={'diagnosis','nexus'}


def test_gap_planner_adds_rating_missing_concepts():
    claim={'id':'c1','condition_name':'Migraine'}
    rating={'profile':'migraine','levels':[{'percentage':30,'status':'partially_supported','missing_concepts':['prostrating']} ]}
    plan=EvidenceGapActionPlanner().build(claim,{'missing_elements':[]},rating)
    assert any('prostrating' in x['action'] for x in plan['actions'])


def test_assembly_validator_blocks_no_documents():
    result=FinalPackageAssemblyValidator().validate([{'id':'c1'}],[],[{'blocked':False}])
    assert result['blocked'] is True


def test_assembly_validator_warns_duplicates(tmp_path):
    f=tmp_path/'a.pdf'; f.write_bytes(b'x')
    docs=[{'include_in_final':True,'signed_status':'signed','duplicate_of':'d0','classification_reviewed':1,'original_path':str(f)}]
    result=FinalPackageAssemblyValidator().validate([{'id':'c1'}],docs,[{'blocked':False}])
    assert result['blocked'] is False
    assert result['warnings']


def test_expanded_rating_profiles_map_common_claims():
    engine=RatingCriteriaEngine()
    for condition in ['Obstructive sleep apnea','Irritable bowel syndrome','Chronic allergic rhinitis','Chronic sinusitis','Voiding dysfunction','Cervical spine strain','TMJ','Erectile dysfunction']:
        assert engine.identify_profile(condition) is not None
