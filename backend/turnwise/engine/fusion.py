"""Decide whether a reposition is strong enough to reset a timer.

Near-infrared light reflects off a blanket. It does not show the shoulder
and hip underneath. A camera reading under a sheet, a blanket, or an
unknown cover stays uncertain, even at high confidence, until Gate 1
scores that cover. Uncovered vision can be labeled likely. That label is
still not a passed gate. A bed-only reading stays uncertain until
`bed_rule_validated` is true. This repo does not ship a bed sensor.
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
    cover: str | None = None,
) -> str:
    """Return 'confirmed', 'likely', or 'uncertain'.

    `cover` is none, sheet, blanket, or unknown. Anything other than
    none blocks a vision-only reset. Gate 1 has not passed for any cover.
    """
    cfg = cfg or load_config()
    vision_on = cfg.has_vision if has_vision is None else has_vision
    if vision_change is not None and cover != "none":
        agreed = (
            bed_movement is not None
            and bed_movement.magnitude >= cfg.bed_min_mag
            and vision_change.confidence >= cfg.vision_min_conf
            and cfg.bed_rule_validated
        )
        return "confirmed" if agreed else "uncertain"
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
