from core.storage.project_db import ProjectDB

def test_project_claim_timeline_and_approval(tmp_path):
    db = ProjectDB(tmp_path / "test.db")
    project = db.create_project("Test")
    claim = db.add_claim(project, "Migraines", "aggravation")
    event = db.add_timeline_event(project, {"claim_id": claim, "event_date_start": "2003", "date_precision": "year",
        "event_type": "onset", "description": "Symptoms worsened during service", "source_type": "veteran_reported"})
    assert db.list_timeline(project)[0]["id"] == event
