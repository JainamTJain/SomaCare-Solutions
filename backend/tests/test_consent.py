"""Consent gates camera numbers. The form text is the config file, filled in."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from turnwise.consent import fill_form
from turnwise.models import ConsentRecord, Event, Resident


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TURNWISE_DATABASE_URL", f"sqlite:///{tmp_path}/turnwise.db")
    monkeypatch.setenv("TURNWISE_EDGE_TOKEN", "edge-test-token")
    monkeypatch.setenv("TURNWISE_SECRET", "test-secret")
    from turnwise.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _login(client, role_name):
    roster = client.get("/auth/roster").json()["staff"]
    person = next(row for row in roster if row["display_name"] == role_name)
    pins = {
        "Maria Santos": "2468",
        "Sam Patel": "4470",
        "Riley Chen": "9130",
        "Helen Cho": "6204",
        "Devon Brooks": "8024",
    }
    response = client.post("/auth/login", json={"staff_id": person["id"], "pin": pins[role_name]})
    assert response.status_code == 200, response.text
    return response.json()["token"], person["id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_form_text_is_the_template(client):
    del client
    text = fill_form("position_monitoring", "Elena Alvarez")
    assert "Elena Alvarez" in text
    assert "Harbor House" in text
    assert "no video or photo is ever saved" in text
    assert "{" not in text


def test_request_print_and_sign_round_trip(client):
    nurse, _ = _login(client, "Sam Patel")
    board = client.get("/consent", headers=_auth(nurse)).json()
    elena = next(row for row in board["residents"] if row["name"] == "Elena Alvarez")
    assert elena["scopes"]["position_monitoring"]["status"] == "signed"
    assert elena["scopes"]["position_monitoring"]["signature_ref"] == "demo-seed"
    assert elena["scopes"]["skin_capture"]["status"] == "none"
    assert elena["scopes"]["position_monitoring"]["explanation_shown"] == fill_form(
        "position_monitoring", "Elena Alvarez"
    )
    created = client.post(
        "/consent/request",
        headers=_auth(nurse),
        json={"resident_id": elena["resident_id"], "scope": "skin_capture"},
    )
    assert created.status_code == 200, created.text
    record_id = created.json()["id"]
    assert created.json()["explanation_shown"] == fill_form("skin_capture", "Elena Alvarez")
    sent = client.post(f"/consent/{record_id}/send", headers=_auth(nurse))
    assert sent.status_code == 200, sent.text
    assert sent.json()["sent_to"] == "in_person"
    form = client.get(f"/consent/{record_id}/form", headers=_auth(nurse))
    assert form.status_code == 200
    assert form.headers["content-type"].startswith("application/pdf")
    assert form.content.startswith(b"%PDF")
    signed = client.post(
        f"/consent/{record_id}/sign",
        headers=_auth(nurse),
        json={"signer_name": "Ana Alvarez", "relationship": "daughter"},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "signed"
    assert signed.json()["signature_ref"] == "Ana Alvarez"


def test_without_position_consent_camera_numbers_are_withheld(client):
    from turnwise.db import SessionLocal

    nurse, _ = _login(client, "Sam Patel")
    maria, _ = _login(client, "Maria Santos")
    board = client.get("/consent", headers=_auth(nurse)).json()
    james = next(row for row in board["residents"] if row["name"] == "James Okonkwo")
    record_id = james["scopes"]["position_monitoring"]["id"]
    revoked = client.post(
        f"/consent/{record_id}/revoke",
        headers=_auth(nurse),
        json={"reason": "Power of attorney declined the camera."},
    )
    assert revoked.status_code == 200, revoked.text
    card = client.get(f"/residents/{james['resident_id']}/card", headers=_auth(maria)).json()
    assert card["monitoring"]["mode"] == "schedule"
    assert card["monitoring"]["label"] == "monitored by schedule, not camera"
    assert card["position"] is None
    assert card["confidence"] is None
    assert card["camera_spectrum"] is None
    assert card["model_version"] is None
    engineer, _ = _login(client, "Riley Chen")
    raw = client.get("/engineer/board", headers=_auth(engineer)).json()
    row = next(item for item in raw["residents"] if item["name"] == "James Okonkwo")
    assert row["monitoring"]["mode"] == "schedule"
    assert row["position"] is None
    assert row["areas"] is None
    assert row["confidence_pct"] is None
    assert row["visual_check"]["withheld"] == "consent"
    camera = next(item for item in raw["cameras"] if item["resident"] == "James Okonkwo")
    assert camera["uncertainty_pct"] is None
    assert camera["monitoring"] == "schedule"
    director, _ = _login(client, "Helen Cho")
    summary = client.get("/director/board", headers=_auth(director)).json()
    assert summary["pressure_injury"]["ulcers_prevented"] is None
    db = SessionLocal()
    stored = db.get(ConsentRecord, record_id)
    assert stored.status == "revoked"
    db.close()


def test_duplicate_device_event_does_not_apply_twice(client):
    _login(client, "Maria Santos")
    edge = {"Authorization": "Bearer edge-test-token"}
    from turnwise.db import SessionLocal

    db = SessionLocal()
    resident = db.query(Resident).filter(Resident.preferred_name == "Harold Bennett").one()
    room_id = resident.room_id
    resident_id = resident.id
    db.close()
    moment = datetime.now(timezone.utc).isoformat()
    body = {
        "room_id": room_id,
        "resident_id": resident_id,
        "ts": moment,
        "kind": "heartbeat",
        "source": "camera",
        "device_id": "baby-monitor-20",
        "value": {"camera_spectrum": "infrared"},
        "model_version": "position-v0.0.0-rules",
    }
    first = client.post("/events", headers=edge, json=body)
    second = client.post("/events", headers=edge, json=body)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == first.json()["event_id"]
    db = SessionLocal()
    count = (
        db.query(Event)
        .filter(Event.device_id == "baby-monitor-20", Event.kind == "heartbeat", Event.resident_id == resident_id)
        .count()
    )
    assert count == 1
    db.close()


def test_pin_locks_after_five_misses(client):
    roster = client.get("/auth/roster").json()["staff"]
    devon = next(row for row in roster if row["display_name"] == "Devon Brooks")
    for _ in range(4):
        missed = client.post("/auth/login", json={"staff_id": devon["id"], "pin": "0000"})
        assert missed.status_code == 401
    locked = client.post("/auth/login", json={"staff_id": devon["id"], "pin": "0000"})
    assert locked.status_code == 429
    real = client.post("/auth/login", json={"staff_id": devon["id"], "pin": "8024"})
    assert real.status_code == 429
    _login(client, "Maria Santos")


def test_skin_capture_hides_the_flag_until_consent(client):
    nurse, _ = _login(client, "Sam Patel")
    board = client.get("/consent", headers=_auth(nurse)).json()
    elena = next(row for row in board["residents"] if row["name"] == "Elena Alvarez")
    edge = {"Authorization": "Bearer edge-test-token"}
    files = {"image": ("crop.jpg", b"not-a-picture", "image/jpeg")}
    data = {"resident_id": elena["resident_id"], "area": "sacrum", "source": "room"}
    denied = client.post("/skin/captures", headers=edge, data=data, files=files)
    assert denied.status_code == 403
    created = client.post(
        "/consent/request",
        headers=_auth(nurse),
        json={"resident_id": elena["resident_id"], "scope": "skin_capture"},
    )
    record_id = created.json()["id"]
    client.post(f"/consent/{record_id}/send", headers=_auth(nurse))
    client.post(
        f"/consent/{record_id}/sign",
        headers=_auth(nurse),
        json={"signer_name": "Ana Alvarez", "relationship": "daughter"},
    )
    accepted = client.post("/skin/captures", headers=edge, data=data, files=files)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["shown_to_staff"] is False
    assert "model_flag" not in body


def test_setup_counts_are_live(client):
    nurse, _ = _login(client, "Sam Patel")
    status = client.get("/setup/status", headers=_auth(nurse)).json()
    rooms = next(step for step in status["steps"] if step["id"] == "rooms")
    consent = next(step for step in status["steps"] if step["id"] == "consent")
    assert rooms["have"] == 10
    assert rooms["cameras_online"] == 9
    assert consent["signed"] == 20
    assert consent["needed"] == 30
    assert consent["done"] is False
    assert status["complete"] is False
