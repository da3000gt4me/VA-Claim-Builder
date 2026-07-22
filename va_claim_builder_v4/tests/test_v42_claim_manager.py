from pathlib import Path

import pytest

from core.claims import ClaimManager
from core.projects import ProjectManager


def _project(tmp_path: Path):
    manager = ProjectManager(home=tmp_path / "home")
    return manager.create_project("Claims Test")


def test_claim_crud_persists(tmp_path: Path) -> None:
    project = _project(tmp_path)
    manager = ClaimManager(project)
    created = manager.create(
        "Tinnitus",
        claim_type="direct",
        service_event="Hazardous noise exposure",
        symptoms="Constant ringing",
    )
    assert created.condition_name == "Tinnitus"
    assert ClaimManager(project).get(created.claim_id).service_event == "Hazardous noise exposure"

    updated = manager.update(created.claim_id, status="ready", notes="Audiology evidence available")
    assert updated.status == "ready"
    assert updated.notes == "Audiology evidence available"

    manager.delete(created.claim_id)
    assert manager.list_claims() == []
    with pytest.raises(KeyError):
        manager.get(created.claim_id)


def test_claim_order_can_be_changed(tmp_path: Path) -> None:
    manager = ClaimManager(_project(tmp_path))
    first = manager.create("First")
    second = manager.create("Second")
    manager.move(second.claim_id, -1)
    assert [claim.claim_id for claim in manager.list_claims()] == [second.claim_id, first.claim_id]


def test_claim_validation(tmp_path: Path) -> None:
    manager = ClaimManager(_project(tmp_path))
    with pytest.raises(ValueError):
        manager.create("")
    with pytest.raises(ValueError):
        manager.create("Condition", claim_type="invalid")
