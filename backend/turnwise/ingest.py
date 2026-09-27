"""File-based care-record import and export. CSV in, completed care out."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from turnwise.engine.budget import ALL_AREAS
from turnwise.models import (
    BradenAssessment,
    Facility,
    IngestBatch,
    Plan,
    Resident,
    ResidentState,
    Room,
    Task,
    Unit,
)


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def import_records(db: Session, files: dict[str, str]) -> dict:
    """files keys: residents, braden, schedules. Each value is CSV text."""
    blob = "\n".join(files.get(name, "") for name in ("residents", "braden", "schedules"))
    checksum = hashlib.sha256(blob.encode()).hexdigest()
    if db.query(IngestBatch).filter(IngestBatch.checksum == checksum).first():
        return {"status": "duplicate", "checksum": checksum}

    facility = db.query(Facility).first()
    if facility is None:
        facility = Facility(name="Imported Facility")
        db.add(facility)
        db.flush()
    unit = db.query(Unit).filter(Unit.facility_id == facility.id, Unit.name == "Imported").first()
    if unit is None:
        unit = Unit(facility_id=facility.id, name="Imported")
        db.add(unit)
        db.flush()

    created = {"residents": 0, "braden": 0, "schedules": 0}
    by_name: dict[str, Resident] = {}
    for row in _rows(files.get("residents", "")):
        name = row["preferred_name"].strip()
        label = row["room_label"].strip()
        room = (
            db.query(Room)
            .filter(Room.unit_id == unit.id, Room.label == label)
            .first()
        )
        if room is None:
            order = db.query(Room).filter(Room.unit_id == unit.id).count()
            room = Room(
                unit_id=unit.id,
                label=label,
                camera_class="none",
                analysis_enabled=False,
                hallway_order=order,
            )
            db.add(room)
            db.flush()
        resident = Resident(
            room_id=room.id,
            preferred_name=name,
            language=(row.get("language") or "en").strip(),
            consent_position=False,
        )
        db.add(resident)
        db.flush()
        db.add(
            ResidentState(
                resident_id=resident.id,
                load={area: 0.0 for area in ALL_AREAS},
                relief_since={area: None for area in ALL_AREAS},
                last_ts=datetime.now(timezone.utc),
                position="back",
                last_known="back",
                camera_online=False,
                settled=False,
            )
        )
        db.add(
            Plan(
                resident_id=resident.id,
                version=1,
                lying_limit_min=int(row.get("lying_limit_min") or 120),
                sitting_limit_min=int(row.get("sitting_limit_min") or 60),
                continence_threshold=float(row.get("continence_threshold") or 0.6),
                status="draft",
                reason="Imported from the care record. A nurse still has to approve it.",
            )
        )
        by_name[name] = resident
        created["residents"] += 1

    for row in _rows(files.get("braden", "")):
        resident = by_name.get(row["preferred_name"].strip())
        if resident is None:
            resident = (
                db.query(Resident).filter(Resident.preferred_name == row["preferred_name"].strip()).first()
            )
        if resident is None:
            continue
        assessed = row.get("assessed_at") or datetime.now(timezone.utc).isoformat()
        db.add(
            BradenAssessment(
                resident_id=resident.id,
                assessed_at=datetime.fromisoformat(assessed),
                sensory=int(row["sensory"]),
                moisture=int(row["moisture"]),
                activity=int(row["activity"]),
                mobility=int(row["mobility"]),
                nutrition=int(row["nutrition"]),
                friction_shear=int(row["friction_shear"]),
            )
        )
        created["braden"] += 1

    for row in _rows(files.get("schedules", "")):
        resident = by_name.get(row["preferred_name"].strip()) or (
            db.query(Resident).filter(Resident.preferred_name == row["preferred_name"].strip()).first()
        )
        if resident is None:
            continue
        db.add(
            Task(
                resident_id=resident.id,
                kind=row["kind"].strip(),
                due_at=datetime.fromisoformat(row["due_at"]),
                window_min=int(row.get("window_min") or 30),
                source="record",
                status="open",
                detail={"imported": True},
            )
        )
        created["schedules"] += 1

    db.add(IngestBatch(source_name="csv", checksum=checksum, summary=created))
    db.commit()
    return {"status": "imported", "checksum": checksum, **created}


def export_care(db: Session) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["resident", "room", "kind", "due_at", "status", "source"])
    rows = (
        db.query(Task, Resident, Room)
        .join(Resident, Resident.id == Task.resident_id)
        .join(Room, Room.id == Resident.room_id)
        .filter(Task.status.in_(["done", "verified"]))
        .all()
    )
    for task, resident, room in rows:
        writer.writerow(
            [
                resident.preferred_name,
                room.label,
                task.kind,
                task.due_at.isoformat() if task.due_at else "",
                task.status,
                task.source or "",
            ]
        )
    return buffer.getvalue()
