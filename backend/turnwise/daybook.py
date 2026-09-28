"""Shift extras that reuse work the facility already does.

Time saved counts camera-verified checks and merged visits. Morning vitals
are the chart they already take. The diet map is a pattern for bedridden
residents, computed from turns and changes already recorded. It is not an
order and it does not change a limit.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from turnwise.config import EngineConfig, load_config
from turnwise.models import BradenAssessment, ContinenceObs, Event, MorningVital, Task


def time_saved(verified_checks: int, merged_visits: int, config: EngineConfig | None = None) -> dict:
    config = config or load_config()
    minutes = int(
        round(
            verified_checks * config.minutes_saved_per_verified_check
            + merged_visits * config.minutes_saved_per_merged_visit
        )
    )
    return {
        "minutes": minutes,
        "hours": minutes // 60,
        "remainder_min": minutes % 60,
        "verified_checks": verified_checks,
        "merged_visits": merged_visits,
        "per_verified_check_min": config.minutes_saved_per_verified_check,
        "per_merged_visit_min": config.minutes_saved_per_merged_visit,
    }


def count_verified(db: Session, resident_ids: list[str], start: datetime, end: datetime) -> int:
    if not resident_ids:
        return 0
    return (
        db.query(Task)
        .filter(
            Task.resident_id.in_(resident_ids),
            Task.status == "verified",
            Task.due_at >= start,
            Task.due_at <= end,
        )
        .count()
    )


def _hour_block(moment: datetime, tz: ZoneInfo) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    hour = moment.astimezone(tz).hour
    if hour < 6:
        return "night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def diet_pattern(
    wet_times: list[datetime],
    turn_times: list[datetime],
    *,
    bedridden: bool,
    tz_name: str = "America/Los_Angeles",
) -> dict:
    """Cluster existing changes and turns. Never writes a diet order."""
    empty = {"night": 0, "morning": 0, "afternoon": 0, "evening": 0}
    if not bedridden:
        return {
            "applies": False,
            "is_order": False,
            "status": "not_bedridden",
            "code": "diet.skip",
            "wet_blocks": empty,
            "turn_blocks": empty,
        }
    tz = ZoneInfo(tz_name)
    wet_blocks = dict(empty)
    turn_blocks = dict(empty)
    for moment in wet_times:
        wet_blocks[_hour_block(moment, tz)] += 1
    for moment in turn_times:
        turn_blocks[_hour_block(moment, tz)] += 1
    code = "diet.quiet"
    if wet_blocks["evening"] >= 2 and wet_blocks["evening"] >= wet_blocks["night"]:
        code = "diet.wet_evening"
    return {
        "applies": True,
        "is_order": False,
        "status": "pilot",
        "code": code,
        "wet_blocks": wet_blocks,
        "turn_blocks": turn_blocks,
    }


def is_bedridden(activity: int | None, mobility: int | None) -> bool:
    """Braden activity and mobility of 1 or 2: bedfast or very limited."""
    if activity is None or mobility is None:
        return False
    return activity <= 2 and mobility <= 2


def chart_line(kind: str, value: dict | None, model_version: str | None) -> dict | None:
    value = value or {}
    model = model_version or ""
    if kind == "position":
        return {
            "code": "chart.position",
            "params": {"position": str(value.get("position") or "unknown"), "model": model},
        }
    if kind == "turn":
        side = value.get("to") or value.get("position") or "unknown"
        return {"code": "chart.turn", "params": {"to": str(side), "model": model}}
    if kind in {"care_visit", "continence"}:
        return {"code": "chart.change", "params": {}}
    return None


def latest_vitals(db: Session, resident_id: str) -> dict | None:
    row = (
        db.query(MorningVital)
        .filter(MorningVital.resident_id == resident_id)
        .order_by(MorningVital.recorded_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "recorded_on": row.recorded_on.isoformat() if row.recorded_on else None,
        "systolic": row.systolic,
        "diastolic": row.diastolic,
        "pulse": row.pulse,
        "temp_c": row.temp_c,
        "spo2": row.spo2,
        "weight_kg": row.weight_kg,
        "source": row.source,
    }


def diet_for_resident(db: Session, resident_id: str, now: datetime, tz_name: str) -> dict:
    braden = (
        db.query(BradenAssessment)
        .filter(BradenAssessment.resident_id == resident_id)
        .order_by(BradenAssessment.assessed_at.desc())
        .first()
    )
    bed = is_bedridden(braden.activity if braden else None, braden.mobility if braden else None)
    start = now - timedelta(days=7)
    wets = [
        row.ts
        for row in db.query(ContinenceObs)
        .filter(
            ContinenceObs.resident_id == resident_id,
            ContinenceObs.kind == "wet",
            ContinenceObs.ts >= start,
        )
        .all()
        if row.ts is not None
    ]
    turns = [
        row.ts
        for row in db.query(Event)
        .filter(
            Event.resident_id == resident_id,
            Event.kind.in_(("position", "turn")),
            Event.ts >= start,
        )
        .all()
        if row.ts is not None
    ]
    pattern = diet_pattern(wets, turns, bedridden=bed, tz_name=tz_name)
    pattern["bedridden"] = bed
    return pattern


def recent_chart_lines(db: Session, resident_ids: list[str], start: datetime, limit: int = 8) -> list[dict]:
    if not resident_ids:
        return []
    events = (
        db.query(Event)
        .filter(Event.resident_id.in_(resident_ids), Event.ts >= start)
        .order_by(Event.ts.desc())
        .limit(40)
        .all()
    )
    lines = []
    for event in events:
        line = chart_line(event.kind, event.value, event.model_version)
        if line is None:
            continue
        moment = event.ts if event.ts.tzinfo else event.ts.replace(tzinfo=timezone.utc)
        lines.append({"ts": moment.isoformat(), "resident_id": event.resident_id, **line})
        if len(lines) >= limit:
            break
    return lines


def shift_ics(items: list[dict], staff_name: str) -> str:
    """The visits already on the shift, as a calendar file. No second list."""

    def esc(text: str) -> str:
        return (
            text.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;")
        )

    def stamp(moment: datetime) -> str:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SomaCare//Shift//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:SomaCare · {esc(staff_name)}",
    ]
    for item in items:
        if item.get("settled"):
            continue
        raw = item.get("due_at")
        if not raw:
            continue
        start = datetime.fromisoformat(raw)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = start + timedelta(minutes=15)
        resident = item.get("resident") or {}
        name = resident.get("preferred_name") or "Resident"
        room = resident.get("room") or ""
        tasks = ", ".join(item.get("tasks") or [])
        uid = item.get("visit_id") or f"{name}-{stamp(start)}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@somacare",
                f"DTSTAMP:{stamp(datetime.now(timezone.utc))}",
                f"DTSTART:{stamp(start)}",
                f"DTEND:{stamp(end)}",
                f"SUMMARY:{esc(name)} {esc(room)}".strip(),
                f"DESCRIPTION:{esc(tasks)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def morning_chart_time(now: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz)
    stamped = datetime.combine(local.date(), time(7, 30), tzinfo=tz)
    return stamped.astimezone(timezone.utc)
