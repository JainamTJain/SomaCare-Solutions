"""Nurse-approved fixed checks and blackout windows.

A new edit is a new version. The previous row is left as it was.
The scheduler reads only the newest approved version.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from turnwise.config import EngineConfig
from turnwise.engine.scheduler import SchedTask
from turnwise.models import Alert, ScheduleTemplate, Task


def _parse_hhmm(value: str) -> int:
    hour, minute = value.split(":")
    hour_i, minute_i = int(hour), int(minute)
    if hour_i < 0 or hour_i > 23 or minute_i < 0 or minute_i > 59:
        raise ValueError(value)
    return hour_i * 60 + minute_i


def _covers(window: dict, minute: int) -> bool:
    start = _parse_hhmm(window["start"])
    end = _parse_hhmm(window["end"])
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def _local_minute(now: datetime, config: EngineConfig) -> int:
    local = now.astimezone(ZoneInfo(config.facility_timezone))
    return local.hour * 60 + local.minute


def active_template(db: Session, resident_id: str) -> ScheduleTemplate | None:
    return (
        db.query(ScheduleTemplate)
        .filter(ScheduleTemplate.resident_id == resident_id, ScheduleTemplate.status == "approved")
        .order_by(ScheduleTemplate.version.desc())
        .first()
    )


def ensure_fixed_tasks(db: Session, resident_id: str, now: datetime, config: EngineConfig) -> None:
    """Open a fixed check while its window contains `now`. Budget alerts are separate."""
    template = active_template(db, resident_id)
    if template is None:
        return
    minute = _local_minute(now, config)
    local = now.astimezone(ZoneInfo(config.facility_timezone))
    for window in template.windows or []:
        if window.get("kind") != "fixed" or not _covers(window, minute):
            continue
        label = window.get("label") or "fixed check"
        existing = (
            db.query(Task)
            .filter(Task.resident_id == resident_id, Task.kind == "fixed", Task.status == "open")
            .all()
        )
        if any((row.detail or {}).get("label") == label for row in existing):
            continue
        start = _parse_hhmm(window["start"])
        due = local.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
        db.add(
            Task(
                resident_id=resident_id,
                kind="fixed",
                due_at=due.astimezone(timezone.utc),
                window_min=int(config.merge_window_min),
                source="schedule",
                status="open",
                priority=0.4,
                detail={"label": label, "fixed": True, "schedule_version": template.version},
            )
        )
    db.flush()


def blackout_task_ids(db: Session, tasks: list[SchedTask], now: datetime, config: EngineConfig) -> set[str]:
    """Hide a non-urgent check inside a blackout. An escalated alert stays."""
    minute = _local_minute(now, config)
    hidden: set[str] = set()
    templates: dict[str, ScheduleTemplate | None] = {}
    for task in tasks:
        if task.kind != "check":
            continue
        if task.resident_id not in templates:
            templates[task.resident_id] = active_template(db, task.resident_id)
        template = templates[task.resident_id]
        if template is None:
            continue
        covered = any(
            window.get("kind") == "blackout" and _covers(window, minute) for window in (template.windows or [])
        )
        if not covered:
            continue
        escalated = (
            db.query(Alert)
            .filter(Alert.task_id == task.id, Alert.status == "escalated")
            .first()
        )
        if escalated is not None:
            continue
        hidden.add(task.id)
    return hidden
