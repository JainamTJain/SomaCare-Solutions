"""SomaCare contract: config, cookies, the care clock, leads, tours, schedules."""

from datetime import datetime, timedelta, timezone

pytest_plugins = ["test_api"]

from turnwise.consent import fill_form, form_version
from turnwise.models import Alert, ConsentRecord, Device, Resident, Task


def _session():
    from turnwise.db import SessionLocal

    return SessionLocal()

from test_api import _auth, _login

UTC = timezone.utc


def test_runtime_config_and_api_prefix(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("SOMACARE_DEMO_MODE", raising=False)
    monkeypatch.setenv("FACILITY_NAME", "Harbor House")
    monkeypatch.setenv("LOGO_URL", "https://example.com/logo.png")
    body = client.get("/api/config").json()
    assert body == {
        "demoMode": False,
        "facilityName": "Harbor House",
        "logoUrl": "https://example.com/logo.png",
    }
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert "last_tick_at" in health
    assert "last_tick_duration_ms" in health


def test_roster_hides_pins_unless_demo_mode(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    hidden = client.get("/auth/roster").json()["staff"]
    assert all("pin" not in row for row in hidden)
    monkeypatch.setenv("DEMO_MODE", "true")
    shown = client.get("/api/auth/roster").json()["staff"]
    maria = next(row for row in shown if row["display_name"] == "Maria Santos")
    assert maria["pin"] == "2468"


def test_login_sets_an_httponly_cookie(client):
    roster = client.get("/auth/roster").json()["staff"]
    maria = next(row for row in roster if row["display_name"] == "Maria Santos")
    response = client.post("/auth/login", json={"staff_id": maria["id"], "pin": "2468"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "somacare_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=43200" in cookie
    shift = client.get("/me/shift")
    assert shift.status_code == 200
    assert shift.json()["staff"]["display_name"] == "Maria Santos"


def test_care_clock_creates_resends_and_escalates(client):
    from turnwise.clock import tick

    db = _session()
    elena = db.query(Resident).filter(Resident.preferred_name == "Elena Alvarez").one()
    open_rows = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == elena.id, Alert.status.in_(("sent", "accepted", "passed", "escalated")))
        .all()
    )
    for row in open_rows:
        row.status = "resolved"
    db.commit()
    db.close()

    moment = datetime.now(UTC)
    tick(moment)
    db = _session()
    created = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == elena.id, Alert.status == "sent")
        .one()
    )
    created_id = created.id
    assert created.charge_notified is False
    db.close()

    tick(moment)
    db = _session()
    again = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == elena.id, Alert.status.in_(("sent", "accepted", "passed", "escalated")))
        .all()
    )
    assert [row.id for row in again] == [created_id]
    db.close()

    tick(moment + timedelta(minutes=5))
    db = _session()
    resent = db.get(Alert, created_id)
    assert resent.charge_notified is True
    assert resent.status == "sent"
    db.close()

    tick(moment + timedelta(minutes=20))
    db = _session()
    escalated = db.get(Alert, created_id)
    assert escalated.status == "escalated"
    db.close()
    health = client.get("/api/health").json()
    assert health["last_tick_at"]
    assert health["last_tick_duration_ms"] >= 0


def test_stream_pushes_a_unit_snapshot(client):
    token, _ = _login(client, "Maria Santos")
    with client.stream("GET", "/api/stream?once=true", headers=_auth(token)) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        chunk = next(response.iter_text())
    assert "event: update" in chunk
    assert "Elena Alvarez" in chunk


def test_leads_are_public_to_write_and_director_to_read(client):
    denied = client.get("/leads")
    assert denied.status_code == 401
    token, _ = _login(client, "Maria Santos")
    assert client.get("/leads", headers=_auth(token)).status_code == 403
    created = client.post(
        "/api/leads",
        json={
            "name": "Ada Home",
            "email": "ada@example.com",
            "organization": "Ada Board and Care",
            "kind": "pilot",
            "message": "We have ten residents.",
        },
    )
    assert created.status_code == 200
    director, _ = _login(client, "Helen Cho")
    rows = client.get("/leads", headers=_auth(director)).json()["leads"]
    assert rows[0]["email"] == "ada@example.com"
    assert rows[0]["kind"] == "pilot"


