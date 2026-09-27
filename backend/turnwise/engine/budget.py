"""Pressure budget per body area.

A minute on a position loads the areas that bear weight in that position.
An area returns to zero only after it has been fully unloaded for `relief_min`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

AREAS_BY_POSITION = {
    "back": ["sacrum", "heels", "occiput"],
    "left": ["left_hip", "left_shoulder"],
    "right": ["right_hip", "right_shoulder"],
    "sitting": ["ischium", "sacrum"],
    "out_of_bed": [],  # standing or walking in the room relieves every area
}
ALL_AREAS = sorted({a for v in AREAS_BY_POSITION.values() for a in v})
MOISTURE_AREAS = {"sacrum", "ischium"}
# When two areas share a ratio, name the one nurses treat first.
CLINICAL_RANK = {
    "sacrum": 0,
    "ischium": 1,
    "heels": 2,
    "occiput": 3,
    "left_hip": 4,
    "right_hip": 5,
    "left_shoulder": 6,
    "right_shoulder": 7,
}


def worst_area(ratios: dict[str, float]) -> str:
    return max(ratios, key=lambda area: (ratios[area], -CLINICAL_RANK[area]))


class PilotModeError(RuntimeError):
    """Camera and model data may only tighten limits while pilot mode is on."""


def minutes_between(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / 60.0


@dataclass
class Budget:
    load: dict[str, float] = field(default_factory=lambda: {a: 0.0 for a in ALL_AREAS})
    relief_since: dict[str, Optional[datetime]] = field(
        default_factory=lambda: {a: None for a in ALL_AREAS}
    )
    last_known: str = "back"

    def step(self, position: str, ts: datetime, dt_min: float, cfg) -> None:
        if dt_min < 0:
            raise ValueError("dt_min must be >= 0")
        if position in ("unknown", "out_of_room"):
            # Conservative: keep loading the last known position while in bed
            # and unseen. Freeze (no load, no relief) when out of the room.
            if position == "out_of_room":
                return
            position = self.last_known
        if position not in AREAS_BY_POSITION:
            raise ValueError(f"unknown position {position}")
        self.last_known = position
        loaded = set(AREAS_BY_POSITION[position])
        for area in ALL_AREAS:
            if area in loaded:
                self.load[area] += dt_min
                self.relief_since[area] = None
            else:
                if self.relief_since[area] is None:
                    self.relief_since[area] = ts
                if minutes_between(ts, self.relief_since[area]) >= cfg.relief_min:
                    self.load[area] = 0.0


@dataclass
class PlanView:
    lying_limit_min: float
    sitting_limit_min: float
    night_lying_limit_min: float | None = None
    continence_threshold: float = 0.6
    version: int = 1
    mattress_type: str = "standard"
    two_person: bool = False


@dataclass
class LimitContext:
    position: str
    is_night: bool
    resident: object
    moist_minutes_24h: float = 0.0
    nurse_override_floor_min: float | None = None


def limit(area: str, plan: PlanView, ctx: LimitContext, cfg) -> float:
    """Nurse-approved base, tightened by version-1 risk steps. Never loosened in pilot mode."""
    if ctx.position == "sitting":
        base = float(plan.sitting_limit_min)
    elif ctx.is_night and plan.night_lying_limit_min:
        base = float(plan.night_lying_limit_min)
    else:
        base = float(plan.lying_limit_min)

    from turnwise.engine.risk_rules import extra_risk_steps

    steps = extra_risk_steps(ctx.resident)
    multiplier = cfg.risk_multiplier(steps)
    if area in MOISTURE_AREAS and ctx.moist_minutes_24h > cfg.moist_threshold_min:
        multiplier *= cfg.m_moisture
    if cfg.pilot_mode and multiplier > 1.0:
        raise PilotModeError(
            "camera and model data may only tighten limits in pilot mode"
        )
    floor = (
        ctx.nurse_override_floor_min
        if ctx.nurse_override_floor_min is not None
        else cfg.limit_floor_min
    )
    return max(base * multiplier, floor)


def turn_due(budget: Budget, plan: PlanView, ctx: LimitContext, cfg):
    ratios = {area: budget.load[area] / limit(area, plan, ctx, cfg) for area in ALL_AREAS}
    worst = worst_area(ratios)
    area_limit = limit(worst, plan, ctx, cfg)
    minutes_left = area_limit - budget.load[worst]
    return worst, ratios[worst], minutes_left <= cfg.lead_min
