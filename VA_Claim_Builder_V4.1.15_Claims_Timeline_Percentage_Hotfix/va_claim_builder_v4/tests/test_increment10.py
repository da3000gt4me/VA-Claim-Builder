from pathlib import Path
from core.analysis.literature_support import LiteratureSupportEngine
from core.drafting.specialist_packet import SpecialistPacketGenerator
from core.drafting.binder_assembler import SubmissionBinderAssembler


def test_literature_requires_identifier_and_does_not_assert_causation():
    result=LiteratureSupportEngine().assess_candidate({'title':'Migraine systematic review','year':'2024','source':'Journal'}, {'condition_name':'Migraine headaches'})
    assert result['citation_complete'] is False
    assert result['patient_specific_causation'] is False


def test_literature_detects_relevance_and_quality():
    c={'title':'Migraine systematic review','year':'2024','source':'Journal','doi':'10.1/x','abstract':'A systematic review of migraine headaches'}
    result=LiteratureSupportEngine().assess_candidate(c, {'condition_name':'Migraine headaches'})
    assert result['claim_relevance']=='potentially_relevant'
    assert result['quality_tier']=='higher'


def test_specialty_mapping():
    gen=SpecialistPacketGenerator()
    assert 'Neurology' in gen.recommend_specialty('Migraine headaches')
    assert 'Urology' in gen.recommend_specialty('Voiding dysfunction')


def test_specialist_packet_exports(tmp_path):
    packet=SpecialistPacketGenerator().build({'condition_name':'Migraine headaches','theory':'direct'}, {'facts_by_element':{'diagnosis':[{'proposition':'Diagnosed migraine','source':'record.pdf p.2'}]}})
    paths=SpecialistPacketGenerator().export(packet,tmp_path)
    assert all(p.exists() for p in paths)


def test_binder_blocks_missing_source(tmp_path):
    result=SubmissionBinderAssembler().assemble('Test',[{'condition_name':'Migraine'}],[{'include_in_final':True,'original_path':str(tmp_path/'missing.pdf'),'original_name':'missing.pdf'}],[],tmp_path)
    assert result['status']=='blocked'


def test_binder_creates_manifest_and_zip(tmp_path):
    src=tmp_path/'record.txt'; src.write_text('evidence')
    out=tmp_path/'summary.txt'; out.write_text('summary')
    docs=[{'include_in_final':True,'original_path':str(src),'original_name':'record.txt','category':'medical_records'}]
    result=SubmissionBinderAssembler().assemble('Test',[{'condition_name':'Migraine','theory':'direct'}],docs,[out],tmp_path/'output')
    assert result['status']=='assembled_for_human_review'
    assert Path(result['binder_zip']).exists()
    assert result['binder_sha256']
