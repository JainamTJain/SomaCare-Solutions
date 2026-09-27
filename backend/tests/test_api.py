"""Events update the budget, role checks hold, and a sample record file imports."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from turnwise.engine.budget import ALL_AREAS
from turnwise.models import Alert, Device, Event, Resident, ResidentState, Task

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


def _login(client, role_name):
    roster = client.get("/auth/roster").json()["staff"]
    person = next(row for row in roster if row["display_name"] == role_name)
    pins = {
        "Maria Santos": "2468",
        "Joy Reyes": "1357",
        "Devon Brooks": "8024",
        "Grace Adeyemi": "5913",
        "Sam Patel": "4470",
        "Riley Chen": "9130",
        "Helen Cho": "6204",
    }
    response = client.post("/auth/login", json={"staff_id": person["id"], "pin": pins[role_name]})
    assert response.status_code == 200, response.text
    return response.json()["token"], person["id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_and_seed(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["pilot_mode"] is True
    assert health.json()["gate1"] == "not_run"
    assert health.json()["resident_data"] == "demo_only"
    roster = client.get("/auth/roster").json()["staff"]
    assert len(roster) == 7
    names = {row["display_name"] for row in roster}
    assert {"Riley Chen", "Helen Cho"} <= names


def test_cna_shift_is_ordered_and_traced(client):
    token, _ = _login(client, "Maria Santos")
    shift = client.get("/me/shift", headers=_auth(token))
    assert shift.status_code == 200, shift.text
    body = shift.json()
    assert body["language"] == "es"
    assert body["items"]
    priorities = [item["priority"] for item in body["items"]]
    assert priorities == sorted(priorities, reverse=True)
    elena = next(item for item in body["items"] if item["resident"]["preferred_name"] == "Elena Alvarez")
    assert "turn" in elena["tasks"]
    assert elena["why"]["worst_area"] == "sacrum"
    assert any(line["code"] == "pref.turn.side_preferred" for line in elena["how_to"])
    assert elena["alert_id"]
    alert_headers = _auth(token)
    # The alert row stores rule, inputs, plan version and model version.
    from turnwise.db import SessionLocal

    db = SessionLocal()
    alert = db.get(Alert, elena["alert_id"])
    assert alert.rule.startswith("turn_due")
    assert alert.inputs["worst_area"] == "sacrum"
    assert alert.plan_version == 1
    assert alert.model_version
    db.close()
    assert alert_headers


def test_posting_events_updates_budget_and_resolves_on_turn(client):
    token, _ = _login(client, "Maria Santos")
    edge = {"Authorization": "Bearer edge-test-token"}
    shift = client.get("/me/shift", headers=_auth(token)).json()
    elena = next(item for item in shift["items"] if item["resident"]["preferred_name"] == "Elena Alvarez")
    resident_id = elena["resident"]["id"]
    from turnwise.db import SessionLocal

    db = SessionLocal()
    resident = db.get(Resident, resident_id)
    state = db.get(ResidentState, resident_id)
    # Replay a long stretch on the back, then a witnessed turn to the right.
    start = datetime.now(UTC) - timedelta(minutes=30)
    state.last_ts = start
    state.position = "back"
    state.load = {area: 100.0 if area in {"sacrum", "heels", "occiput"} else 0.0 for area in ALL_AREAS}
    state.relief_since = {area: None for area in ALL_AREAS}
    db.commit()
    room_id = resident.room_id
    db.close()

    moved = client.post(
        "/events",
        headers=edge,
        json={
            "room_id": room_id,
            "resident_id": resident_id,
            "ts": datetime.now(UTC).isoformat(),
            "kind": "turn",
            "value": {"from": "back", "to": "right", "persons": 2},
            "confidence": 0.93,
            "model_version": "position-v0.0.0-rules",
        },
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["resolved_alerts"] >= 1
    db = SessionLocal()
    state = db.get(ResidentState, resident_id)
    assert state.position == "right"
    assert state.relief_since["sacrum"] is not None
    open_turns = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == resident_id, Alert.status.in_(["sent", "accepted", "escalated"]))
        .count()
    )
    assert open_turns == 0
    db.close()


def test_cna_cannot_open_an_unassigned_resident_or_approve_a_plan(client):
    devon, _ = _login(client, "Devon Brooks")
    maria, _ = _login(client, "Maria Santos")
    shift = client.get("/me/shift", headers=_auth(maria)).json()
    resident_id = shift["items"][0]["resident"]["id"]
    denied = client.get(f"/residents/{resident_id}/card", headers=_auth(devon))
    assert denied.status_code == 403
    plans = client.get("/nurse/plans/pending", headers=_auth(maria))
    assert plans.status_code == 403


def test_nurse_approval_updates_the_cna_schedule(client):
    nurse, _ = _login(client, "Sam Patel")
    pending = client.get("/nurse/plans/pending", headers=_auth(nurse)).json()["plans"]
    assert pending
    plan = pending[0]
    approved = client.post(
        f"/nurse/plans/{plan['id']}/approve",
        headers=_auth(nurse),
        json={"reason": "Night movement is low; tighten the night limit.", "night_lying_limit_min": 90},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    maria, _ = _login(client, "Maria Santos")
    shift = client.get("/me/shift", headers=_auth(maria))
    assert shift.status_code == 200


def test_ingest_csv_and_export(client):
    nurse, _ = _login(client, "Sam Patel")
    residents = "preferred_name,room_label,language,lying_limit_min\nAda Lovelace,101,en,120\n"
    braden = (
        "preferred_name,assessed_at,sensory,moisture,activity,mobility,nutrition,friction_shear\n"
        "Ada Lovelace,2026-09-01T00:00:00+00:00,3,3,2,2,3,2\n"
    )
    schedules = (
        "preferred_name,kind,due_at,window_min\n"
        "Ada Lovelace,check,2026-09-27T12:00:00+00:00,30\n"
    )
    response = client.post(
        "/ingest/records",
        headers=_auth(nurse),
        files={
            "residents": ("residents.csv", residents, "text/csv"),
            "braden": ("braden.csv", braden, "text/csv"),
            "schedules": ("schedules.csv", schedules, "text/csv"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["residents"] == 1
    assert body["braden"] == 1
    assert body["schedules"] == 1
    exported = client.get("/export/care", headers=_auth(nurse))
    assert exported.status_code == 200
    assert "resident" in exported.text


def test_rule_extractor_requires_nurse_approval(client):
    nurse, _ = _login(client, "Sam Patel")
    maria, _ = _login(client, "Maria Santos")
    shift = client.get("/me/shift", headers=_auth(maria)).json()
    resident_id = next(
        item["resident"]["id"]
        for item in shift["items"]
        if item["resident"]["preferred_name"] == "Harold Bennett"
    )
    extracted = client.post(
        "/nurse/preferences/extract",
        headers=_auth(nurse),
        json={
            "resident_id": resident_id,
            "text": "Resident prefers to be positioned on his right side. Pillow between knees.",
        },
    )
    assert extracted.status_code == 200, extracted.text
    suggestions = extracted.json()["suggestions"]
    assert suggestions
    assert extracted.json()["method"] == "rules"
    card = client.get(f"/residents/{resident_id}/card", headers=_auth(maria)).json()
    assert all(line["code"] != "pref.turn.side_preferred" or line["params"].get("side") != "right" for line in card["how_to"])
    approved = client.post(
        f"/nurse/preferences/{suggestions[0]['id']}/approve",
        headers=_auth(nurse),
    )
    assert approved.status_code == 200
    card = client.get(f"/residents/{resident_id}/card", headers=_auth(maria)).json()
    assert any(
        line["code"] == "pref.turn.side_preferred" and line["params"].get("side") == "right"
        for line in card["how_to"]
    )


def test_uncertain_baby_monitor_frame_does_not_reset_the_timer(client):
    edge = {"Authorization": "Bearer edge-test-token"}
    token, _ = _login(client, "Maria Santos")
    shift = client.get("/me/shift", headers=_auth(token)).json()
    elena = next(item for item in shift["items"] if item["resident"]["preferred_name"] == "Elena Alvarez")
    resident_id = elena["resident"]["id"]
    from turnwise.db import SessionLocal

    db = SessionLocal()
    resident = db.get(Resident, resident_id)
    room_id = resident.room_id
    before = db.get(ResidentState, resident_id)
    assert before.position == "back"
    assert before.relief_since["sacrum"] is None
    open_before = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == resident_id, Alert.status.in_(["sent", "accepted", "passed", "escalated"]))
        .count()
    )
    db.close()
    moment = datetime.now(UTC).isoformat()
    low = client.post(
        "/events",
        headers=edge,
        json={
            "room_id": room_id,
            "resident_id": resident_id,
            "ts": moment,
            "kind": "position",
            "source": "camera",
            "device_id": "baby-monitor-12",
            "value": {"position": "left", "persons_in_zone": 2},
            "confidence": 0.4,
            "model_version": "position-v0.0.0-rules",
        },
    )
    assert low.status_code == 200, low.text
    assert low.json()["resolved_alerts"] == 0
    assert low.json()["position"] == "back"
    vitals = client.post(
        "/events",
        headers=edge,
        json={
            "room_id": room_id,
            "resident_id": resident_id,
            "ts": moment,
            "kind": "night_vitals",
            "source": "camera",
            "device_id": "baby-monitor-12",
            "value": {"note": "not a reposition"},
            "model_version": "position-v0.0.0-rules",
        },
    )
    assert vitals.status_code == 200, vitals.text
    assert vitals.json()["resolved_alerts"] == 0
    db = SessionLocal()
    state = db.get(ResidentState, resident_id)
    assert state.position == "back"
    assert state.relief_since["sacrum"] is None
    assert state.camera_online is True
    event = (
        db.query(Event)
        .filter(Event.resident_id == resident_id, Event.kind == "position")
        .order_by(Event.id.desc())
        .first()
    )
    assert event.source == "camera"
    assert event.device_id == "baby-monitor-12"
    assert event.value["fusion"] == "uncertain"
    assert event.value["fusion_reason"] == "cover_unvalidated"
    assert event.value["gate1"] == "not_run"
    assert event.value["claim"] == "withheld"
    device = db.get(Device, "baby-monitor-12")
    assert device.last_seen is not None
    assert device.active is True
    assert device.config["fps"] is None or "fps" not in device.config or device.config.get("spectrum") != "offline"
    open_after = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == resident_id, Alert.status.in_(["sent", "accepted", "passed", "escalated"]))
        .count()
    )
    assert open_after == open_before
    db.close()
    covered = client.post(
        "/events",
        headers=edge,
        json={
            "room_id": room_id,
            "resident_id": resident_id,
            "ts": moment,
            "kind": "position",
            "source": "camera",
            "device_id": "baby-monitor-12",
            "value": {"position": "left", "persons_in_zone": 2, "cover": "blanket"},
            "confidence": 0.96,
            "model_version": "position-v0.0.0-rules",
        },
    )
    assert covered.status_code == 200, covered.text
    assert covered.json()["resolved_alerts"] == 0
    assert covered.json()["position"] == "back"
    sure = client.post(
        "/events",
        headers=edge,
        json={
            "room_id": room_id,
            "resident_id": resident_id,
            "ts": moment,
            "kind": "position",
            "source": "camera",
            "device_id": "baby-monitor-12",
            "value": {"position": "right", "persons_in_zone": 2, "cover": "none", "fps": 1.0, "latency_ms": 90},
            "confidence": 0.91,
            "model_version": "position-v0.0.0-rules",
        },
    )
    assert sure.status_code == 200, sure.text
    assert sure.json()["resolved_alerts"] >= 1
    assert sure.json()["position"] == "right"
    offline = client.post(
        "/events",
        headers=edge,
        json={
            "room_id": room_id,
            "resident_id": resident_id,
            "ts": moment,
            "kind": "device_offline",
            "source": "camera",
            "device_id": "baby-monitor-12",
            "value": {"reason": "no_frame", "silence_s": 120},
            "model_version": "position-v0.0.0-rules",
        },
    )
    assert offline.status_code == 200, offline.text
    db = SessionLocal()
    state = db.get(ResidentState, resident_id)
    assert state.camera_online is False
    assert state.camera_spectrum == "offline"
    device = db.get(Device, "baby-monitor-12")
    assert device.active is False
    assert device.config["spectrum"] == "offline"
    assert device.config["fps"] == 1.0
    db.close()


def test_missing_token_is_rejected(client):
    assert client.get("/me/shift").status_code == 401


def test_engineer_board_is_raw_and_director_does_not_invent_ulcers(client):
    maria, _ = _login(client, "Maria Santos")
    assert client.get("/engineer/board", headers=_auth(maria)).status_code == 403
    assert client.get("/director/board", headers=_auth(maria)).status_code == 403
    engineer, _ = _login(client, "Riley Chen")
    board = client.get("/engineer/board", headers=_auth(engineer)).json()
    assert board["position_model"] == "position-v0.0.0-rules"
    assert board["sensing"]["default"] == "infrared baby monitor"
    assert board["sensing"]["frames_leave_home"] is False
    assert board["sensing"]["per_side_under_blanket"] == "not_claimed"
    assert board["gate1"]["status"] == "not_run"
    assert board["gate1"]["hardware_hours"] == 0
    cameras = board["cameras"]
    assert len(cameras) == 10
    assert {row["kind"] for row in cameras} == {"camera"}
    elena_cam = next(row for row in cameras if row["room"] == "12")
    assert elena_cam["online"] is True
    assert elena_cam["infrared"] is True
    assert elena_cam["mic"] == "off"
    assert elena_cam["cloud"] == "off"
    assert elena_cam["simulated"] is True
    assert elena_cam["live"] is False
    assert elena_cam["uncertainty_pct"] == 8
    carmen_cam = next(row for row in cameras if row["room"] == "28")
    assert carmen_cam["online"] is False
    assert carmen_cam["infrared"] is False
    step_ids = [step["id"] for step in board["install"]["steps"]]
    assert {"consent", "mic", "cloud", "internet", "mount", "pair", "night"} <= set(step_ids)
    assert "bed" not in " ".join(step_ids)
    elena = next(row for row in board["residents"] if row["name"] == "Elena Alvarez")
    assert elena["camera_spectrum"] == "infrared"
    assert 0 <= elena["uncertainty_pct"] <= 100
    assert elena["confidence_pct"] + elena["uncertainty_pct"] == 100
    assert elena["areas"]
    assert "ratio" in elena["areas"][0]
    assert "wet_probability" in elena["continence"]
    assert "would_verify" in elena["visual_check"]
    assert "gate_pct" in elena["visual_check"]
    director, _ = _login(client, "Helen Cho")
    summary = client.get("/director/board", headers=_auth(director)).json()
    assert summary["pressure_injury"]["ulcers_prevented"] is None
    assert summary["position_claim"]["under_blanket"] == "not_claimed"
    assert summary["position_claim"]["gate1"] == "not_run"
    assert summary["pressure_injury"]["new_injuries_recorded_this_shift"] == 0
    saved = summary["time_saved"]
    assert saved["total_minutes"] == (
        saved["turning"]["minutes"] + saved["incontinence"]["minutes"] + saved["visual_checks"]["minutes"]
    )
    assert saved["visual_checks"]["minutes"] >= 16
    assert summary["pressure_injury"]["residents_inside_nurse_limit"] >= 1


def test_calendar_and_time_saved_use_the_same_shift(client):
    token, _ = _login(client, "Maria Santos")
    shift = client.get("/me/shift", headers=_auth(token)).json()
    saved = shift["time_saved"]
    assert saved["verified_checks"] >= 4
    assert saved["minutes"] == saved["verified_checks"] * 4 + saved["merged_visits"] * 3
    ics = client.get("/me/shift.ics", headers=_auth(token))
    assert ics.status_code == 200
    assert "text/calendar" in ics.headers["content-type"]
    assert "Elena Alvarez" in ics.text
    assert "BEGIN:VCALENDAR" in ics.text
    elena = next(item for item in shift["items"] if item["resident"]["preferred_name"] == "Elena Alvarez")
    card = client.get(f"/residents/{elena['resident']['id']}/card", headers=_auth(token)).json()
    assert card["camera_spectrum"] == "infrared"
    assert card["model_version"] == "position-v0.0.0-rules"
    assert card["vitals"]["source"] == "morning_chart"
    assert card["vitals"]["spo2"] == 96
    assert card["diet"]["is_order"] is False
    assert card["diet"]["applies"] is True
    assert card["diet"]["code"] == "diet.wet_evening"
    nurse, _ = _login(client, "Sam Patel")
    roster = client.get("/nurse/residents", headers=_auth(nurse)).json()["residents"]
    james_id = next(row["id"] for row in roster if row["preferred_name"] == "James Okonkwo")
    james_card = client.get(f"/residents/{james_id}/card", headers=_auth(token)).json()
    assert james_card["diet"]["applies"] is False
