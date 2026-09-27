"""Engineer and director readings of the same hall.

The engineer board is the raw engine state: position, confidence, area
ratios, continence probability, and whether a visual check would pass.
The director board is the value a facility can defend. Hours saved are the
same walk-minutes as the CNA shift. Pressure ulcers prevented are not
estimated: this system does not contain an incident log.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from turnwise.careflow import (
    approved_plan,
    budget_from_state,
    current_shift,
    limit_context,
    plan_view,
    refresh_resident_only,
)
from turnwise.config import EngineConfig, load_config
from turnwise.daybook import time_saved
from turnwise.engine.budget import ALL_AREAS
from turnwise.engine.budget import limit as area_limit
from turnwise.engine.risk_rules import extra_risk_steps
from turnwise.engine.scheduler import SchedTask, can_verify_check, merge_tasks
from turnwise.models import Alert, Resident, ResidentState, Room, SkinAssessment, Task

IN_BED = {"back", "left", "right", "sitting"}
INJURY_FINDINGS = {"stage1", "stage2", "stage3", "stage4", "unstageable", "dtpi", "red"}


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def hall_rows(db: Session, now: datetime, config: EngineConfig | None = None) -> list[dict]:
    config = config or load_config()
    rows = []
    residents = db.query(Resident).all()
    for resident in residents:
        refresh_resident_only(db, resident.id, now)
        state = db.get(ResidentState, resident.id)
        room = db.get(Room, resident.room_id) if resident.room_id else None
        if state is None:
            continue
        plan, ctx, risk = limit_context(db, resident.id, state, now, config)
        budget = budget_from_state(state)
        steps = extra_risk_steps(risk) if plan else 0
        areas = []
        worst = None
        worst_ratio = None
        if plan and ctx:
            view = plan_view(plan)
            for area in ALL_AREAS:
                cap = area_limit(area, view, ctx, config)
                load = float(budget.load.get(area, 0.0))
                ratio = load / cap if cap else 0.0
                areas.append(
                    {
                        "area": area,
                        "load_min": round(load, 2),
                        "limit_min": round(cap, 2),
                        "ratio": round(ratio, 4),
                        "relief": budget.relief_since.get(area) is not None and load == 0,
                    }
                )
            worst = max(areas, key=lambda row: (row["ratio"], row["area"]))
            worst_ratio = worst["ratio"]
        confidence = float(state.confidence or 0)
        open_turn = (
            db.query(Alert)
            .join(Task, Task.id == Alert.task_id)
            .filter(
                Task.resident_id == resident.id,
                Task.kind == "turn",
                Alert.status.in_(("sent", "accepted", "passed", "escalated")),
            )
            .first()
        )
        in_bed = state.position in IN_BED
        settled = bool(state.settled) and open_turn is None
        check_ok = can_verify_check(
            camera_online=bool(state.camera_online),
            in_bed=in_bed,
            settled=settled,
            confidence=confidence,
            open_alert=open_turn is not None,
            min_confidence=config.verify_min_confidence,
        )
        blocked = []
        if not state.camera_online:
            blocked.append("camera_offline")
        if not in_bed:
            blocked.append("not_in_bed")
        if not state.settled:
            blocked.append("not_settled")
        if open_turn is not None:
            blocked.append("open_turn_alert")
        if confidence < config.verify_min_confidence:
            blocked.append("confidence_below_gate")
        continence = (
            db.query(Task)
            .filter(Task.resident_id == resident.id, Task.kind == "continence", Task.status == "open")
            .order_by(Task.due_at.asc())
            .first()
        )
        detail = (continence.detail or {}) if continence else {}
        wet = detail.get("wet_probability")
        threshold = plan.continence_threshold if plan else None
        rows.append(
            {
                "resident_id": resident.id,
                "name": resident.preferred_name,
                "room": room.label if room else "",
                "position": state.position,
                "last_known": state.last_known,
                "confidence": round(confidence, 4),
                "confidence_pct": round(confidence * 100, 1),
                "uncertainty_pct": round((1 - confidence) * 100, 1),
                "model_version": state.model_version,
                "camera_online": bool(state.camera_online),
                "camera_spectrum": state.camera_spectrum,
                "persons_in_zone": state.persons_in_zone,
                "settled": bool(state.settled),
                "areas": areas,
                "worst_area": worst["area"] if worst else None,
                "worst_ratio": worst_ratio,
                "inside_nurse_limit": worst_ratio is not None and worst_ratio < 1,
                "extra_risk_steps": steps,
                "risk_multiplier": config.risk_multiplier(steps) if plan else None,
                "braden_total": risk.braden_total,
                "continence": {
                    "wet_probability": wet,
                    "threshold": threshold,
                    "above_threshold": wet is not None and threshold is not None and wet >= threshold,
                    "learning": bool(detail.get("learning", config.learning_period)),
                    "reason_code": detail.get("reason_code"),
                    "due_at": _aware(continence.due_at).isoformat() if continence and continence.due_at else None,
                    "source": continence.source if continence else None,
                },
                "visual_check": {
                    "would_verify": check_ok,
                    "confidence_pct": round(confidence * 100, 1),
                    "uncertainty_pct": round((1 - confidence) * 100, 1),
                    "gate_pct": round(config.verify_min_confidence * 100, 1),
                    "blocked_by": [] if check_ok else blocked,
                },
                "open_alert": None
                if open_turn is None
                else {
                    "id": open_turn.id,
                    "rule": open_turn.rule,
                    "status": open_turn.status,
                    "inputs": open_turn.inputs,
                    "plan_version": open_turn.plan_version,
                    "model_version": open_turn.model_version,
                },
            }
        )
    rows.sort(key=lambda row: row["room"])
    return rows


def _saved_by_kind(db: Session, now: datetime, config: EngineConfig) -> dict:
    shift = current_shift(db, now)
    start = shift.starts_at if shift else now
    end = shift.ends_at if shift else now
    verified = (
        db.query(Task)
        .filter(Task.status == "verified", Task.due_at >= start, Task.due_at <= end)
        .all()
    )
    open_tasks = db.query(Task).filter(Task.status == "open").all()
    sched = []
    for task in open_tasks:
        room = db.get(Room, db.get(Resident, task.resident_id).room_id)
        sched.append(
            SchedTask(
                id=task.id,
                resident_id=task.resident_id,
                kind=task.kind,
                due_at=_aware(task.due_at or now),
                window_min=task.window_min or int(config.merge_window_min),
                priority=task.priority or 0,
                room_order=room.hallway_order if room else 0,
                source=task.source or "record",
            )
        )
    merge_tasks(sched, config.merge_window_min)
    merged = [task for task in sched if task.merged_into]
    kinds = {}
    for kind in ("turn", "continence", "check"):
        verified_n = sum(1 for task in verified if task.kind == kind)
        merged_n = sum(1 for task in merged if task.kind == kind)
        kinds[kind] = time_saved(verified_n, merged_n, config)
    total_minutes = sum(kinds[kind]["minutes"] for kind in kinds)
    return {"by_kind": kinds, "total_minutes": total_minutes, "total_hours": round(total_minutes / 60, 2)}


def engineer_board(db: Session, now: datetime) -> dict:
    config = load_config()
    rows = hall_rows(db, now, config)
    return {
        "generated_at": now.isoformat(),
        "pilot_mode": config.pilot_mode,
        "position_model": "position-v0.0.0-rules",
        "position_model_note": "Shoulder-hip rule. Not trained on SLP. Infrared frames only; color frames are rejected.",
        "verify_gate": config.verify_min_confidence,
        "residents": rows,
    }


def director_board(db: Session, now: datetime) -> dict:
    config = load_config()
    rows = hall_rows(db, now, config)
    saved = _saved_by_kind(db, now, config)
    shift = current_shift(db, now)
    start = shift.starts_at if shift else now
    injuries = (
        db.query(SkinAssessment)
        .filter(SkinAssessment.ts >= start, SkinAssessment.finding.in_(INJURY_FINDINGS))
        .count()
    )
    online = [row for row in rows if row["camera_online"] and row["camera_spectrum"] == "infrared"]
    above = [row for row in rows if row["continence"]["above_threshold"]]
    inside = [row for row in rows if row["inside_nurse_limit"]]
    over = [row for row in rows if row["worst_ratio"] is not None and row["worst_ratio"] >= 1]
    checks_pass = [row for row in rows if row["visual_check"]["would_verify"]]
    mean_uncertainty = (
        round(sum(row["uncertainty_pct"] for row in rows) / len(rows), 1) if rows else None
    )
    return {
        "generated_at": now.isoformat(),
        "facility": "Harbor House",
        "unit": "Night Hall",
        "residents": len(rows),
        "time_saved": {
            "total_minutes": saved["total_minutes"],
            "total_hours": saved["total_hours"],
            "turning": saved["by_kind"]["turn"],
            "incontinence": saved["by_kind"]["continence"],
            "visual_checks": saved["by_kind"]["check"],
            "per_verified_check_min": config.minutes_saved_per_verified_check,
            "per_merged_visit_min": config.minutes_saved_per_merged_visit,
        },
        "pressure_injury": {
            "ulcers_prevented": None,
            "ulcers_prevented_note": (
                "Not estimated. Sorety does not count prevented ulcers. "
                "There is no incident log in this system, and no model here is validated to predict one."
            ),
            "new_injuries_recorded_this_shift": injuries,
            "residents_inside_nurse_limit": len(inside),
            "residents_at_or_over_limit": len(over),
        },
        "cameras": {
            "infrared_online": len(online),
            "residents": len(rows),
            "mean_uncertainty_pct": mean_uncertainty,
        },
        "incontinence": {
            "above_nurse_threshold": len(above),
            "names": [row["name"] for row in above],
        },
        "visual_checks_passing": len(checks_pass),
        "closest_to_limit": sorted(
            [row for row in rows if row["worst_ratio"] is not None],
            key=lambda row: row["worst_ratio"],
            reverse=True,
        )[:3],
    }
