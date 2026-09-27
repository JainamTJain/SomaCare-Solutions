"""Version-1 pressure-injury risk. Deterministic rules for the pilot.

Version 2 (MIMIC-IV) is not deployed to residents. It may only inform these
weights after it beats a Braden-only baseline on a temporal split.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def braden_band(total: int) -> str:
    if total <= 9:
        return "very_high"
    if total <= 12:
        return "high"
    if total <= 14:
        return "moderate"
    if total <= 18:
        return "mild"
    return "none"


@dataclass
class ResidentRisk:
    braden_total: int = 15
    braden_nutrition: int = 3
    braden_friction_shear: int = 2
    mattress: str = "standard"
    stage2_plus_now: bool = False
    red_flag_last_7d: bool = False
    factors: set[str] = field(default_factory=set)
    night_movements_per_hour: float | None = None

    def confirmed(self, name: str) -> bool:
        return name in self.factors


def eligible_for_3h(r: ResidentRisk) -> bool:
    """A suggestion for the nurse. The engine never applies this by itself,
    because lengthening a limit would loosen care, which pilot mode forbids."""
    return (
        10 <= r.braden_total <= 14
        and r.mattress == "high_density_foam"
        and not r.stage2_plus_now
        and not r.red_flag_last_7d
    )


def extra_risk_steps(r: ResidentRisk) -> int:
    steps = 0
    steps += 1 if r.confirmed("prior_injury") else 0
    steps += 1 if r.confirmed("diabetes") or r.confirmed("vascular") else 0
    steps += 1 if r.confirmed("weight_loss") or r.braden_nutrition <= 2 else 0
    steps += 1 if r.braden_friction_shear == 1 else 0
    # Camera: median self-movements per night hour over the last 3 nights.
    if r.night_movements_per_hour is not None and r.night_movements_per_hour < 1.0:
        steps += 1
    return min(steps, 2)