def test_tours_are_stored_per_person(client):
    maria, _ = _login(client, "Maria Santos")
    assert client.get("/me/tours", headers=_auth(maria)).json()["tours"] == []
    saved = client.post("/me/tours", headers=_auth(maria), json={"tour": "cna"})
    assert saved.status_code == 200
    again = client.post("/api/me/tours", headers=_auth(maria), json={"tour": "cna"})
    assert again.status_code == 200
    assert again.json()["tour"] == "cna"
    helen, _ = _login(client, "Helen Cho")
    assert client.get("/me/tours", headers=_auth(helen)).json()["tours"] == []
    assert len(client.get("/me/tours", headers=_auth(maria)).json()["tours"]) == 1


def test_schedule_versions_fixed_checks_and_blackouts(client):
    nurse, _ = _login(client, "Sam Patel")
    maria, _ = _login(client, "Maria Santos")
    residents = client.get("/nurse/residents", headers=_auth(nurse)).json()["residents"]
    carmen = next(row for row in residents if row["preferred_name"] == "Carmen Ruiz")
    first = client.post(
        "/nurse/schedules",
        headers=_auth(nurse),
        json={
            "resident_id": carmen["id"],
            "reason": "Quiet hour after lunch",
            "windows": [{"kind": "blackout", "label": "rest", "start": "00:00", "end": "23:59"}],
        },
    )
    assert first.status_code == 200
    approved = client.post(
        f"/nurse/schedules/{first.json()['id']}/approve",
        headers=_auth(nurse),
        json={"reason": "Quiet hour after lunch"},
    )
    assert approved.json()["status"] == "approved"
    shift = client.get("/me/shift", headers=_auth(maria)).json()
    carmen_item = next((item for item in shift["items"] if item["resident"]["preferred_name"] == "Carmen Ruiz"), None)
    if carmen_item is not None:
        assert "check" not in carmen_item["tasks"]

    db = _session()
    check = (
        db.query(Task)
        .filter(Task.resident_id == carmen["id"], Task.kind == "check", Task.status == "open")
        .one()
    )
    db.add(
        Alert(
            task_id=check.id,
            staff_id=maria and _staff_id(client, "Maria Santos"),
            rule="test",
            status="escalated",
            inputs={},
            plan_version=1,
            model_version="position-v0.0.0-rules",
        )
    )
    db.commit()
    db.close()
    shift = client.get("/me/shift", headers=_auth(maria)).json()
    carmen_item = next(item for item in shift["items"] if item["resident"]["preferred_name"] == "Carmen Ruiz")
    assert "check" in carmen_item["tasks"]

    second = client.post(
        "/nurse/schedules",
        headers=_auth(nurse),
        json={
            "resident_id": carmen["id"],
            "reason": "Add an evening round",
            "windows": [
                {"kind": "blackout", "label": "rest", "start": "00:00", "end": "00:01"},
                {"kind": "fixed", "label": "evening round", "start": "00:00", "end": "23:59"},
            ],
        },
    )
    client.post(
        f"/nurse/schedules/{second.json()['id']}/approve",
        headers=_auth(nurse),
        json={"reason": "Add an evening round"},
    )
    versions = client.get(f"/nurse/schedules/{carmen['id']}", headers=_auth(nurse)).json()["versions"]
    assert versions[1]["windows"] == [{"kind": "blackout", "label": "rest", "start": "00:00", "end": "23:59"}]
    shift = client.get("/me/shift", headers=_auth(maria)).json()
    carmen_items = [item for item in shift["items"] if item["resident"]["preferred_name"] == "Carmen Ruiz"]
    assert any("fixed" in item["tasks"] for item in carmen_items)


