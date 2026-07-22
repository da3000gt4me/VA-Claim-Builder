from pathlib import Path
import pytest
from core.legal.caselaw_engine import CaseLawEngine, LegalAuthority
from core.providers.provider_template import ProviderTemplateGenerator

def test_bva_requires_nonprecedential_warning():
    a = LegalAuthority('BVA decision','A000000','bva_decision','https://va.gov/x','similar facts',verified=True)
    assert 'bva_nonprecedential_warning_required' in CaseLawEngine().validate(a)

def test_binding_authority_ranks_first():
    e=CaseLawEngine(); b=LegalAuthority('BVA','x','bva_decision','https://va.gov/x','p',verified=True,negative_treatment='Nonprecedential')
    r=LegalAuthority('Reg','38 CFR','regulation','https://ecfr.gov/x','p',verified=True)
    assert e.rank([b,r])[0].authority_type=='regulation'

def test_provider_branding_requires_supplied_logo(tmp_path):
    with pytest.raises(ValueError):
        ProviderTemplateGenerator().build_docx({},'Migraine',[],tmp_path/'x.docx','provider_supplied_branding')

def test_neutral_provider_template_builds(tmp_path):
    p=ProviderTemplateGenerator().build_docx({'practice_name':'Example Clinic'},'Migraine',[('Records Reviewed','Record A')],tmp_path/'x.docx')
    assert p.exists()
