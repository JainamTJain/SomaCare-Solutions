"""Apply events to the pressure budget and build a CNA's shift.

The care decisions in this module are the deterministic engine plus the
version-1 risk rules. No language model is called.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from turnwise.config import EngineConfig, load_config
from turnwise.consent import has_signed, monitoring_state, withhold_camera_fields, withhold_continence_prediction
from turnwise.daybook import (
    count_verified,
    diet_for_resident,
    latest_vitals,
    recent_chart_lines,
    time_saved,
)
from turnwise.engine.alerts import AlertState, advance_alert, allow_send
from turnwise.engine.fusion import BedMovement, VisionChange, classify_reposition, resets_timer
from turnwise.engine.gate1 import live_status
from turnwise.engine.budget import (
    ALL_AREAS,
    Budget,
    LimitContext,
    PlanView,
    limit as area_limit,
    worst_area,
)
from turnwise.engine.budget import turn_due
from turnwise.engine.continence import FEATURE_NAMES, continence_features, cumulative_wet, schedule_from_hazard
from turnwise.engine.risk_rules import ResidentRisk, dose_in_window, extra_risk_steps
from turnwise.engine.scheduler import SchedTask, can_verify_check, merge_tasks, risk_weight, with_caregiver_load
from turnwise.schedule import blackout_task_ids, ensure_fixed_tasks
from turnwise.models import (
    Alert,
    Assignment,
    AuditLog,
    BradenAssessment,
    ContinenceObs,
    Device,
    Event,
    MealLog,
    MedicationLog,
    MorningVital,
    Override,
    Plan,
    Preference,
    Resident,
    ResidentState,
    RiskFactor,
    Room,
    Shift,
    SkinCapture,
    Staff,
    Task,
)

OPEN_ALERT = ("sent", "accepted", "passed", "escalated")
POSITIONS = {"back", "left", "right", "sitting", "out_of_bed", "unknown", "out_of_room"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def cfg() -> EngineConfig:
    return load_config()


def audit(db: Session, staff_id: str | None, action: str, target_type: str, target_id: str, detail: dict):
    db.add(
        AuditLog(
            staff_id=staff_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            detail=detail,
        )
    )


def budget_from_state(state: ResidentState) -> Budget:
    relief = {}
    for area in ALL_AREAS:
        raw = (state.relief_since or {}).get(area)
        relief[area] = datetime.fromisoformat(raw) if raw else None
    load = {area: float((state.load or {}).get(area, 0.0)) for area in ALL_AREAS}
    return Budget(load=load, relief_since=relief, last_known=state.last_known or "back")


def save_budget(state: ResidentState, budget: Budget) -> None:
    state.load = {area: budget.load[area] for area in ALL_AREAS}
    state.relief_since = {
        area: budget.relief_since[area].isoformat() if budget.relief_since[area] else None
        for area in ALL_AREAS
    }
    state.last_known = budget.last_known


def latest_braden(db: Session, resident_id: str) -> BradenAssessment | None:
    return (
        db.query(BradenAssessment)
        .filter(BradenAssessment.resident_id == resident_id)
        .order_by(BradenAssessment.assessed_at.desc())
        .first()
    )


def approved_plan(db: Session, resident_id: str) -> Plan | None:
    return (
        db.query(Plan)
        .filter(Plan.resident_id == resident_id, Plan.status == "approved")
        .order_by(Plan.version.desc())
        .first()
    )


def _medication_flags(db: Session, resident_id: str, now: datetime, config: EngineConfig) -> tuple[bool, bool]:
    """Diuretic inside its window, and a sedating dose inside its window."""
    now = _aware(now)
    earliest = now - timedelta(hours=max(config.diuretic_window_hours, config.sedating_window_hours))
    rows = (
        db.query(MedicationLog)
        .filter(MedicationLog.resident_id == resident_id, MedicationLog.ts >= earliest)
        .all()
    )
    diuretic = False
    sedating = False
    for row in rows:
        given = _aware(row.ts)
        if row.is_diuretic and dose_in_window(given, now, config.diuretic_window_hours):
            diuretic = True
        if row.is_sedating and dose_in_window(given, now, config.sedating_window_hours):
            sedating = True
    return diuretic, sedating


def resident_risk(db: Session, resident_id: str, state: ResidentState, now: datetime | None = None) -> ResidentRisk:
    braden = latest_braden(db, resident_id)
    factors = {
        row.factor
        for row in db.query(RiskFactor).filter(RiskFactor.resident_id == resident_id)
        if row.confirmed_by is not None
    }
    if now is not None:
        _diuretic, sedating = _medication_flags(db, resident_id, now, cfg())
        if sedating:
            factors.add("sedating_medication")
    return ResidentRisk(
        braden_total=braden.total if braden else 15,
        braden_nutrition=braden.nutrition if braden else 3,
        braden_friction_shear=braden.friction_shear if braden else 2,
        mattress=(approved_plan(db, resident_id).mattress_type if approved_plan(db, resident_id) else "standard")
        or "standard",
        factors=factors,
        night_movements_per_hour=state.night_movements_per_hour,
    )


def plan_view(plan: Plan) -> PlanView:
    return PlanView(
        lying_limit_min=plan.lying_limit_min,
        sitting_limit_min=plan.sitting_limit_min,
        night_lying_limit_min=plan.night_lying_limit_min,
        continence_threshold=plan.continence_threshold,
        version=plan.version,
        mattress_type=plan.mattress_type or "standard",
        two_person=plan.two_person,
    )


def is_night(when: datetime, config: EngineConfig) -> bool:
    local = when.astimezone(ZoneInfo(config.facility_timezone))
    hour = local.hour
    start, end = config.night_start_hour, config.night_end_hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def limit_context(db: Session, resident_id: str, state: ResidentState, when: datetime, config: EngineConfig) -> tuple[Plan | None, LimitContext | None, ResidentRisk]:
    plan = approved_plan(db, resident_id)
    risk = resident_risk(db, resident_id, state, when)
    if plan is None:
        return None, None, risk
    position = state.position if state.position not in ("unknown", "out_of_room") else state.last_known
    ctx = LimitContext(
        position=position or "back",
        is_night=is_night(when, config),
        resident=risk,
        moist_minutes_24h=state.moist_minutes_24h or 0,
    )
    return plan, ctx, risk


def actionable_turn(budget: Budget, plan: PlanView, ctx: LimitContext, config: EngineConfig):
    """Like turn_due, but an area already unloading does not raise a new alert."""
    candidates = [area for area in ALL_AREAS if budget.relief_since[area] is None]
    if not candidates:
        return None, 0.0, False, 0.0
    ratios = {area: budget.load[area] / area_limit(area, plan, ctx, config) for area in candidates}
    worst = worst_area(ratios)
    cap = area_limit(worst, plan, ctx, config)
    minutes_left = cap - budget.load[worst]
    return worst, ratios[worst], minutes_left <= config.lead_min, minutes_left


def project_state(db: Session, state: ResidentState, now: datetime, config: EngineConfig) -> Budget:
    now = _aware(now)
    budget = budget_from_state(state)
    last = _aware(state.last_ts) if state.last_ts else now
    dt = (now - last).total_seconds() / 60.0
    if dt > 0:
        if state.position == "out_of_room":
            budget.step("out_of_room", now, dt, config)
        elif not state.camera_online:
            # Camera down: keep loading the last known in-bed position.
            budget.step("unknown", now, dt, config)
        else:
            budget.step(state.position or "unknown", now, dt, config)
        state.last_ts = now
        save_budget(state, budget)
    return budget


def _caregiver_open_tasks(db: Session, staff_id: str, now: datetime) -> int:
    """Open tasks for every resident this caregiver is assigned on the active shift."""
    shift = current_shift(db, now)
    if shift is None:
        return 0
    resident_ids = [
        row.resident_id
        for row in db.query(Assignment).filter(Assignment.shift_id == shift.id, Assignment.staff_id == staff_id)
    ]
    if not resident_ids:
        return 0
    return (
        db.query(Task)
        .filter(Task.resident_id.in_(resident_ids), Task.status == "open")
        .count()
    )


def _assigned_staff(db: Session, resident_id: str, now: datetime) -> str | None:
    row = (
        db.query(Assignment)
        .join(Shift, Shift.id == Assignment.shift_id)
        .filter(
            Assignment.resident_id == resident_id,
            Shift.starts_at <= now,
            Shift.ends_at >= now,
        )
        .first()
    )
    return row.staff_id if row else None


def _sent_this_hour(db: Session, staff_id: str, now: datetime) -> int:
    start = now.replace(minute=0, second=0, microsecond=0)
    return (
        db.query(Alert)
        .filter(Alert.staff_id == staff_id, Alert.created_at >= start, Alert.status != "deferred")
        .count()
    )


def _open_alert_for(db: Session, resident_id: str, kind: str) -> Alert | None:
    return (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == resident_id, Task.kind == kind, Alert.status.in_(OPEN_ALERT))
        .first()
    )


def ensure_turn_alert(db: Session, resident: Resident, state: ResidentState, budget: Budget, now: datetime, config: EngineConfig):
    plan, ctx, risk = limit_context(db, resident.id, state, now, config)
    if plan is None or ctx is None:
        return
    view = plan_view(plan)
    worst, ratio, due, minutes_left = actionable_turn(budget, view, ctx, config)
    if not due or worst is None:
        return
    if _open_alert_for(db, resident.id, "turn"):
        return
    steps = extra_risk_steps(risk)
    weight = risk_weight(steps, risk.braden_total)
    due_at = now + timedelta(minutes=max(minutes_left, 0))
    task = Task(
        resident_id=resident.id,
        kind="turn",
        due_at=due_at,
        window_min=int(config.merge_window_min),
        source="budget",
        status="open",
        priority=weight * ratio,
        detail={
            "worst_area": worst,
            "minutes_left": round(minutes_left, 1),
            "ratio": round(ratio, 3),
        },
    )
    db.add(task)
    db.flush()
    staff_id = _assigned_staff(db, resident.id, now)
    sent = _sent_this_hour(db, staff_id, now) if staff_id else 0
    if staff_id and not allow_send(sent, config):
        task.detail = {**(task.detail or {}), "alert_deferred": True}
        return
    inputs = {
        "worst_area": worst,
        "minutes_left": round(minutes_left, 1),
        "ratio": round(ratio, 3),
        "position": state.position,
        "load": {worst: round(budget.load[worst], 1)},
        "limit_min": round(area_limit(worst, view, ctx, config), 1),
        "extra_risk_steps": steps,
        "multiplier": config.risk_multiplier(steps),
        "pilot_mode": config.pilot_mode,
        "braden_total": risk.braden_total,
    }
    db.add(
        Alert(
            task_id=task.id,
            staff_id=staff_id,
            created_at=now,
            rule="turn_due:minutes_left<=lead_min",
            inputs=inputs,
            plan_version=plan.version,
            model_version=state.model_version,
            status="sent",
        )
    )


def _cold_start_bin_prob(interval_min: float, bin_min: float) -> float:
    """Choose a flat hazard whose median time-to-void matches the nurse interval."""
    bins = max(interval_min / bin_min, 1)
    # (1-p)^bins = 0.5
    return 1 - 0.5 ** (1 / bins)


def ensure_continence_task(db: Session, resident: Resident, state: ResidentState, now: datetime, config: EngineConfig):
    plan = approved_plan(db, resident.id)
    if plan is None:
        return
    if db.query(Task).filter(Task.resident_id == resident.id, Task.kind == "continence", Task.status == "open").first():
        return
    bin_min = config.continence_bin_min
    interval = float(plan.lying_limit_min)
    p = _cold_start_bin_prob(interval, bin_min)
    last = _aware(state.last_change_at) if state.last_change_at else now - timedelta(hours=2)
    elapsed = max((now - last).total_seconds() / 60.0, 0)
    n_bins = int(elapsed // bin_min) + 8
    starts = [last + timedelta(minutes=bin_min * (i + 1)) for i in range(n_bins)]
    probs = [p] * n_bins
    nurse_checks = []
    if config.learning_period:
        # Keep the nurse's fixed cadence, anchored on the last change.
        cursor = last + timedelta(minutes=interval)
        while cursor < now + timedelta(hours=8):
            nurse_checks.append(cursor)
            cursor += timedelta(minutes=interval)
    visits = schedule_from_hazard(
        bin_starts=starts,
        probs=probs,
        threshold=plan.continence_threshold,
        lead_min=config.continence_lead_min,
        nurse_checks=nurse_checks,
        learning_period=config.learning_period,
        last_change=last,
    )
    upcoming = [v for v in visits if v.due_at >= now - timedelta(minutes=5)]
    if not upcoming:
        return
    first = upcoming[0]
    w = first.wet_probability
    if w == 0:
        # Nurse check kept during learning. Estimate W at that time for the card.
        bins_until = max(int((first.due_at - last).total_seconds() / 60.0 / bin_min), 1)
        w = cumulative_wet([p] * bins_until)
    diuretic, _sedating = _medication_flags(db, resident.id, now, config)
    local = now.astimezone(ZoneInfo(config.facility_timezone))
    hours_since = max((now - last).total_seconds() / 3600.0, 0.0)
    features = continence_features(
        hours_since=hours_since,
        hour=local.hour + local.minute / 60.0,
        night=1.0 if is_night(now, config) else 0.0,
        meal=0.0,
        diuretic=1.0 if diuretic else 0.0,
        category=0.0,
    )
    db.add(
        Task(
            resident_id=resident.id,
            kind="continence",
            due_at=first.due_at,
            window_min=int(config.merge_window_min),
            source=first.source,
            status="open",
            priority=w,
            detail={
                "wet_probability": round(w, 2),
                "reason_code": first.reason_code,
                "reason_params": first.reason_params,
                "learning": config.learning_period,
                "last_change_at": last.isoformat(),
                "features": features,
                "diuretic_last_6h": bool(diuretic),
            },
        )
    )


def tick_alerts(db: Session, now: datetime, config: EngineConfig) -> None:
    rows = db.query(Alert).filter(Alert.status.in_(OPEN_ALERT)).all()
    for row in rows:
        state = AlertState(
            id=row.id,
            task_id=row.task_id or "",
            staff_id=row.staff_id or "",
            created_at=_aware(row.created_at),
            rule=row.rule,
            inputs=row.inputs or {},
            plan_version=row.plan_version or 0,
            model_version=row.model_version or "",
            status=row.status,
            accepted_at=_aware(row.accepted_at) if row.accepted_at else None,
            resolved_at=_aware(row.resolved_at) if row.resolved_at else None,
            charge_notified=row.charge_notified,
            resend_count=1 if row.charge_notified else 0,
        )
        advance_alert(state, now, config, saw_confirming_event=False)
        row.status = state.status
        row.charge_notified = state.charge_notified
        row.accepted_at = state.accepted_at
        row.resolved_at = state.resolved_at


def resolve_open_care(db: Session, resident_id: str, now: datetime, *, rule: str) -> int:
    alerts = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == resident_id, Alert.status.in_(OPEN_ALERT))
        .all()
    )
    count = 0
    for alert in alerts:
        task = db.get(Task, alert.task_id)
        if task and task.kind not in ("turn", "check", "continence", "care_visit"):
            continue
        alert.status = "resolved"
        alert.resolved_at = now
        if task and task.status == "open":
            task.status = "done"
            task.detail = {**(task.detail or {}), "resolved_by": rule}
        count += 1
    return count


def apply_event(db: Session, payload: dict) -> dict:
    config = cfg()
    ts = _aware(payload["ts"])
    kind = payload["kind"]
    if kind not in {
        "position",
        "movement",
        "presence_start",
        "presence_end",
        "bed_exit",
        "bathroom_trip",
        "bath_start",
        "bath_end",
        "turn",
        "care_visit",
        "camera_offline",
        "heartbeat",
        "stillness",
        "bed_return",
        "night_vitals",
        "device_offline",
    }:
        raise ValueError(f"unknown event kind {kind}")
    room = db.get(Room, payload.get("room_id")) if payload.get("room_id") else None
    resident = None
    if payload.get("resident_id"):
        resident = db.get(Resident, payload["resident_id"])
    if resident is None and room is not None:
        resident = db.query(Resident).filter(Resident.room_id == room.id).first()
    if resident is None:
        raise LookupError("resident not found for event")
    dedup = None
    if payload.get("device_id"):
        raw = payload.get("value") or {}
        dedup = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:16]
        priors = (
            db.query(Event)
            .filter(
                Event.device_id == payload["device_id"],
                Event.resident_id == resident.id,
                Event.kind == kind,
                Event.ts == ts,
            )
            .all()
        )
        prior = next((row for row in priors if (row.value or {}).get("dedup") == dedup), None)
        if prior is not None:
            state = db.get(ResidentState, resident.id)
            return {
                "event_id": prior.id,
                "resident_id": resident.id,
                "position": state.position if state else None,
                "load": state.load if state else {},
                "resolved_alerts": 0,
                "duplicate": True,
            }
    if room and not room.analysis_enabled and kind != "camera_offline":
        db.add(
            Event(
                room_id=room.id,
                resident_id=resident.id,
                ts=ts,
                kind=kind,
                value={"ignored": True, "reason": "analysis_disabled"},
                confidence=payload.get("confidence"),
                model_version=payload.get("model_version"),
                source=payload.get("source"),
                device_id=payload.get("device_id"),
            )
        )
        return {"ignored": True, "reason": "analysis_disabled"}

    value = dict(payload.get("value") or {})
    if dedup is not None:
        value["dedup"] = dedup
    source = payload.get("source")
    if source not in {None, "bed_sensor", "vision", "camera", "manual"}:
        raise ValueError(f"unknown event source {source}")
    fusion = None
    # A camera or vision event below the confidence gate is logged and does
    # not move the pressure clock. Events with no source keep the older path
    # so a witnessed turn still resolves.
    if source == "bed_sensor" and kind == "movement":
        movement = BedMovement(
            magnitude=float(value.get("magnitude") or 0),
            duration_s=float(value.get("duration_s") or 0),
        )
        fusion = classify_reposition(None, movement, config, has_vision=False)
        value["fusion"] = fusion
    elif kind in {"position", "turn"} and source in {"vision", "camera"}:
        vision = VisionChange(confidence=float(payload.get("confidence") or 0))
        bed = None
        if value.get("bed_magnitude") is not None:
            bed = BedMovement(magnitude=float(value["bed_magnitude"]), duration_s=float(value.get("bed_duration_s") or 0))
        cover = value.get("cover") or "unknown"
        if cover not in {"none", "sheet", "blanket", "unknown"}:
            raise ValueError(f"unknown cover {cover}")
        fusion = classify_reposition(vision, bed, config, has_vision=True, cover=cover)
        value["cover"] = cover
        value["fusion"] = fusion
        value["gate1"] = live_status()["status"]
        if cover != "none":
            value["fusion_reason"] = "cover_unvalidated"
            value["claim"] = "withheld"
        else:
            value["claim"] = "per_side_unvalidated"
    skip_clock = fusion is not None and not resets_timer(str(fusion), config)
    event = Event(
        room_id=resident.room_id,
        resident_id=resident.id,
        ts=ts,
        kind=kind,
        value=value,
        confidence=payload.get("confidence"),
        model_version=payload.get("model_version"),
        source=source,
        device_id=payload.get("device_id"),
    )
    db.add(event)
    state = db.get(ResidentState, resident.id)
    if state is None:
        state = ResidentState(
            resident_id=resident.id,
            load={area: 0.0 for area in ALL_AREAS},
            relief_since={area: None for area in ALL_AREAS},
            last_ts=ts,
            position="back",
            last_known="back",
        )
        db.add(state)
        db.flush()

    budget = project_state(db, state, ts, config)
    resolved = 0
    if kind == "position":
        new_pos = value.get("position", "unknown")
        if new_pos not in POSITIONS:
            raise ValueError(f"unknown position {new_pos}")
        if payload.get("confidence") is not None:
            state.confidence = float(payload["confidence"])
        if payload.get("model_version"):
            state.model_version = payload["model_version"]
        if skip_clock:
            state.settled = False
        else:
            previous = state.position
            persons = int(value.get("persons_in_zone", state.persons_in_zone or 1))
            state.persons_in_zone = persons
            state.position = new_pos
            if new_pos not in ("unknown", "out_of_room"):
                budget.last_known = new_pos
                state.last_known = new_pos
            state.settled = state.confidence >= config.verify_min_confidence and new_pos in {
                "back",
                "left",
                "right",
            }
            if persons >= 2 and new_pos != previous and new_pos in {"back", "left", "right", "sitting"}:
                resolved = resolve_open_care(db, resident.id, ts, rule="position_with_presence")
            elif persons == 1 and new_pos != previous and new_pos in {"back", "left", "right", "sitting", "out_of_bed"}:
                # Self-repositioning relieves the budget by the new position; the
                # open turn is resolved because the resident moved themselves.
                resolved = resolve_open_care(db, resident.id, ts, rule="self_reposition")
    elif kind == "turn":
        if not skip_clock:
            new_pos = value.get("to", state.position)
            state.position = new_pos
            state.persons_in_zone = max(state.persons_in_zone or 1, 2)
            if new_pos in POSITIONS and new_pos not in ("unknown", "out_of_room"):
                budget.last_known = new_pos
                state.last_known = new_pos
            if payload.get("confidence") is not None:
                state.confidence = float(payload["confidence"])
            resolved = resolve_open_care(db, resident.id, ts, rule="turn_event")
    elif kind == "care_visit":
        resolved = resolve_open_care(db, resident.id, ts, rule="care_visit")
        if value.get("includes_change"):
            previous_change = state.last_change_at
            state.last_change_at = ts
            db.add(
                ContinenceObs(
                    resident_id=resident.id,
                    kind="change",
                    ts=ts,
                    interval_start=_aware(previous_change) if previous_change else None,
                )
            )
    elif kind in {"camera_offline", "device_offline"}:
        state.camera_online = False
        state.camera_spectrum = "offline"
    elif kind == "heartbeat":
        spectrum = value.get("camera_spectrum")
        if spectrum == "color_rejected":
            state.camera_online = False
            state.camera_spectrum = "color_rejected"
        else:
            state.camera_online = True
            if spectrum:
                state.camera_spectrum = spectrum
    elif kind in {"night_vitals", "stillness", "bed_return"}:
        pass
    elif kind == "presence_start":
        state.persons_in_zone = int(value.get("persons", 2))
    elif kind == "presence_end":
        state.persons_in_zone = int(value.get("persons", 1))
    elif kind == "bed_exit":
        state.position = "out_of_bed"
        budget.last_known = state.last_known
    elif kind == "bathroom_trip":
        db.add(
            ContinenceObs(
                resident_id=resident.id,
                kind="bathroom_trip",
                ts=ts,
                interval_start=_aware(datetime.fromisoformat(value["left_at"])) if value.get("left_at") else None,
            )
        )
    elif kind == "movement":
        pass

    if not skip_clock and kind in {"position", "turn", "bed_exit"} and state.position in {
        "back",
        "left",
        "right",
        "sitting",
        "out_of_bed",
    }:
        # Zero-length step so areas that just lost load start their relief clock
        # without waiting for the next observation.
        budget.step(state.position, ts, 0, config)
    state.last_ts = ts
    save_budget(state, budget)
    _touch_device(db, payload, resident, ts, value, online=state.camera_online)
    if kind not in {"camera_offline", "device_offline", "night_vitals"} and state.camera_online:
        ensure_turn_alert(db, resident, state, budget, ts, config)
    if kind in {"care_visit", "bathroom_trip", "heartbeat", "position"} and not skip_clock:
        ensure_continence_task(db, resident, state, ts, config)
    tick_alerts(db, ts, config)
    db.flush()
    return {
        "event_id": event.id,
        "resident_id": resident.id,
        "position": state.position,
        "load": state.load,
        "resolved_alerts": resolved,
    }


def _touch_device(
    db: Session,
    payload: dict,
    resident: Resident,
    ts: datetime,
    value: dict,
    *,
    online: bool,
) -> None:
    """Record that the home computer heard this baby monitor. No image is stored."""
    device_id = payload.get("device_id")
    if not device_id:
        return
    device = db.get(Device, device_id)
    if device is None:
        device = Device(
            id=device_id,
            kind="camera",
            room_id=resident.room_id,
            resident_id=resident.id,
            installed_at=ts,
            config={"label": "infrared baby monitor", "mic": "off", "cloud": "off"},
            active=True,
        )
        db.add(device)
    device.last_seen = ts
    device.resident_id = device.resident_id or resident.id
    device.room_id = device.room_id or resident.room_id
    device.active = bool(online)
    stored = dict(device.config or {})
    stored["label"] = stored.get("label") or "infrared baby monitor"
    if "fps" in value:
        stored["fps"] = value["fps"]
    if "latency_ms" in value:
        stored["latency_ms"] = value["latency_ms"]
    spectrum = value.get("camera_spectrum") or value.get("spectrum")
    if spectrum:
        stored["spectrum"] = spectrum
    if payload.get("kind") in {"device_offline", "camera_offline"}:
        stored["spectrum"] = "offline"
        device.active = False
    device.config = stored


def current_shift(db: Session, now: datetime) -> Shift | None:
    return (
        db.query(Shift)
        .filter(Shift.starts_at <= now, Shift.ends_at >= now)
        .order_by(Shift.starts_at.desc())
        .first()
    )


def _prefs(db: Session, resident_id: str, approved_only: bool = True) -> list[dict]:
    query = db.query(Preference).filter(Preference.resident_id == resident_id)
    if approved_only:
        query = query.filter(Preference.approved_by.isnot(None))
    rows = []
    for pref in query.all():
        rows.append(
            {
                "id": pref.id,
                "category": pref.category,
                "code": pref.code,
                "params": pref.params or {},
                "source_type": pref.source_type,
                "source_excerpt": pref.source_excerpt,
                "source_date": pref.source_date.isoformat() if pref.source_date else None,
                "approved": pref.approved_by is not None,
            }
        )
    return rows


def how_to_codes(prefs: list[dict], *, two_person: bool) -> list[dict]:
    turning = [p for p in prefs if p["category"] == "turning" and p.get("code")]
    comfort = [p for p in prefs if p["category"] == "comfort" and p.get("code")]
    lines = turning + comfort
    if two_person and not any(p["code"] == "pref.turn.two_person" for p in lines):
        lines.append({"code": "pref.turn.two_person", "params": {}})
    return [{"code": p["code"], "params": p.get("params") or {}} for p in lines[:6]]


def refresh_assignment(db: Session, staff_id: str, now: datetime) -> list[Resident]:
    config = cfg()
    shift = current_shift(db, now)
    if shift is None:
        return []
    assignments = (
        db.query(Assignment)
        .filter(Assignment.shift_id == shift.id, Assignment.staff_id == staff_id)
        .all()
    )
    residents = []
    for assignment in assignments:
        resident = db.get(Resident, assignment.resident_id)
        state = db.get(ResidentState, resident.id)
        if state is None:
            continue
        if not state.camera_online and (now - _aware(state.last_ts)).total_seconds() > config.camera_offline_s:
            state.camera_online = False
        budget = project_state(db, state, now, config)
        if state.camera_online:
            ensure_turn_alert(db, resident, state, budget, now, config)
        ensure_continence_task(db, resident, state, now, config)
        _maybe_verify_checks(db, resident, state, config)
        residents.append(resident)
    tick_alerts(db, now, config)
    db.flush()
    return residents


def _maybe_verify_checks(db: Session, resident: Resident, state: ResidentState, config: EngineConfig) -> None:
    checks = (
        db.query(Task)
        .filter(Task.resident_id == resident.id, Task.kind == "check", Task.status == "open")
        .all()
    )
    open_alert = _open_alert_for(db, resident.id, "turn") is not None
    in_bed = state.position in {"back", "left", "right", "sitting"}
    for check in checks:
        ok = can_verify_check(
            camera_online=bool(state.camera_online),
            in_bed=in_bed,
            settled=bool(state.settled) and not open_alert,
            confidence=state.confidence or 0,
            open_alert=open_alert,
            min_confidence=config.verify_min_confidence,
        )
        if ok:
            check.status = "verified"
            check.detail = {**(check.detail or {}), "verified_by": "camera"}


def staff_can_see(db: Session, principal_id: str, role: str, resident_id: str, now: datetime) -> bool:
    if role in {"nurse", "charge_nurse", "admin"}:
        return db.get(Resident, resident_id) is not None
    shift = current_shift(db, now)
    if shift is None:
        return False
    return (
        db.query(Assignment)
        .filter(
            Assignment.shift_id == shift.id,
            Assignment.staff_id == principal_id,
            Assignment.resident_id == resident_id,
        )
        .first()
        is not None
    )


def build_shift(db: Session, staff: Staff, now: datetime) -> dict:
    now = _aware(now)
    residents = refresh_assignment(db, staff.id, now)
    shift = current_shift(db, now)
    config = cfg()
    tasks: list[SchedTask] = []
    resident_payload = {}
    resident_base: dict[str, float] = {}
    verified = 0
    queue_open = _caregiver_open_tasks(db, staff.id, now)
    per_task = config.caregiver_load_per_open_task
    for resident in residents:
        state = db.get(ResidentState, resident.id)
        room = db.get(Room, resident.room_id)
        plan, ctx, risk = limit_context(db, resident.id, state, now, config)
        budget = budget_from_state(state)
        allowed = has_signed(db, resident.id, "position_monitoring")
        continence_allowed = has_signed(db, resident.id, "continence_tracking")
        why = {"camera_online": state.camera_online} if allowed else {}
        if allowed:
            why["position"] = state.position
        if plan and ctx:
            view = plan_view(plan)
            worst, ratio, due, minutes_left = actionable_turn(budget, view, ctx, config)
            # Also report the spec turn_due so the trace matches the formula,
            # including an area that is already unloading.
            spec_worst, spec_ratio, _spec_due = turn_due(budget, view, ctx, config)
            why.update(
                {
                    "worst_area": worst or spec_worst,
                    "minutes_left": round(minutes_left, 1) if worst else None,
                    "ratio": round(ratio, 3) if worst else round(spec_ratio, 3),
                    "learning": config.learning_period,
                }
            )
        ensure_fixed_tasks(db, resident.id, now, config)
        open_tasks = (
            db.query(Task)
            .filter(Task.resident_id == resident.id, Task.status == "open")
            .all()
        )
        verified += (
            db.query(Task)
            .filter(Task.resident_id == resident.id, Task.status == "verified")
            .count()
        )
        prefs = _prefs(db, resident.id)
        steps = extra_risk_steps(risk) if plan else 0
        weight = risk_weight(steps, risk.braden_total)
        for task in open_tasks:
            detail = task.detail or {}
            if continence_allowed and detail.get("wet_probability") is not None:
                why["wet_probability"] = detail["wet_probability"]
                why["reason_code"] = detail.get("reason_code")
                why["reason_params"] = detail.get("reason_params")
                why["last_change_at"] = detail.get("last_change_at")
            base = task.priority or 0
            if task.kind == "turn" and why.get("ratio"):
                base = max(base, weight * why["ratio"])
            resident_base[resident.id] = max(resident_base.get(resident.id, 0.0), base)
            priority = with_caregiver_load(base, queue_open, per_task)
            tasks.append(
                SchedTask(
                    id=task.id,
                    resident_id=resident.id,
                    kind=task.kind,
                    due_at=_aware(task.due_at or now),
                    window_min=task.window_min or int(config.merge_window_min),
                    priority=priority,
                    room_order=room.hallway_order if room else 0,
                    source=task.source or "record",
                )
            )
        alerts = (
            db.query(Alert)
            .join(Task, Task.id == Alert.task_id)
            .filter(Task.resident_id == resident.id, Alert.status.in_(OPEN_ALERT), Alert.staff_id == staff.id)
            .all()
        )
        resident_payload[resident.id] = {
            "resident": resident,
            "room": room,
            "state": state,
            "prefs": prefs,
            "why": why,
            "two_person": bool(plan.two_person) if plan else False,
            "alerts": alerts,
            "plan": plan,
            "monitoring": monitoring_state(db, resident.id),
        }

    hidden = blackout_task_ids(db, tasks, now, config)
    if hidden:
        tasks = [task for task in tasks if task.id not in hidden]
    visits = merge_tasks(tasks, config.merge_window_min)
    for task in tasks:
        if task.merged_into:
            row = db.get(Task, task.id)
            if row and row.merged_into != task.merged_into:
                row.merged_into = task.merged_into
    items = []
    for visit in visits:
        info = resident_payload[visit.resident_id]
        resident = info["resident"]
        room = info["room"]
        why = dict(info["why"])
        alert = info["alerts"][0] if info["alerts"] else None
        items.append(
            {
                "visit_id": visit.id,
                "resident": {
                    "id": resident.id,
                    "preferred_name": resident.preferred_name,
                    "room": room.label if room else "",
                    "language": resident.language,
                },
                "tasks": visit.kinds,
                "due_at": visit.due_at.isoformat() if visit.due_at else None,
                "priority": round(visit.priority, 3),
                "base_priority": round(resident_base.get(resident.id, 0.0), 3),
                "queue_open": queue_open,
                "why": why,
                "how_to": how_to_codes(info["prefs"], two_person=info["two_person"]),
                "two_person": info["two_person"],
                "camera_online": info["state"].camera_online if info["monitoring"]["mode"] == "camera" else None,
                "position": info["state"].position if info["monitoring"]["mode"] == "camera" else None,
                "monitoring": info["monitoring"],
                "alert_id": alert.id if alert else None,
                "settled": bool(info["state"].settled) and alert is None,
            }
        )
    if len(items) >= 2:
        leader, follower = items[0], items[1]
        load_passed = leader["queue_open"] > follower["queue_open"] and leader["base_priority"] <= follower["base_priority"]
        code = "why.ahead.load" if load_passed else "why.ahead.pressure"
        items[0]["ahead"] = {
            "code": code,
            "params": {
                "name": follower["resident"]["preferred_name"],
                "count": leader["queue_open"],
            },
        }
    db.commit()
    resident_ids = [row.id for row in residents]
    merged_visits = sum(1 for task in tasks if task.merged_into)
    window_start = shift.starts_at if shift else now - timedelta(hours=8)
    window_end = shift.ends_at if shift else now
    saved = time_saved(count_verified(db, resident_ids, window_start, window_end), merged_visits, config)
    return {
        "shift_id": shift.id if shift else None,
        "language": staff.ui_language,
        "staff": {"id": staff.id, "display_name": staff.display_name, "role": staff.role},
        "items": items,
        "verified_checks": verified,
        "time_saved": saved,
        "chart_lines": recent_chart_lines(db, resident_ids, window_start),
        "generated_at": now.isoformat(),
    }


def resident_card(db: Session, resident_id: str, now: datetime) -> dict:
    refresh_resident_only(db, resident_id, now)
    resident = db.get(Resident, resident_id)
    state = db.get(ResidentState, resident_id)
    room = db.get(Room, resident.room_id)
    plan = approved_plan(db, resident_id)
    prefs = _prefs(db, resident_id)
    minutes_in_position = 0
    if state and state.last_ts:
        # Load on the current areas is the time in this position since relief.
        budget = budget_from_state(state)
        from turnwise.engine.budget import AREAS_BY_POSITION

        areas = AREAS_BY_POSITION.get(state.position, [])
        if areas:
            minutes_in_position = max(budget.load[a] for a in areas)
    allowed = has_signed(db, resident_id, "position_monitoring")
    card = {
        "resident": {
            "id": resident.id,
            "preferred_name": resident.preferred_name,
            "language": resident.language,
            "room": room.label if room else "",
        },
        "monitoring": monitoring_state(db, resident_id),
        "position": state.position if state and allowed else None,
        "minutes_in_position": round(minutes_in_position, 1) if allowed else None,
        "camera_online": state.camera_online if state and allowed else None,
        "preferences": prefs[:6],
        "how_to": how_to_codes(prefs, two_person=bool(plan.two_person) if plan else False),
        "two_person": bool(plan.two_person) if plan else False,
        "continence_threshold": plan.continence_threshold if plan else None,
        "camera_spectrum": state.camera_spectrum if state and allowed else None,
        "confidence": state.confidence if state and allowed else None,
        "model_version": state.model_version if state and allowed else None,
        "vitals": latest_vitals(db, resident_id),
        "diet": diet_for_resident(db, resident_id, now, cfg().facility_timezone)
        if has_signed(db, resident_id, "continence_tracking")
        else {"applies": False, "is_order": False, "withheld": "consent"},
        "chart_lines": recent_chart_lines(db, [resident_id], now - timedelta(days=7), limit=3) if allowed else [],
    }
    return card


def refresh_resident_only(db: Session, resident_id: str, now: datetime) -> None:
    config = cfg()
    resident = db.get(Resident, resident_id)
    state = db.get(ResidentState, resident_id)
    if resident and state:
        budget = project_state(db, state, now, config)
        if state.camera_online:
            ensure_turn_alert(db, resident, state, budget, now, config)
        ensure_continence_task(db, resident, state, now, config)
        _maybe_verify_checks(db, resident, state, config)
        db.commit()


def _source(rows: list, withheld: str | None = None) -> dict:
    return {"empty": len(rows) == 0, "withheld": withheld, "rows": rows}


def full_picture(db: Session, resident_id: str, now: datetime) -> dict:
    """One read for the chart, the risk flags, the doses, and the timeline."""
    now = _aware(now)
    config = cfg()
    refresh_resident_only(db, resident_id, now)
    resident = db.get(Resident, resident_id)
    state = db.get(ResidentState, resident_id)
    position_ok = has_signed(db, resident_id, "position_monitoring")
    continence_ok = has_signed(db, resident_id, "continence_tracking")
    skin_ok = has_signed(db, resident_id, "skin_capture")
    factors = (
        db.query(RiskFactor).filter(RiskFactor.resident_id == resident_id).order_by(RiskFactor.factor).all()
    )
    factor_rows = [
        {
            "factor": row.factor,
            "source": row.source,
            "confirmed": row.confirmed_by is not None,
        }
        for row in factors
    ]
    braden = latest_braden(db, resident_id)
    braden_row = None
    if braden is not None:
        braden_row = {
            "assessed_at": _aware(braden.assessed_at).isoformat(),
            "sensory": braden.sensory,
            "moisture": braden.moisture,
            "activity": braden.activity,
            "mobility": braden.mobility,
            "nutrition": braden.nutrition,
            "friction_shear": braden.friction_shear,
            "total": braden.total,
        }
    doses = (
        db.query(MedicationLog)
        .filter(MedicationLog.resident_id == resident_id)
        .order_by(MedicationLog.ts.desc())
        .all()
    )
    dose_rows = [
        {
            "id": row.id,
            "ts": _aware(row.ts).isoformat(),
            "medication_name": row.medication_name,
            "dose": row.dose,
            "route": row.route,
            "is_diuretic": bool(row.is_diuretic),
            "is_sedating": bool(row.is_sedating),
            "in_diuretic_window": bool(row.is_diuretic)
            and dose_in_window(_aware(row.ts), now, config.diuretic_window_hours),
            "in_sedating_window": bool(row.is_sedating)
            and dose_in_window(_aware(row.ts), now, config.sedating_window_hours),
        }
        for row in doses
    ]
    risk = resident_risk(db, resident_id, state, now) if state else ResidentRisk()
    steps = extra_risk_steps(risk)
    diuretic, _sedating = _medication_flags(db, resident_id, now, config)
    last = _aware(state.last_change_at) if state and state.last_change_at else now
    local = now.astimezone(ZoneInfo(config.facility_timezone))
    features = continence_features(
        hours_since=max((now - last).total_seconds() / 3600.0, 0.0),
        hour=local.hour + local.minute / 60.0,
        night=1.0 if is_night(now, config) else 0.0,
        meal=0.0,
        diuretic=1.0 if diuretic else 0.0,
        category=0.0,
    )
    camera_kinds = {"position", "movement", "presence", "bed_exit", "bed_return", "stillness"}
    events = (
        db.query(Event).filter(Event.resident_id == resident_id).order_by(Event.ts.desc()).limit(40).all()
    )
    if position_ok:
        event_rows = [
            {
                "ts": _aware(row.ts).isoformat(),
                "kind": row.kind,
                "value": row.value,
            }
            for row in events
        ]
        event_source = _source(event_rows)
    else:
        kept = [row for row in events if row.kind not in camera_kinds]
        event_rows = [
            {"ts": _aware(row.ts).isoformat(), "kind": row.kind, "value": row.value} for row in kept
        ]
        event_source = _source(event_rows, "consent")
    if continence_ok:
        obs = (
            db.query(ContinenceObs)
            .filter(ContinenceObs.resident_id == resident_id)
            .order_by(ContinenceObs.ts.desc())
            .limit(20)
            .all()
        )
        obs_rows = [{"ts": _aware(row.ts).isoformat(), "kind": row.kind} for row in obs]
        obs_source = _source(obs_rows)
    else:
        obs_rows = []
        obs_source = _source([], "consent")
    if skin_ok:
        captures = (
            db.query(SkinCapture)
            .filter(SkinCapture.resident_id == resident_id)
            .order_by(SkinCapture.ts.desc())
            .limit(20)
            .all()
        )
        # shown_to_staff stays false. The flag is not returned.
        skin_rows = [
            {
                "ts": _aware(row.ts).isoformat(),
                "area": row.area,
                "shown_to_staff": False,
            }
            for row in captures
        ]
        skin_source = _source(skin_rows)
    else:
        skin_rows = []
        skin_source = _source([], "consent")
    vitals = (
        db.query(MorningVital)
        .filter(MorningVital.resident_id == resident_id)
        .order_by(MorningVital.recorded_at.desc())
        .limit(7)
        .all()
    )
    vital_rows = [
        {
            "ts": _aware(row.recorded_at).isoformat(),
            "systolic": row.systolic,
            "diastolic": row.diastolic,
            "pulse": row.pulse,
            "temp_c": row.temp_c,
            "spo2": row.spo2,
            "weight_kg": row.weight_kg,
            "source": row.source,
        }
        for row in vitals
    ]
    meals = (
        db.query(MealLog)
        .filter(MealLog.resident_id == resident_id)
        .order_by(MealLog.ts.desc())
        .limit(20)
        .all()
    )
    meal_rows = [
        {
            "ts": _aware(row.ts).isoformat(),
            "meal_type": row.meal_type,
            "items_text": row.items_text,
            "percent_eaten": row.percent_eaten,
        }
        for row in meals
    ]
    items = []
    for row in event_rows:
        items.append({"ts": row["ts"], "kind": row["kind"], "source": "event"})
    for row in obs_rows:
        items.append({"ts": row["ts"], "kind": row["kind"], "source": "continence"})
    for row in skin_rows:
        items.append({"ts": row["ts"], "kind": "skin_capture", "source": "skin", "area": row["area"]})
    for row in vital_rows:
        items.append({"ts": row["ts"], "kind": "vitals", "source": "vitals"})
    for row in dose_rows:
        items.append({"ts": row["ts"], "kind": "medication", "source": "medication", "name": row["medication_name"]})
    for row in meal_rows:
        items.append({"ts": row["ts"], "kind": "meal", "source": "meals", "meal_type": row["meal_type"]})
    items.sort(key=lambda row: row["ts"], reverse=True)
    feature_block = (
        {
            "empty": False,
            "withheld": None,
            "names": list(FEATURE_NAMES),
            "values": features,
            "diuretic": features[8],
        }
        if continence_ok
        else {"empty": True, "withheld": "consent", "names": list(FEATURE_NAMES), "values": None, "diuretic": None}
    )
    return {
        "resident_id": resident_id,
        "name": resident.preferred_name if resident else None,
        "risk_factors": _source(factor_rows),
        "braden": {"empty": braden_row is None, "withheld": None, "rows": [braden_row] if braden_row else []},
        "medications": _source(dose_rows),
        "risk": {
            "extra_steps": steps,
            "weight": risk_weight(steps, risk.braden_total),
            "factors": sorted(risk.factors),
            "sedating_medication": "sedating_medication" in risk.factors,
        },
        "continence_features": feature_block,
        "timeline": {
            "empty": len(items) == 0,
            "sources": {
                "events": event_source,
                "continence": obs_source,
                "skin_captures": skin_source,
                "vitals": _source(vital_rows),
                "medications": _source(dose_rows),
                "meals": _source(meal_rows),
            },
            "items": items[:40],
        },
    }


def history(db: Session, resident_id: str, days: int, now: datetime) -> dict:
    start = now - timedelta(days=days)
    events = (
        db.query(Event)
        .filter(Event.resident_id == resident_id, Event.ts >= start)
        .order_by(Event.ts.desc())
        .limit(400)
        .all()
    )
    alerts = (
        db.query(Alert)
        .join(Task, Task.id == Alert.task_id)
        .filter(Task.resident_id == resident_id, Alert.created_at >= start)
        .all()
    )
    tasks = (
        db.query(Task)
        .filter(Task.resident_id == resident_id, Task.due_at >= start)
        .order_by(Task.due_at.desc())
        .all()
    )
    return {
        "resident_id": resident_id,
        "days": days,
        "events": [
            {
                "id": event.id,
                "ts": _aware(event.ts).isoformat(),
                "kind": event.kind,
                "value": event.value,
                "confidence": event.confidence,
                "model_version": event.model_version,
            }
            for event in events
        ],
        "alerts": [
            {
                "id": alert.id,
                "created_at": _aware(alert.created_at).isoformat(),
                "rule": alert.rule,
                "inputs": alert.inputs,
                "plan_version": alert.plan_version,
                "model_version": alert.model_version,
                "status": alert.status,
                "accepted_at": _aware(alert.accepted_at).isoformat() if alert.accepted_at else None,
                "resolved_at": _aware(alert.resolved_at).isoformat() if alert.resolved_at else None,
            }
            for alert in alerts
        ],
        "tasks": [
            {
                "id": task.id,
                "kind": task.kind,
                "due_at": _aware(task.due_at).isoformat() if task.due_at else None,
                "status": task.status,
                "source": task.source,
                "detail": task.detail,
            }
            for task in tasks
        ],
    }


def continence_view(db: Session, resident_id: str, now: datetime) -> dict:
    refresh_resident_only(db, resident_id, now)
    state = db.get(ResidentState, resident_id)
    plan = approved_plan(db, resident_id)
    tasks = (
        db.query(Task)
        .filter(Task.resident_id == resident_id, Task.kind == "continence", Task.status == "open")
        .all()
    )
    obs = (
        db.query(ContinenceObs)
        .filter(ContinenceObs.resident_id == resident_id)
        .order_by(ContinenceObs.ts.desc())
        .limit(20)
        .all()
    )
    return {
        "resident_id": resident_id,
        "threshold": plan.continence_threshold if plan else None,
        "learning": cfg().learning_period,
        "last_change_at": _aware(state.last_change_at).isoformat() if state and state.last_change_at else None,
        "windows": [
            {
                "due_at": _aware(task.due_at).isoformat() if task.due_at else None,
                "source": task.source,
                "detail": task.detail,
            }
            for task in tasks
        ],
        "observations": [
            {"kind": row.kind, "ts": _aware(row.ts).isoformat()} for row in obs
        ],
    }


def approve_plan(db: Session, plan_id: str, staff_id: str, body: dict, now: datetime) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise LookupError("plan not found")
    suggestion = plan.suggestion or {}
    if suggestion.get("effect") == "loosen":
        raise PermissionError("a model suggestion may not loosen a limit; a nurse must set that directly")
    if body.get("lying_limit_min") is not None:
        plan.lying_limit_min = int(body["lying_limit_min"])
    if body.get("sitting_limit_min") is not None:
        plan.sitting_limit_min = int(body["sitting_limit_min"])
    if "night_lying_limit_min" in body:
        raw = body["night_lying_limit_min"]
        plan.night_lying_limit_min = int(raw) if raw else None
    if body.get("continence_threshold") is not None:
        plan.continence_threshold = float(body["continence_threshold"])
    if body.get("mattress_type"):
        plan.mattress_type = body["mattress_type"]
    if body.get("two_person") is not None:
        plan.two_person = bool(body["two_person"])
    if not body.get("reason"):
        raise ValueError("a reason is required")
    plan.reason = body["reason"]
    plan.status = "approved"
    plan.approved_by = staff_id
    plan.approved_at = now
    previous = (
        db.query(Plan)
        .filter(
            Plan.resident_id == plan.resident_id,
            Plan.status == "approved",
            Plan.id != plan.id,
        )
        .all()
    )
    for old in previous:
        old.status = "retired"
    audit(db, staff_id, "plan.approve", "plan", plan.id, {"version": plan.version, "reason": plan.reason})
    db.commit()
    return plan


def record_override(db: Session, staff_id: str, target_type: str, target_id: str, reason: str, now: datetime) -> Override:
    row = Override(target_type=target_type, target_id=target_id, by_staff=staff_id, reason=reason, ts=now)
    db.add(row)
    audit(db, staff_id, "override", target_type, target_id, {"reason": reason})
    db.commit()
    return row