def _staff_id(client, name: str) -> str:
    roster = client.get("/auth/roster").json()["staff"]
    return next(row["id"] for row in roster if row["display_name"] == name)


def test_timeline_includes_a_logged_meal_and_empty_sources(client):
    nurse, _ = _login(client, "Sam Patel")
    residents = client.get("/nurse/residents", headers=_auth(nurse)).json()["residents"]
    mei = next(row for row in residents if row["preferred_name"] == "Mei Lin")
    before = client.get(f"/residents/{mei['id']}/timeline", headers=_auth(nurse)).json()["timeline"]
    assert before["sources"]["meals"]["empty"] is True
    logged = client.post(
        f"/residents/{mei['id']}/meals",
        headers=_auth(nurse),
        json={"meal_type": "dinner", "items_text": "soup", "percent_eaten": 50},
    )
    assert logged.status_code == 200
    after = client.get(f"/api/residents/{mei['id']}/timeline", headers=_auth(nurse)).json()["timeline"]
    assert any(item["kind"] == "meal" for item in after["items"])


def test_existing_camera_without_consent_is_flagged(client):
    nurse, _ = _login(client, "Grace Adeyemi")
    residents = client.get("/nurse/residents", headers=_auth(nurse)).json()["residents"]
    elena = next(row for row in residents if row["preferred_name"] == "Elena Alvarez")
    db = _session()
    device = db.query(Device).filter(Device.resident_id == elena["id"]).one()
    device.config = {**(device.config or {}), "origin": "existing"}
    signed = (
        db.query(ConsentRecord)
        .filter(
            ConsentRecord.resident_id == elena["id"],
            ConsentRecord.scope == "position_monitoring",
            ConsentRecord.status == "signed",
        )
        .all()
    )
    for row in signed:
        row.status = "revoked"
        row.revoked_at = datetime.now(UTC)
        row.revoked_reason = "test"
    db.commit()
    db.close()
    token, _ = _login(client, "Riley Chen")
    cameras = client.get("/engineer/board", headers=_auth(token)).json()["cameras"]
    row = next(item for item in cameras if item["resident"] == "Elena Alvarez")
    assert row["origin"] == "existing"
    assert row["consent_state"] == "missing"
    assert row["consent_warning"] is True


def test_new_consent_is_version_2_and_old_text_stays(client):
    assert form_version() == 2
    assert "SomaCare" in fill_form("position_monitoring", "Elena Alvarez")
    nurse, nurse_id = _login(client, "Sam Patel")
    db = _session()
    resident = db.query(Resident).filter(Resident.preferred_name == "Mei Lin").one()
    old = ConsentRecord(
        resident_id=resident.id,
        scope="skin_capture",
        status="signed",
        explanation_shown="Sorety uses the version 1 wording for Mei Lin.",
        form_version=1,
        signed_at=datetime.now(UTC),
    )
    db.add(old)
    db.commit()
    old_id = old.id
    db.close()
    created = client.post(
        "/consent/request",
        headers=_auth(nurse),
        json={"resident_id": resident.id, "scope": "position_monitoring"},
    )
    assert created.status_code == 200
    assert created.json()["form_version"] == 2
    assert "SomaCare" in created.json()["explanation_shown"]
    db = _session()
    kept = db.get(ConsentRecord, old_id)
    assert kept.form_version == 1
    assert kept.explanation_shown.startswith("Sorety")
    db.close()
    assert nurse_id


def test_database_url_accepts_postgres_when_no_explicit_url(monkeypatch):
    monkeypatch.delenv("SOMACARE_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURNWISE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/somacare")
    from sqlalchemy.engine.url import make_url

    from turnwise.db import database_url

    url = database_url()
    assert url.startswith("postgresql")
    assert make_url(url).get_backend_name() == "postgresql"


def test_calendar_file_is_named_somacare(client):
    token, _ = _login(client, "Maria Santos")
    ics = client.get("/me/shift.ics", headers=_auth(token))
    assert 'filename="somacare-shift.ics"' in ics.headers["content-disposition"]
    assert "SomaCare" in ics.text
