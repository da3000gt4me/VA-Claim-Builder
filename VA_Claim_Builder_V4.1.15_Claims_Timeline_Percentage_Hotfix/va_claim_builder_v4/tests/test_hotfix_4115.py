from core.claims.form995_parser import Form995ClaimParser
from core.timeline.auto_populator import HistoricalTimelineAutoPopulator


def page(doc, text):
    return {"document_id": doc, "document_name": f"{doc}.pdf", "page": 5, "text": text, "category": "01_form_20_0995_submissions"}


def test_two_forms_are_isolated_and_capped_at_nine_each():
    rows1 = "\n".join(f"{i}. Condition A{i}" for i in range(1,10))
    rows2 = "\n".join(f"{i}. Condition B{i}" for i in range(1,10))
    noise = "\n".join(f"{i}. This should never be claim {i}" for i in range(1,10))
    pages = [page("one", f"21A SPECIFIC ISSUES\n{rows1}\n21B DATE OF VA DECISION\n{noise}"), page("two", f"21A SPECIFIC ISSUES\n{rows2}\n21B DATE OF VA DECISION\n{noise}")]
    parsed = Form995ClaimParser().parse_pages(pages)
    assert len(parsed) == 18
    assert parsed[0].condition_name == "Condition A1"
    assert parsed[-1].condition_name == "Condition B9"


def test_timeline_uses_real_category_values_and_keeps_undated_medical_event():
    claims=[{"id":"c1","condition_name":"Migraine headaches"}]
    chunks=[{"document_id":"d1","page":2,"category":"03_medical_records","text":"Patient diagnosed with migraine headaches and prescribed medication.","linked_claim_ids":"c1","ocr_confidence":.9}]
    items=HistoricalTimelineAutoPopulator().propose(claims,[],chunks)
    assert items
    assert items[0]["source_type"] == "medical_verified"
    assert items[0]["date_precision"] == "unknown"
