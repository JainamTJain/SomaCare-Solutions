"""Server-sent events for one staff member's unit.

The payload is the current resident status and open alerts. The care clock
writes those rows. This endpoint only reads them.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from turnwise.consent import monitoring_state
from turnwise.models import Alert, Assignment, Resident, ResidentState, Shift, Task


def _residents_for(db: Session, staff_id: str, role: str) -> list[Resident]:
    if role == "cna":
        shift = db.query(Shift).order_by(Shift.starts_at.desc()).first()
        if shift is None:
            return []
        ids = [
            row.resident_id
            for row in db.query(Assignment)
            .filter(Assignment.shift_id == shift.id, Assignment.staff_id == staff_id)
            .all()
        ]
        if not ids:
            return []
        return db.query(Resident).filter(Resident.id.in_(ids)).order_by(Resident.preferred_name).all()
    return db.query(Resident).order_by(Resident.preferred_name).all()


def snapshot(db: Session, staff_id: str, role: str) -> dict:
    rows = []
    for resident in _residents_for(db, staff_id, role):
        state = db.get(ResidentState, resident.id)
        watch = monitoring_state(db, resident.id)
        alerts = (
            db.query(Alert)
            .join(Task, Task.id == Alert.task_id)
            .filter(Task.resident_id == resident.id, Alert.status.in_(("sent", "accepted", "passed", "escalated")))
            .all()
        )
        allowed = watch["mode"] == "camera"
        rows.append(
            {
                "resident_id": resident.id,
                "name": resident.preferred_name,
                "monitoring": watch,
                "position": state.position if state and allowed else None,
                "camera_online": state.camera_online if state and allowed else None,
                "alerts": [{"id": alert.id, "status": alert.status, "rule": alert.rule} for alert in alerts],
            }
        )
    return {"role": role, "residents": rows}


def format_sse(payload: dict) -> str:
    return f"event: update\ndata: {json.dumps(payload, sort_keys=True)}\n\n"
