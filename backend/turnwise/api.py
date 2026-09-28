"""HTTP and websocket API. Role checks keep CNAs to their assignment."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from turnwise.auth import SESSION_COOKIE, TOKEN_MAX_AGE_S, Principal, get_db, get_principal, issue_token, require_roles, verify_pin
from turnwise.boards import director_board, engineer_board
from turnwise.daybook import shift_ics
from turnwise.careflow import (
    apply_event,
    approve_plan,
    build_shift,
    continence_view,
    current_shift,
    full_picture,
    history,
    record_override,
    resident_card,
    staff_can_see,
    utcnow,
)
from turnwise.clock import status as clock_status
from turnwise.config import load_config
from turnwise.consent import has_signed, request_consent, revoke_consent, send_consent, sign_consent, simple_pdf
from turnwise.engine.preferences import extract_with_fallback
from turnwise.ingest import export_care, import_records
from turnwise.live import format_sse, snapshot
from turnwise.settings import DEMO_PINS, demo_mode, public_config
from turnwise.models import (
    Alert,
    Assignment,
    AuditLog,
    HelpRequest,
    HandoffNote,
    ConsentRecord,
    Device,
    Facility,
    Lead,
    MealLog,
    ScheduleTemplate,
    StaffTour,
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


class ConsentRequestIn(BaseModel):
    resident_id: str
    scope: str


class ConsentSignIn(BaseModel):
    signer_name: str
    relationship: str = "resident"


class ConsentRevokeIn(BaseModel):
    reason: str


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
    body = {
        "ok": True,
        "pilot_mode": config.pilot_mode,
        "llm_preference_extract": config.features.llm_preference_extract,
        "llm_note_translation": config.features.llm_note_translation,
        "gate1": "not_run",
        "resident_data": "demo_only",
    }
    body.update(clock_status())
    return body


@router.get("/config")
def runtime_config():
    return public_config()


@router.get("/auth/roster")
def roster(db: Session = Depends(get_db)):
    people = db.query(Staff).order_by(Staff.display_name).all()
    show_pins = demo_mode()
    rows = []
    for person in people:
        row = {
            "id": person.id,
            "display_name": person.display_name,
            "role": person.role,
            "ui_language": person.ui_language,
        }
        if show_pins and person.display_name in DEMO_PINS:
            row["pin"] = DEMO_PINS[person.display_name]
        rows.append(row)
    return {"staff": rows}


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    person = db.get(Staff, body.staff_id)
    credential = db.get(StaffCredential, body.staff_id) if person else None
    now = datetime.now(timezone.utc)
    locked = credential.locked_until if credential is not None else None
    if locked is not None and locked.tzinfo is None:
        locked = locked.replace(tzinfo=timezone.utc)
    if locked is not None and locked > now:
        raise HTTPException(
            status_code=429,
            detail="Too many tries. Please wait a few minutes and try again.",
        )
    if person is None or credential is None or not verify_pin(body.pin, credential):
        if credential is not None:
            credential.failed_attempts = int(credential.failed_attempts or 0) + 1
            if credential.failed_attempts >= 5:
                credential.locked_until = now + timedelta(minutes=15)
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail="Too many tries. Please wait a few minutes and try again.",
                )
            db.commit()
        raise HTTPException(
            status_code=401,
            detail="That PIN does not match. Try again, or ask your director to reset it.",
        )
    credential.failed_attempts = 0
    credential.locked_until = None
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
    token = issue_token(person)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=TOKEN_MAX_AGE_S,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {
        "token": token,
        "staff": {
            "id": person.id,
            "display_name": person.display_name,
            "role": person.role,
            "ui_language": person.ui_language,
        },
    }


def _consent_row(row: ConsentRecord) -> dict:
    return {
        "id": row.id,
        "scope": row.scope,
        "status": row.status,
        "form_version": row.form_version,
        "explanation_shown": row.explanation_shown,
        "sent_to": row.sent_to,
        "signature_ref": row.signature_ref,
        "signed_at": row.signed_at.isoformat() if row.signed_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


@router.get("/consent")
def consent_board(
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    residents = db.query(Resident).order_by(Resident.preferred_name).all()
    rows = []
    for resident in residents:
        records = (
            db.query(ConsentRecord)
            .filter(ConsentRecord.resident_id == resident.id)
            .order_by(ConsentRecord.requested_at.desc())
            .all()
        )
        scopes = {}
        for scope in ("position_monitoring", "skin_capture", "continence_tracking"):
            same = [record for record in records if record.scope == scope]
            signed = next((record for record in same if record.status == "signed" and record.revoked_at is None), None)
            match = signed or (same[0] if same else None)
            scopes[scope] = _consent_row(match) if match else {"id": None, "scope": scope, "status": "none"}
        rows.append({"resident_id": resident.id, "name": resident.preferred_name, "scopes": scopes})
    return {"residents": rows, "outbound": load_config().features.consent_outbound}


@router.post("/consent/request")
def consent_request(
    body: ConsentRequestIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    resident = db.get(Resident, body.resident_id)
    if resident is None:
        raise HTTPException(status_code=404, detail="resident not found")
    try:
        row = request_consent(db, resident=resident, scope=body.scope, staff_id=principal.id, now=utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _consent_row(row)


@router.post("/consent/{record_id}/send")
def consent_send(
    record_id: str,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    row = db.get(ConsentRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="consent not found")
    try:
        result = send_consent(db, row, now=utcnow(), outbound=load_config().features.consent_outbound)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/consent/{record_id}/sign")
def consent_sign(
    record_id: str,
    body: ConsentSignIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    row = db.get(ConsentRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="consent not found")
    try:
        sign_consent(db, row, signer_name=body.signer_name, relationship=body.relationship, now=utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _consent_row(row)


@router.post("/consent/{record_id}/revoke")
def consent_revoke(
    record_id: str,
    body: ConsentRevokeIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    row = db.get(ConsentRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="consent not found")
    try:
        revoke_consent(db, row, reason=body.reason, now=utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _consent_row(row)


@router.get("/consent/{record_id}/form")
def consent_form(
    record_id: str,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    row = db.get(ConsentRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="consent not found")
    return Response(content=simple_pdf(row.explanation_shown), media_type="application/pdf")


@router.get("/setup/status")
def setup_status(
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    del principal
    facility = db.query(Facility).first()
    residents = db.query(Resident).count()
    rooms = db.query(Room).count()
    cameras_on = db.query(Device).filter(Device.kind == "camera", Device.active.is_(True)).count()
    staff = db.query(Staff).count()
    scopes = 3
    signed = (
        db.query(ConsentRecord)
        .filter(ConsentRecord.status == "signed", ConsentRecord.revoked_at.is_(None))
        .count()
    )
    needed = residents * scopes
    steps = [
        {"id": "facility", "done": facility is not None, "label": facility.name if facility else ""},
        {"id": "rooms", "done": rooms > 0 and cameras_on == rooms, "have": rooms, "cameras_online": cameras_on},
        {"id": "residents", "done": residents > 0, "have": residents},
        {"id": "staff", "done": staff > 0, "have": staff},
        {"id": "consent", "done": residents > 0 and signed >= needed, "signed": signed, "needed": needed},
    ]
    return {"complete": all(step["done"] for step in steps), "steps": steps}


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
        headers={"Content-Disposition": 'attachment; filename="somacare-shift.ics"'},
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


@router.get("/residents/{resident_id}/full-picture")
def resident_full_picture(
    resident_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.role in {"nurse", "charge_nurse", "admin", "engineer", "director"}:
        if db.get(Resident, resident_id) is None:
            raise HTTPException(status_code=404, detail="resident not found")
    else:
        _guard_resident(db, principal, resident_id)
    return full_picture(db, resident_id, utcnow())


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
    if db.get(Resident, resident_id) is None:
        raise HTTPException(status_code=404, detail="resident not found")
    if not has_signed(db, resident_id, "skin_capture"):
        raise HTTPException(status_code=403, detail="skin capture consent is not signed")
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
    # TODO: leave shown_to_staff false until pilot data clears sensitivity >= 0.90,
    # specificity >= 0.80, and a skin-tone gap within 0.05. Do not flip it in code.
    if capture.shown_to_staff:
        raise RuntimeError("skin model output cannot be shown before the acceptance gate")
    db.add(capture)
    db.commit()
    return {
        "id": capture.id,
        "shown_to_staff": False,
        "quality_ok": result["ok"],
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


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    organization: str | None = None
    kind: str
    message: str | None = None


class TourIn(BaseModel):
    tour: str = Field(min_length=1, max_length=40)


class WindowIn(BaseModel):
    kind: str
    label: str = Field(min_length=1, max_length=80)
    start: str
    end: str


class ScheduleIn(BaseModel):
    resident_id: str
    reason: str = Field(min_length=3)
    windows: list[WindowIn]


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


class MealIn(BaseModel):
    meal_type: str
    items_text: str | None = None
    percent_eaten: int | None = None
    fluid_intake_ml: int | None = None


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_TOUR = re.compile(r"^[a-z0-9_]{1,40}$")
_LEAD_KINDS = {"pilot", "investor", "partner", "other"}
_MEALS = {"breakfast", "lunch", "dinner", "snack"}


def _window_row(window: WindowIn) -> dict:
    if window.kind not in {"fixed", "blackout"}:
        raise HTTPException(status_code=400, detail="window kind must be fixed or blackout")
    if not _HHMM.match(window.start) or not _HHMM.match(window.end):
        raise HTTPException(status_code=400, detail="window times use HH:MM")
    return {"kind": window.kind, "label": window.label, "start": window.start, "end": window.end}


def _schedule_row(row: ScheduleTemplate) -> dict:
    return {
        "id": row.id,
        "resident_id": row.resident_id,
        "version": row.version,
        "status": row.status,
        "reason": row.reason,
        "windows": row.windows or [],
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


@router.get("/stream")
async def unit_events(once: bool = False, principal: Principal = Depends(get_principal)):
    """Push resident status and alert changes for the caller's role.

    `once` returns a single event and closes. The live client omits it and
    keeps the connection open.
    """
    staff_id, role = principal.id, principal.role

    async def _events():
        from turnwise.db import SessionLocal

        previous = None
        while True:
            db = SessionLocal()
            try:
                payload = snapshot(db, staff_id, role)
            finally:
                db.close()
            encoded = format_sse(payload)
            if encoded != previous:
                yield encoded
                previous = encoded
            else:
                yield ": keepalive\n\n"
            if once:
                return
            await asyncio.sleep(2)

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.post("/leads")
def create_lead(body: LeadIn, db: Session = Depends(get_db)):
    if body.kind not in _LEAD_KINDS:
        raise HTTPException(status_code=400, detail="kind must be pilot, investor, partner, or other")
    if "@" not in body.email:
        raise HTTPException(status_code=400, detail="email needs an @")
    row = Lead(
        name=body.name.strip(),
        email=body.email.strip(),
        organization=(body.organization or "").strip() or None,
        kind=body.kind,
        message=(body.message or "").strip() or None,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "created_at": row.created_at.isoformat()}


@router.get("/leads")
def list_leads(
    principal: Principal = Depends(require_roles("director", "admin")),
    db: Session = Depends(get_db),
):
    rows = db.query(Lead).order_by(Lead.created_at.desc()).all()
    return {
        "leads": [
            {
                "id": row.id,
                "name": row.name,
                "email": row.email,
                "organization": row.organization,
                "kind": row.kind,
                "message": row.message,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/me/tours")
def my_tours(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.query(StaffTour).filter(StaffTour.staff_id == principal.id).order_by(StaffTour.tour_key).all()
    return {"tours": [{"tour": row.tour_key, "seen_at": row.seen_at.isoformat()} for row in rows]}


@router.post("/me/tours")
def mark_tour(body: TourIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if not _TOUR.match(body.tour):
        raise HTTPException(status_code=400, detail="tour key must be short lowercase words")
    existing = (
        db.query(StaffTour)
        .filter(StaffTour.staff_id == principal.id, StaffTour.tour_key == body.tour)
        .first()
    )
    if existing is None:
        existing = StaffTour(staff_id=principal.id, tour_key=body.tour)
        db.add(existing)
        db.commit()
    return {"tour": existing.tour_key, "seen_at": existing.seen_at.isoformat()}


@router.get("/nurse/schedules/{resident_id}")
def resident_schedule(
    resident_id: str,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    if db.get(Resident, resident_id) is None:
        raise HTTPException(status_code=404, detail="resident not found")
    rows = (
        db.query(ScheduleTemplate)
        .filter(ScheduleTemplate.resident_id == resident_id)
        .order_by(ScheduleTemplate.version.desc())
        .all()
    )
    return {"versions": [_schedule_row(row) for row in rows]}


@router.post("/nurse/schedules")
def draft_schedule(
    body: ScheduleIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    if db.get(Resident, body.resident_id) is None:
        raise HTTPException(status_code=404, detail="resident not found")
    latest = (
        db.query(ScheduleTemplate)
        .filter(ScheduleTemplate.resident_id == body.resident_id)
        .order_by(ScheduleTemplate.version.desc())
        .first()
    )
    row = ScheduleTemplate(
        resident_id=body.resident_id,
        version=(latest.version + 1) if latest else 1,
        status="draft",
        reason=body.reason.strip(),
        windows=[_window_row(window) for window in body.windows],
    )
    db.add(row)
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="schedule.draft",
            target_type="schedule_template",
            target_id=row.id,
            detail={"version": row.version, "resident_id": body.resident_id},
        )
    )
    db.commit()
    return _schedule_row(row)


@router.post("/nurse/schedules/{template_id}/approve")
def approve_schedule(
    template_id: str,
    body: ReasonIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "admin")),
    db: Session = Depends(get_db),
):
    row = db.get(ScheduleTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    if row.status == "approved":
        return _schedule_row(row)
    row.status = "approved"
    row.reason = body.reason.strip()
    row.approved_by = principal.id
    row.approved_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            staff_id=principal.id,
            action="schedule.approve",
            target_type="schedule_template",
            target_id=row.id,
            detail={"version": row.version},
        )
    )
    db.commit()
    return _schedule_row(row)


@router.get("/director/load")
def director_load(
    principal: Principal = Depends(require_roles("director", "admin")),
    db: Session = Depends(get_db),
):
    config = load_config()
    shift = current_shift(db, utcnow())
    counts: dict[str, int] = {}
    if shift is not None:
        for row in db.query(Assignment).filter(Assignment.shift_id == shift.id).all():
            counts[row.staff_id] = counts.get(row.staff_id, 0) + 1
    people = []
    for staff_id, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        person = db.get(Staff, staff_id)
        people.append(
            {
                "staff_id": staff_id,
                "display_name": person.display_name if person else None,
                "residents": count,
                "over": count > config.caregiver_ratio,
            }
        )
    return {"ratio": config.caregiver_ratio, "shift_id": shift.id if shift else None, "caregivers": people}


@router.get("/residents/{resident_id}/timeline")
def resident_timeline(
    resident_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    resident = _guard_resident(db, principal, resident_id)
    picture = full_picture(db, resident.id, utcnow())
    return {"resident_id": resident.id, "name": picture["name"], "timeline": picture["timeline"]}


@router.post("/residents/{resident_id}/meals")
def log_meal(
    resident_id: str,
    body: MealIn,
    principal: Principal = Depends(require_roles("nurse", "charge_nurse", "cna", "admin")),
    db: Session = Depends(get_db),
):
    resident = _guard_resident(db, principal, resident_id)
    if body.meal_type not in _MEALS:
        raise HTTPException(status_code=400, detail="meal_type must be breakfast, lunch, dinner, or snack")
    row = MealLog(
        resident_id=resident.id,
        meal_type=body.meal_type,
        items_text=body.items_text,
        percent_eaten=body.percent_eaten,
        fluid_intake_ml=body.fluid_intake_ml,
        entered_by=principal.id,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "meal_type": row.meal_type}
