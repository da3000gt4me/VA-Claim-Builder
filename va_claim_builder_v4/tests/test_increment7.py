from core.drafting.fact_matrix import ApprovedFactMatrix
from core.drafting.fact_validator import DraftFactValidator
from core.drafting.claim_drafting_intelligence import ClaimDraftingIntelligence

CLAIM={"id":"c1","condition_name":"Anxiety and depression","theory":"direct"}

def annotation(i, element, finding, category="medical_records", polarity="favorable"):
    return {"id":i,"claim_id":"c1","claim_element":element,"finding":finding,"quote":finding,"category":category,"document_name":"record.pdf","page":2,"confidence":.95,"polarity":polarity,"review_status":"approved"}

def test_fact_matrix_uses_only_approved_and_separates_authority():
    rows=[annotation("1","diagnosis","Major depressive disorder diagnosed."),{**annotation("2","continuity","Spouse observed symptoms.","buddy_letters"),"review_status":"pending"}]
    matrix=ApprovedFactMatrix().build(CLAIM,rows,[])
    assert matrix["draftable_fact_count"]==1
    assert matrix["facts_by_element"]["diagnosis"][0]["authority"]=="medical"

def test_lay_medical_conclusion_is_flagged():
    matrix=ApprovedFactMatrix().build(CLAIM,[annotation("1","diagnosis","MDD diagnosed.")],[])
    result=DraftFactValidator().validate("I believe anxiety was caused by service.",matrix,"buddy_letter")
    assert any(x["kind"]=="medical_conclusion_in_lay_draft" for x in result["warnings"])

def test_unsupported_year_is_flagged():
    matrix=ApprovedFactMatrix().build(CLAIM,[annotation("1","diagnosis","MDD diagnosed.")],[])
    result=DraftFactValidator().validate("Symptoms began in 2004.",matrix,"personal_statement")
    assert any(x["kind"]=="unsupported_date" for x in result["warnings"])

def test_generated_doctor_package_contains_review_guardrails(tmp_path):
    matrix=ApprovedFactMatrix().build(CLAIM,[annotation("1","diagnosis","MDD diagnosed.")],[])
    pkg=ClaimDraftingIntelligence().build_sections(matrix,"doctor_nexus","My original draft")
    assert pkg["sections"][0]["heading"]=="Original Draft Starting Point"
    paths=ClaimDraftingIntelligence().export(pkg,tmp_path)
    assert all(p.exists() for p in paths)
