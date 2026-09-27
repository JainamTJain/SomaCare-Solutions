"""In-memory frame loop. Production builds do not write frames."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from turnwise.config import EngineConfig, load_config

from edge.capture.infrared import frame_is_infrared
from edge.pipeline.position_rules import MODEL_VERSION, classify_keypoints
from edge.pipeline.smooth import PositionSmoother


def lab_debug_allowed(consent: bool, config: EngineConfig | None = None) -> bool:
    config = config or load_config()
    flag = os.environ.get("TURNWISE_LAB_DEBUG", "") == "1" and config.features.lab_debug_frames
    return bool(flag and consent)


def observe(
    *,
    keypoints: dict | None,
    persons_in_zone: int,
    ts: datetime,
    smoother: PositionSmoother,
    frame=None,
    consent_debug: bool = False,
    config: EngineConfig | None = None,
) -> list[dict]:
    """Classify one observation. `frame` is accepted and discarded.

    Nothing in this function writes the frame. A lab debug path exists only
    when the build flag and written consent are both present, and even then
    this function does not write; callers must opt in separately.
    """
    spectrum = None
    saturation = None
    if frame is not None:
        accepted, saturation = frame_is_infrared(frame)
        spectrum = "infrared" if accepted else "color_rejected"
    del frame  # discarded. Do not persist.
    if spectrum == "color_rejected":
        return [
            {
                "ts": ts.astimezone(timezone.utc).isoformat(),
                "kind": "heartbeat",
                "value": {
                    "camera_spectrum": "color_rejected",
                    "saturation": round(float(saturation or 0), 3),
                    "position_skipped": True,
                },
                "confidence": 0.0,
                "model_version": MODEL_VERSION,
            }
        ]
    if consent_debug and lab_debug_allowed(True, config):
        # The flag is checked so a future debug sink can sit here.
        # This build still does not write.
        pass
    label, confidence = classify_keypoints(keypoints, persons_in_zone)
    changed = smoother.update(label, confidence, ts)
    if changed is None:
        return []
    previous, current = changed
    value = {
        "position": current,
        "previous": previous,
        "persons_in_zone": persons_in_zone,
    }
    if spectrum is not None:
        value["camera_spectrum"] = spectrum
        value["saturation"] = round(float(saturation or 0), 3)
    return [
        {
            "ts": ts.astimezone(timezone.utc).isoformat(),
            "kind": "position",
            "value": value,
            "confidence": confidence,
            "model_version": MODEL_VERSION,
        }
    ]
