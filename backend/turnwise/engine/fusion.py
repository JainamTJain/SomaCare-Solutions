"""Decide whether a reposition is strong enough to reset a timer.

The sensor in this product is an infrared baby monitor. The home computer
runs the shoulder-hip rule on that picture. Uncertain vision never resets
a timer. A bed-only reading is not the product path and stays uncertain
until `bed_rule_validated` is true. Night vitals are not a reposition and
never reach this function.
"""

from __future__ import annotations

from dataclasses import dataclass

from turnwise.config import EngineConfig, load_config


@dataclass
class VisionChange:
    confidence: float


@dataclass
class BedMovement:
    magnitude: float
    duration_s: float = 0.0


def classify_reposition(
    vision_change: VisionChange | None,
    bed_movement: BedMovement | None,
    cfg: EngineConfig | None = None,
    *,
    has_vision: bool | None = None,
) -> str:
    """Return 'confirmed', 'likely', or 'uncertain'."""
    cfg = cfg or load_config()
    vision_on = cfg.has_vision if has_vision is None else has_vision
    if vision_change and vision_change.confidence >= cfg.vision_min_conf:
        if bed_movement and bed_movement.magnitude >= cfg.bed_min_mag:
            return "confirmed"
        return "likely"
    if bed_movement and not vision_on:
        big = (
            bed_movement.magnitude >= cfg.bed_reposition_mag
            and bed_movement.duration_s >= cfg.bed_reposition_dur_s
        )
        return "likely" if big and cfg.bed_rule_validated else "uncertain"
    return "uncertain"


def resets_timer(result: str, cfg: EngineConfig | None = None) -> bool:
    """True only when the reposition is strong enough to clear the timer."""
    cfg = cfg or load_config()
    if result == "uncertain":
        return False
    if result == "confirmed":
        return True
    return result == "likely" and cfg.accept_likely
