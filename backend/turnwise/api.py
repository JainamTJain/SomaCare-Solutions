"""HTTP and websocket API. Role checks keep CNAs to their assignment."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from turnwise.auth import Principal, get_db, get_principal, issue_token, require_roles, verify_pin
from turnwise.boards import director_board, engineer_board
from turnwise.daybook import shift_ics
from turnwise.careflow import (
    apply_event,
    approve_plan,
    build_shift,
    continence_view,
    history,
    record_override,
    resident_card,
    staff_can_see,
    utcnow,
)
from turnwise.config import load_config
from turnwise.engine.preferences import extract_with_fallback
from turnwise.ingest import export_care, import_records
from turnwise.models import (
    Alert,
    AuditLog,
    HelpRequest,
    HandoffNote,
    Plan,
    Preference,
    Resident,
    ResidentState,
    Room,
    Shift,
    SkinAssessment,
    SkinCapture,
    Staff,
    StaffCredential,
    Task,
    Unit,
)

router = APIRouter()


class LoginIn(BaseModel):
    staff_id: str
    pin: str


class EventIn(BaseModel):
    room_id: str | None = None
    resident_id: str | None = None
    ts: datetime
    kind: str
    value: dict = Field(default_factory=dict)
    confidence: float | None = None
    model_version: str | None = None
    source: str | None = None
    device_id: str | None = None


class HeartbeatIn(BaseModel):
    room_id: str
    resident_id: str | None = None
    ts: datetime | None = None
    model_version: str | None = "edge-heartbeat"
    device_id: str | None = None
    value: dict = Field(default_factory=dict)


class PlanDecision(BaseModel):
    reason: str
    lying_limit_min: int | None = None
    sitting_limit_min: int | None = None
    night_lying_limit_min: int | None = None
    continence_threshold: float | None = None
    mattress_type: str | None = None
    two_person: bool | None = None


class ExtractIn(BaseModel):
    resident_id: str
    text: str


class HelpIn(BaseModel):
    resident_id: str


class OverrideIn(BaseModel):
    target_type: str
    target_id: str
    reason: str


class AssessmentIn(BaseModel):
    resident_id: str
    area: str
    finding: str
    warmth: bool | None = None
    firmness: bool | None = None
    pain: bool | None = None


class HandoffIn(BaseModel):
    text_note: str | None = None
    shift_id: str | None = None


def _staff(db: Session, principal: Principal) -> Staff:
    person = db.get(Staff, principal.id)
    if person is None:
        raise HTTPException(status_code=401, detail="unknown staff")
    return person


def _guard_resident(db: Session, principal: Principal, resident_id: str) -> Resident:
    if not staff_can_see(db, principal.id, principal.role, resident_id, utcnow()):
        raise HTTPException(status_code=403, detail="not on your assignment")
    resident = db.get(Resident, resident_id)
    if resident is None:
        raise HTTPException(status_code=404, detail="resident not found")
    return resident


@router.get("/health")
def health():
    config = load_config()
    return {
        "ok": True,
        "pilot_mode": config.pilot_mode,
        "llm_preference_extract": config.features.llm_preference_extract,
        "llm_note_translation": config.features.llm_note_translation,
        "gate1": "not_run",
        "resident_data": "demo_only",
    }


@router.get("/auth/roster")
def roster(db: Session = Depends(get_db)):
    people = db.query(Staff).order_by(Staff.display_name).all()
    return {
        "staff": [
            {
                "id": person.id,
                "display_name": person.display_name,
                "role": person.role,
                "ui_language": person.ui_language,
            }
            for person in people
        ]
    }


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    person = db.get(Staff, body.staff_id)
    credential = db.get(StaffCredential, body.staff_id) if person else None
    if person is None or credential is None or not verify_pin(body.pin, credential):
        raise HTTPException(status_code=401, detail="name or PIN does not match")
    db.add(
        AuditLog(
            staff_id=person.id,
            action="auth.login",
            target_type="staff",
            target_id=person.id,
            detail={"role": person.role},
        )
    )
    db.commit()
    return {
        "token": issue_token(person),
        "staff": {
            "id": person.id,
            "display_name": person.display_name,
            "role": person.role,
            "ui_language": person.ui_language,
        },
    }


@router.post("/events")
def post_event(
    body: EventIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.is_edge and principal.role not in {"admin", "nurse", "charge_nurse"}:
        raise HTTPException(status_code=403, detail="edge token required")
    try:
        result = apply_event(db, body.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    hub.publish(result)
    return result


@router.post("/events/heartbeat")
def post_heartbeat(
    body: HeartbeatIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.is_edge and principal.role != "admin":
        raise HTTPException(status_code=403, detail="edge token required")
    payload = {
        "room_id": body.room_id,
        "resident_id": body.resident_id,
        "ts": body.ts or utcnow(),
        "kind": "heartbeat",
        "value": body.value or {},
        "confidence": None,
        "model_version": body.model_version,
        "source": "camera",
        "device_id": body.device_id,
    }
    try:
        result = apply_event(db, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/ingest/records")
async def ingest(
    residents: UploadFile | None = File(default=None),
    braden: UploadFile | None = File(default=None),
    schedules: UploadFile | None = File(default=None),
    principal: Principal = Depends(require_roles("admin", "nurse", "charge_nurse")),
    db: Session = Depends(get_db),
):
    del principal
    files = {}
    for name, handle in ("residents", residents), ("braden", braden), ("schedules", schedules):
        if handle is not None:
            files[name] = (await handle.read()).decode()
    if not files:
        raise HTTPException(status_code=400, detail="upload at least one CSV")
    return import_records(db, files)


@router.get("/export/care")
def export(
    principal: Principal = Depends(require_roles("admin", "nurse", "charge_nurse")),
    db: Session = Depends(get_db),
):
    del principal
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(export_care(db), media_type="text/csv")


@router.get("/engineer/board")
def engineer_view(
    principal: Principal = Depends(require_roles("engineer", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    return engineer_board(db, utcnow())


@router.get("/director/board")
def director_view(
    principal: Principal = Depends(require_roles("director", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    return director_board(db, utcnow())


@router.get("/me/shift")
def my_shift(
    principal: Principal = Depends(require_roles("cna", "charge_nurse", "nurse", "admin")),
    db: Session = Depends(get_db),
):
    person = _staff(db, principal)
    return build_shift(db, person, utcnow())


@router.get("/me/shift.ics")
def my_shift_calendar(
    principal: Principal = Depends(require_roles("cna", "charge_nurse", "nurse", "admin")),
    db: Session = Depends(get_db),
):
    """The same visits, as a calendar file Google Calendar can import."""
    from fastapi.responses import Response

    person = _staff(db, principal)
    body = build_shift(db, person, utcnow())
    payload = shift_ics(body["items"], person.display_name)
    return Response(
        content=payload,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="sorety-shift.ics"'},
    )


@router.get("/residents/{resident_id}/card")
def card(
    resident_id: str,
    lang: str | None = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _guard_resident(db, principal, resident_id)
    payload = resident_card(db, resident_id, utcnow())
    payload["lang"] = lang or principal.ui_language
    return payload


@router.get("/residents/{resident_id}/history")
def resident_history(
    resident_id: str,
    days: int = Query(default=7, ge=1, le=30),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _guard_resident(db, principal, resident_id)
    return history(db, resident_id, days, utcnow())


@router.get("/residents/{resident_id}/continence")
def resident_continence(
    resident_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _guard_resident(db, principal, resident_id)
    return continence_view(db, resident_id, utcnow())


def _alert_for_staff(db: Session, principal: Principal, alert_id: str) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if principal.role == "cna" and alert.staff_id != principal.id:
        raise HTTPException(status_code=403, detail="not your alert")
    return alert


@router.post("/alerts/{alert_id}/accept")
def accept_alert(
    alert_id: str,
    principal: Principal = Depends(require_roles("cna", "charge_nurse")),
    db: Session = Depends(get_db),
):
    alert = _alert_for_staff(db, principal, alert_id)
    alert.status = "accepted"
    alert.accepted_at = utcnow()
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="alert.accept",
            target_type="alert",
            target_id=alert.id,
            detail={"rule": alert.rule},
        )
    )
    db.commit()
    return {"id": alert.id, "status": alert.status}


@router.post("/alerts/{alert_id}/pass")
def pass_alert(
    alert_id: str,
    to_staff_id: str | None = None,
    principal: Principal = Depends(require_roles("cna", "charge_nurse")),
    db: Session = Depends(get_db),
):
    alert = _alert_for_staff(db, principal, alert_id)
    if to_staff_id is None:
        other = (
            db.query(Staff)
            .filter(Staff.role == "cna", Staff.id != principal.id)
            .order_by(Staff.display_name)
            .first()
        )
        if other is None:
            raise HTTPException(status_code=409, detail="no teammate to pass to")
        to_staff_id = other.id
    teammate = db.get(Staff, to_staff_id)
    if teammate is None:
        raise HTTPException(status_code=404, detail="teammate not found")
    alert.status = "passed"
    alert.staff_id = teammate.id
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="alert.pass",
            target_type="alert",
            target_id=alert.id,
            detail={"to": teammate.id},
        )
    )
    db.commit()
    return {"id": alert.id, "status": alert.status, "staff_id": teammate.id, "display_name": teammate.display_name}


@router.post("/alerts/{alert_id}/confirm")
def confirm_alert(
    alert_id: str,
    principal: Principal = Depends(require_roles("cna", "charge_nurse")),
    db: Session = Depends(get_db),
):
    """One tap when the camera could not confirm the turn."""
    alert = _alert_for_staff(db, principal, alert_id)
    task = db.get(Task, alert.task_id) if alert.task_id else None
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    now = utcnow()
    resident = db.get(Resident, task.resident_id)
    side = "left" if (db.get(ResidentState, resident.id).position == "right") else "right"
    for pref in db.query(Preference).filter(Preference.resident_id == resident.id, Preference.code == "pref.turn.side_preferred"):
        if pref.params and pref.params.get("side") in {"left", "right"}:
            side = pref.params["side"]
    apply_event(
        db,
        {
            "room_id": resident.room_id,
            "resident_id": resident.id,
            "ts": now,
            "kind": "turn",
            "value": {"to": side, "from": db.get(ResidentState, resident.id).position, "confirmed_by": principal.id},
            "confidence": None,
            "model_version": "cna-confirm",
        },
    )
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="alert.confirm",
            target_type="alert",
            target_id=alert.id,
            detail={"rule": alert.rule},
        )
    )
    db.commit()
    db.refresh(alert)
    return {"id": alert.id, "status": alert.status}


@router.post("/help")
def help_request(
    body: HelpIn,
    principal: Principal = Depends(require_roles("cna", "charge_nurse")),
    db: Session = Depends(get_db),
):
    resident = _guard_resident(db, principal, body.resident_id)
    teammate = (
        db.query(Staff)
        .filter(Staff.role == "cna", Staff.id != principal.id)
        .order_by(Staff.display_name)
        .first()
    )
    room = resident.room
    eta = 3
    if teammate and room is not None:
        eta = 2 + (room.hallway_order % 4)
    row = HelpRequest(
        resident_id=resident.id,
        requester_id=principal.id,
        teammate_id=teammate.id if teammate else None,
        eta_min=eta,
    )
    db.add(row)
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="help.request",
            target_type="resident",
            target_id=resident.id,
            detail={"teammate_id": teammate.id if teammate else None, "eta_min": eta},
        )
    )
    db.commit()
    return {
        "id": row.id,
        "teammate": teammate.display_name if teammate else None,
        "eta_min": eta,
        "resident": resident.preferred_name,
    }


@router.post("/handoff/notes")
async def handoff(
    text_note: str | None = Form(default=None),
    audio: UploadFile | None = File(default=None),
    principal: Principal = Depends(require_roles("cna", "charge_nurse", "nurse")),
    db: Session = Depends(get_db),
):
    """Audio stays on the facility server. Transcription is a local speech
    model when one is installed; until then the note is saved with the audio."""
    audio_ref = None
    if audio is not None:
        from turnwise.paths import data_dir

        dest_dir = data_dir() / "handoff"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{principal.id}-{int(utcnow().timestamp())}.webm"
        dest.write_bytes(await audio.read())
        audio_ref = str(dest)
    note = HandoffNote(
        staff_id=principal.id,
        text_note=text_note,
        audio_ref=audio_ref,
        transcript=None,
        transcript_status="pending_local_asr" if audio_ref else "text_only",
    )
    db.add(note)
    db.commit()
    return {
        "id": note.id,
        "transcript_status": note.transcript_status,
        "text_note": note.text_note,
    }


@router.get("/handoff/notes")
def list_handoff(
    principal: Principal = Depends(require_roles("cna", "charge_nurse", "nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    notes = db.query(HandoffNote).order_by(HandoffNote.created_at.desc()).limit(20).all()
    return {
        "notes": [
            {
                "id": note.id,
                "staff_id": note.staff_id,
                "created_at": note.created_at.isoformat() if note.created_at else None,
                "text_note": note.text_note,
                "transcript": note.transcript,
                "transcript_status": note.transcript_status,
                "has_audio": bool(note.audio_ref),
            }
            for note in notes
        ]
    }


@router.get("/nurse/residents")
def nurse_residents(
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    rows = db.query(Resident).all()
    payload = []
    for resident in rows:
        room = db.get(Room, resident.room_id)
        payload.append(
            {
                "id": resident.id,
                "preferred_name": resident.preferred_name,
                "room": room.label if room else "",
                "language": resident.language,
            }
        )
    payload.sort(key=lambda row: row["room"])
    return {"residents": payload}


@router.get("/nurse/plans/pending")
def pending_plans(
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    rows = db.query(Plan).filter(Plan.status == "draft").all()
    payload = []
    for plan in rows:
        resident = db.get(Resident, plan.resident_id)
        payload.append(
            {
                "id": plan.id,
                "resident_id": plan.resident_id,
                "resident_name": resident.preferred_name if resident else "",
                "version": plan.version,
                "lying_limit_min": plan.lying_limit_min,
                "sitting_limit_min": plan.sitting_limit_min,
                "night_lying_limit_min": plan.night_lying_limit_min,
                "continence_threshold": plan.continence_threshold,
                "mattress_type": plan.mattress_type,
                "two_person": plan.two_person,
                "reason": plan.reason,
                "suggestion": plan.suggestion,
                "status": plan.status,
            }
        )
    return {"plans": payload}


@router.post("/nurse/plans/{plan_id}/approve")
def approve(
    plan_id: str,
    body: PlanDecision,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    try:
        plan = approve_plan(db, plan_id, principal.id, body.model_dump(), utcnow())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": plan.id, "status": plan.status, "version": plan.version}


@router.post("/nurse/preferences/extract")
def extract_prefs(
    body: ExtractIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    config = load_config()
    suggestions, method = extract_with_fallback(
        body.text, llm_enabled=config.features.llm_preference_extract
    )
    created = []
    for suggestion in suggestions:
        row = Preference(
            resident_id=body.resident_id,
            category=suggestion.category if suggestion.category != "turning" else "turning",
            code=suggestion.code,
            params=suggestion.params,
            source_type=method,
            source_excerpt=suggestion.source_excerpt,
            source_date=utcnow().date(),
        )
        if suggestion.category == "comfort":
            row.category = "comfort"
        elif suggestion.category == "continence":
            row.category = "continence"
        db.add(row)
        db.flush()
        created.append(
            {
                "id": row.id,
                "code": row.code,
                "params": row.params,
                "source_excerpt": row.source_excerpt,
                "method": method,
                "approved": False,
            }
        )
    db.commit()
    return {"suggestions": created, "method": method}


@router.get("/nurse/preferences/pending")
def pending_prefs(
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    rows = db.query(Preference).filter(Preference.approved_by.is_(None)).all()
    payload = []
    for pref in rows:
        resident = db.get(Resident, pref.resident_id)
        payload.append(
            {
                "id": pref.id,
                "resident_id": pref.resident_id,
                "resident_name": resident.preferred_name if resident else "",
                "category": pref.category,
                "code": pref.code,
                "params": pref.params,
                "source_excerpt": pref.source_excerpt,
                "source_type": pref.source_type,
                "text_en": pref.text_en,
            }
        )
    return {"preferences": payload}


@router.post("/nurse/preferences/{preference_id}/approve")
def approve_pref(
    preference_id: str,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    pref = db.get(Preference, preference_id)
    if pref is None:
        raise HTTPException(status_code=404, detail="preference not found")
    pref.approved_by = principal.id
    pref.approved_at = utcnow()
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="preference.approve",
            target_type="preference",
            target_id=pref.id,
            detail={"code": pref.code, "excerpt": pref.source_excerpt},
        )
    )
    db.commit()
    return {"id": pref.id, "approved": True}


@router.post("/overrides")
def create_override(
    body: OverrideIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="a reason is required")
    row = record_override(db, principal.id, body.target_type, body.target_id, body.reason, utcnow())
    return {"id": row.id}


@router.get("/nurse/overrides")
def list_overrides(
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    from turnwise.models import Override

    rows = db.query(Override).order_by(Override.ts.desc()).limit(100).all()
    return {
        "overrides": [
            {
                "id": row.id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "by_staff": row.by_staff,
                "reason": row.reason,
                "ts": row.ts.isoformat() if row.ts else None,
            }
            for row in rows
        ]
    }


@router.post("/skin/captures")
async def skin_capture(
    resident_id: str = Form(...),
    area: str = Form(...),
    source: str = Form(...),
    image: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if source not in {"phone", "room"}:
        raise HTTPException(status_code=400, detail="source must be phone or room")
    if not principal.is_edge:
        _guard_resident(db, principal, resident_id)
    raw = await image.read()
    from turnwise.skincheck import assess_upload

    result = assess_upload(raw)
    # Shadow mode: the classifier is not shown to staff until its gate passes.
    capture = SkinCapture(
        resident_id=resident_id,
        area=area,
        source=source,
        image_ref=result["image_ref"],
        quality=result["quality"],
        model_flag=result["model_flag"],
        model_version=result["model_version"],
        shown_to_staff=False,
    )
    if capture.shown_to_staff:
        raise RuntimeError("skin model output cannot be shown before the acceptance gate")
    db.add(capture)
    db.commit()
    return {
        "id": capture.id,
        "shown_to_staff": False,
        "quality_ok": result["ok"],
        "model_flag": capture.model_flag,
        "model_version": capture.model_version,
    }


@router.post("/skin/assessments")
def skin_assessment(
    body: AssessmentIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse")),
    db: Session = Depends(get_db),
):
    allowed = {
        "normal",
        "blanchable_redness",
        "nonblanchable_redness",
        "stage2",
        "stage3",
        "stage4",
        "unstageable",
        "dti",
        "iad",
    }
    if body.finding not in allowed:
        raise HTTPException(status_code=400, detail="finding not in the nurse scale")
    row = SkinAssessment(
        resident_id=body.resident_id,
        area=body.area,
        finding=body.finding,
        warmth=body.warmth,
        firmness=body.firmness,
        pain=body.pain,
        assessed_by=principal.id,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "finding": row.finding}


@router.websocket("/stream/unit/{unit_id}")
async def stream(websocket: WebSocket, unit_id: str):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    hub.subscribe(queue)
    try:
        await websocket.send_json({"kind": "hello", "unit_id": unit_id})
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        hub.unsubscribe(queue)
    finally:
        hub.unsubscribe(queue)


class Hub:
    def __init__(self):
        self.queues: list[asyncio.Queue] = []

    def subscribe(self, queue: asyncio.Queue) -> None:
        self.queues.append(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self.queues:
            self.queues.remove(queue)

    def publish(self, message: dict) -> None:
        for queue in list(self.queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue


hub = Hub()
