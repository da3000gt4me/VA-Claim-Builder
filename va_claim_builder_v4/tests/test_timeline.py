from core.timeline.reconciler import reconcile_events

def test_onset_conflict_detected():
    events = [
      {"id":"1","claim_id":"c","event_type":"onset","event_date_start":"2003","source_type":"veteran_reported","date_precision":"year"},
      {"id":"2","claim_id":"c","event_type":"diagnosis","event_date_start":"2015","source_type":"medical_verified","date_precision":"year"},
    ]
    conflicts = reconcile_events(events)
    assert conflicts and conflicts[0].conflict_type == "onset_date_discrepancy"
