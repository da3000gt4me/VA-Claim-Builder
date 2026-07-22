from core.claims.form995_parser import Form995ClaimParser
from core.storage.project_db import ProjectDB


def test_page5_section21a_extracts_nine_and_stops_before_dates():
    text = '''VA FORM 20-0995 Page 5
21A. SPECIFIC ISSUE(S) FOR REVIEW
1. Migraine headaches
2. Chronic allergic rhinitis
3. Chronic sinusitis
4. Tinnitus
5. Bilateral hearing loss
6. Cervical spine strain with degenerative changes
7. Temporomandibular joint disorder (TMJ)
8. Irritable bowel syndrome (IBS)
9. Obstructive sleep apnea
21B. DATE OF VA DECISION
01/05/2025
'''
    rows = Form995ClaimParser().parse_pages([{"page": 5, "text": text}])
    assert len(rows) == 9
    assert rows[0].condition_name == "Migraine headaches"
    assert rows[-1].condition_name == "Obstructive sleep apnea"
    assert all("2025" not in row.condition_name for row in rows)


def test_ignores_generic_issue_words_outside_page5_section21a():
    pages = [
        {"page": 1, "text": "Specific issue: Privacy Act and filing instructions"},
        {"page": 5, "text": "21A. SPECIFIC ISSUE(S)\n1. Tinnitus\n21B. DATE OF VA DECISION\n01/01/2024"},
    ]
    rows = Form995ClaimParser().parse_pages(pages)
    assert [r.condition_name for r in rows] == ["Tinnitus"]


def test_claims_can_be_edited_and_deleted(tmp_path):
    db = ProjectDB(tmp_path / "project.db")
    project_id = db.ensure_default_project()
    claim_id = db.add_claim(project_id, "Old Name", "unknown")
    db.update_claim(claim_id, condition_name="Migraine headaches", theory="direct", status="active")
    claim = next(c for c in db.list_claims(project_id) if c["id"] == claim_id)
    assert claim["condition_name"] == "Migraine headaches"
    assert claim["theory"] == "direct"
    db.delete_claim(claim_id)
    assert not db.list_claims(project_id)
