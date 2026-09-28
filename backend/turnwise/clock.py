"""Care clock. One loop in this process, off the request path.

It recomputes each resident from stored timestamps, opens an alert when a
limit is inside the lead window, resends at the accept threshold, and
escalates at the resolve threshold. Restarting it is safe: an open alert is
not opened again. Run the API with one worker so two clocks do not race.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timezone

from turnwise.config import load_config

_LOCK = threading.Lock()
_STATE: dict[str, str | int | None] = {"last_tick_at": None, "last_tick_duration_ms": None}


def status() -> dict:
    return {
        "last_tick_at": _STATE["last_tick_at"],
        "last_tick_duration_ms": _STATE["last_tick_duration_ms"],
    }


def interval_seconds() -> float:
    return float(load_config().care_clock_s)


def clock_enabled() -> bool:
    raw = os.environ.get("SOMACARE_CARE_CLOCK", os.environ.get("TURNWISE_CARE_CLOCK"))
    if raw is not None:
        return raw == "1"
    return "pytest" not in sys.modules


def tick(now: datetime | None = None) -> dict:
    """One pass. A second overlapping pass in this process is skipped."""
    if not _LOCK.acquire(blocking=False):
        return status()
    try:
        started = time.perf_counter()
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        from turnwise.careflow import refresh_resident_only, tick_alerts
        from turnwise.db import SessionLocal
        from turnwise.models import Resident
        from turnwise.schedule import ensure_fixed_tasks

        if SessionLocal is None:
            return status()
        config = load_config()
        db = SessionLocal()
        try:
            residents = db.query(Resident).all()
            for resident in residents:
                refresh_resident_only(db, resident.id, moment)
            for resident in residents:
                ensure_fixed_tasks(db, resident.id, moment, config)
            tick_alerts(db, moment, config)
            db.commit()
        finally:
            db.close()
        _STATE["last_tick_at"] = moment.isoformat()
        _STATE["last_tick_duration_ms"] = int((time.perf_counter() - started) * 1000)
        return status()
    finally:
        _LOCK.release()
