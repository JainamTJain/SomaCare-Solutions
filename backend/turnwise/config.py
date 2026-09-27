"""Load engine constants from config/turnwise.yaml. Nothing clinical is hard-coded
in the care path beyond what this file documents.

Render's root directory is backend/, so the file that ships is
backend/config/turnwise.yaml. A copy at the repo root stays for local reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from turnwise.paths import default_config_path

DEFAULT_CONFIG_PATH = default_config_path()


@dataclass
class FeatureFlags:
    llm_preference_extract: bool = False
    llm_note_translation: bool = False
    lab_debug_frames: bool = False


@dataclass
class EngineConfig:
    pilot_mode: bool = True
    facility_timezone: str = "America/Los_Angeles"
    night_start_hour: int = 21
    night_end_hour: int = 7
    relief_min: float = 20
    moist_threshold_min: float = 120
    m_moisture: float = 0.85
    limit_floor_min: float = 60
    lead_min: float = 15
    merge_window_min: float = 30
    m_risk: dict[int, float] = field(default_factory=lambda: {0: 1.00, 1: 0.85, 2: 0.70})
    move_threshold: float = 0.05
    position_hold_s: float = 30
    position_min_confidence: float = 0.7
    verify_min_confidence: float = 0.8
    alert_accept_min: float = 5
    alert_resolve_min: float = 20
    alerts_per_cna_per_hour: int = 8
    presence_hold_s: float = 10
    bed_exit_absent_s: float = 20
    bathroom_return_min: float = 30
    bath_min_presence_s: float = 300
    keypoint_visibility_min: float = 0.75
    movement_min_s: float = 2
    camera_offline_s: float = 120
    heartbeat_s: float = 60
    continence_bin_min: float = 30
    continence_lead_min: float = 15
    learning_period: bool = True
    sharp_min: float = 80
    # Minutes a CNA does not walk when the camera verifies a check, or when
    # two tasks share one visit. Shown on the shift. Not a clinical limit.
    minutes_saved_per_verified_check: float = 4
    minutes_saved_per_merged_visit: float = 3
    features: FeatureFlags = field(default_factory=FeatureFlags)

    def risk_multiplier(self, steps: int) -> float:
        if steps not in self.m_risk:
            raise KeyError(f"no M_RISK entry for {steps} extra risk steps")
        return float(self.m_risk[steps])


def _coerce(data: dict[str, Any]) -> EngineConfig:
    raw_risk = data.get("m_risk", {0: 1.0, 1: 0.85, 2: 0.70})
    m_risk = {int(k): float(v) for k, v in raw_risk.items()}
    flags = data.get("features") or {}
    known = {f.name for f in EngineConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    kwargs = {k: v for k, v in data.items() if k in known and k not in {"m_risk", "features"}}
    return EngineConfig(
        **kwargs,
        m_risk=m_risk,
        features=FeatureFlags(
            llm_preference_extract=bool(flags.get("llm_preference_extract", False)),
            llm_note_translation=bool(flags.get("llm_note_translation", False)),
            lab_debug_frames=bool(flags.get("lab_debug_frames", False)),
        ),
    )


def load_config(path: Path | None = None) -> EngineConfig:
    path = path or DEFAULT_CONFIG_PATH
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return _coerce(data)
