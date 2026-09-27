"""Caregiver load, medication flags, and the joined resident picture."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from turnwise.engine.continence import DIURETIC_INDEX, continence_features
from turnwise.engine.risk_rules import ResidentRisk, extra_risk_steps
from turnwise.engine.scheduler import SchedTask, merge_tasks, with_caregiver_load
from turnwise.models import MedicationLog, Resident, Task

UTC = timezone.utc


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TURNWISE_DATABASE_URL", f"sqlite:///{tmp_path}/turnwise.db")
    monkeypatch.setenv("TURNWISE_EDGE_TOKEN", "edge-test-token")
    monkeypatch.setenv("TURNWISE_SECRET", "test-secret")
    from turnwise.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_heavier_queue_passes_a_higher_pressure_ratio():
    light = with_caregiver_load(0.90, 0, 0.08)
    heavy = with_caregiver_load(0.70, 8, 0.08)
    assert heavy > light
    t0 = datetime(2026, 9, 27, 2, tzinfo=UTC)
    alone = merge_tasks(
        [
            SchedTask(id="a", resident_id="pressure", kind="turn", due_at=t0, priority=0.90),
            SchedTask(id="b", resident_id="queue", kind="turn", due_at=t0, priority=0.70),
        ],
        30,
    )
    assert [visit.resident_id for visit in alone] == ["pressure", "queue"]
    loaded = merge_tasks(
        [
            SchedTask(id="a", resident_id="pressure", kind="turn", due_at=t0, priority=light),
            SchedTask(id="b", resident_id="queue", kind="turn", due_at=t0, priority=heavy),
        ],
        30,
    )
    assert [visit.resident_id for visit in loaded] == ["queue", "pressure"]


def test_sedating_factor_adds_one_risk_step():
    plain = ResidentRisk(braden_total=18)
    assert extra_risk_steps(plain) == 0
    sedated = ResidentRisk(braden_total=18, factors={"sedating_medication"})
    assert extra_risk_steps(sedated) == extra_risk_steps(plain) + 1


def test_diuretic_flips_only_that_feature():
    off = continence_features(hours_since=2, hour=3, night=1, meal=0, diuretic=0, category=0)
    on = continence_features(hours_since=2, hour=3, night=1, meal=0, diuretic=1, category=0)
    assert off[DIURETIC_INDEX] == 0
    assert on[DIURETIC_INDEX] == 1
    assert off[:DIURETIC_INDEX] == on[:DIURETIC_INDEX]
    assert off[DIURETIC_INDEX + 1 :] == on[DIURETIC_INDEX + 1 :]


def test_open_tasks_raise_the_same_residents_priority(client):
    token, _ = _login(client, "Maria Santos")
    first = client.get("/me/shift", headers=_auth(token)).json()
    james = next(item for item in first["items"] if item["resident"]["preferred_name"] == "James Okonkwo")
    before = james["priority"]
    waiting = james["queue_open"]
    from turnwise.db import SessionLocal

    db = SessionLocal()
    harold = db.query(Resident).filter(Resident.preferred_name == "Harold Bennett").one()
    for _ in range(4):
        db.add(Task(resident_id=harold.id, kind="turn", status="open", due_at=datetime.now(UTC), source="record"))
    db.commit()
    db.close()
    second = client.get("/me/shift", headers=_auth(token)).json()
    again = next(item for item in second["items"] if item["resident"]["preferred_name"] == "James Okonkwo")
    assert again["queue_open"] == waiting + 4
    assert again["priority"] > before
    assert second["items"][0]["ahead"]["code"] in {"why.ahead.pressure", "why.ahead.load"}


def test_sedating_dose_raises_the_risk_score(client):
    token, _ = _login(client, "Sam Patel")
    harold = _resident(client, token, "Harold Bennett")
    before = client.get(f"/residents/{harold}/full-picture", headers=_auth(token)).json()
    assert before["risk"]["sedating_medication"] is False
    from turnwise.db import SessionLocal

    db = SessionLocal()
    db.add(
        MedicationLog(
            resident_id=harold,
            ts=datetime.now(UTC) - timedelta(hours=1),
            medication_name="lorazepam",
            dose="0.5 mg",
            route="oral",
            is_sedating=True,
            is_diuretic=False,
        )
    )
    db.commit()
    db.close()
    after = client.get(f"/residents/{harold}/full-picture", headers=_auth(token)).json()
    assert after["risk"]["extra_steps"] == before["risk"]["extra_steps"] + 1
    assert after["risk"]["weight"] > before["risk"]["weight"]
    assert after["risk"]["sedating_medication"] is True


def test_diuretic_window_and_full_picture_sources(client):
    token, _ = _login(client, "Sam Patel")
    james = _resident(client, token, "James Okonkwo")
    harold = _resident(client, token, "Harold Bennett")
    elena = _resident(client, token, "Elena Alvarez")
    james_pic = client.get(f"/residents/{james}/full-picture", headers=_auth(token)).json()
    harold_pic = client.get(f"/residents/{harold}/full-picture", headers=_auth(token)).json()
    elena_pic = client.get(f"/residents/{elena}/full-picture", headers=_auth(token)).json()
    assert james_pic["continence_features"]["diuretic"] == 1
    assert james_pic["continence_features"]["values"][DIURETIC_INDEX] == 1
    assert harold_pic["continence_features"]["diuretic"] == 0
    assert elena_pic["medications"]["empty"] is True
    assert elena_pic["medications"]["rows"] == []
    for key in ("risk_factors", "braden", "medications"):
        assert key in elena_pic
        assert "empty" in elena_pic[key]
    for key in ("events", "continence", "skin_captures", "vitals"):
        assert key in elena_pic["timeline"]["sources"]
        assert "empty" in elena_pic["timeline"]["sources"][key]
    assert elena_pic["risk_factors"]["empty"] is False
    assert elena_pic["braden"]["empty"] is False
    assert elena_pic["timeline"]["sources"]["skin_captures"]["withheld"] == "consent"
    assert "model_flag" not in str(elena_pic["timeline"])


def _login(client, role_name):
    roster = client.get("/auth/roster").json()["staff"]
    person = next(row for row in roster if row["display_name"] == role_name)
    pins = {"Maria Santos": "2468", "Sam Patel": "4470"}
    response = client.post("/auth/login", json={"staff_id": person["id"], "pin": pins[role_name]})
    assert response.status_code == 200, response.text
    return response.json()["token"], person["id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _resident(client, token, name):
    board = client.get("/nurse/residents", headers=_auth(token)).json()["residents"]
    return next(row["id"] for row in board if row["preferred_name"] == name)
