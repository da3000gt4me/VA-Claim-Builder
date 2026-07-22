from core.timeline.auto_populator import HistoricalTimelineAutoPopulator


def test_autopopulates_affirmative_dated_events_and_skips_negation():
    claims=[{"id":"c1","condition_name":"Anxiety and depression"}]
    annotations=[
        {"claim_id":"c1","document_id":"d1","page":2,"category":"medical_records","claim_element":"diagnosis","polarity":"favorable","finding":"Diagnosed with anxiety in 2024.","quote":"The patient was diagnosed with anxiety in March 2024.","confidence":.9},
        {"claim_id":"c1","document_id":"d1","page":3,"category":"medical_records","claim_element":"severity","polarity":"unfavorable","finding":"No anxiety","quote":"Patient denies anxiety and depression.","confidence":.9},
    ]
    out=HistoricalTimelineAutoPopulator().propose(claims,annotations,[])
    assert len(out)==1
    assert out[0]["event_type"]=="diagnosis"
    assert out[0]["event_date_start"]=="2024-03"
    assert out[0]["verification_status"]=="proposed"


def test_personal_timeline_page_creates_editable_reported_event():
    claims=[{"id":"c1","condition_name":"Migraine headaches"}]
    chunks=[{"document_id":"d2","page":1,"category":"personal_timelines","linked_claim_ids":"c1","ocr_confidence":.95,"text":"I first experienced severe headaches while on active duty in 2004. They worsened in 2005 and continued after separation."}]
    out=HistoricalTimelineAutoPopulator().propose(claims,[],chunks)
    assert any(x["event_type"]=="onset" and x["event_date_start"]=="2004" for x in out)
    assert all(x["source_type"]=="veteran_reported" for x in out)
