"""Model 2, version 1: movement, presence, bed exit and bath as explicit rules.

Thresholds are config, tuned on labeled recordings before any pilot claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def torso_length(keypoints: dict) -> float:
    if "left_shoulder" not in keypoints or "left_hip" not in keypoints:
        return 1.0
    shoulder = np.array(
        [
            (keypoints["left_shoulder"][0] + keypoints["right_shoulder"][0]) / 2,
            (keypoints["left_shoulder"][1] + keypoints["right_shoulder"][1]) / 2,
        ]
    )
    hip = np.array(
        [
            (keypoints["left_hip"][0] + keypoints["right_hip"][0]) / 2,
            (keypoints["left_hip"][1] + keypoints["right_hip"][1]) / 2,
        ]
    )
    length = float(np.linalg.norm(shoulder - hip))
    return length if length > 1 else 1.0


def frame_displacement(current: dict, previous: dict) -> float:
    """Mean joint movement divided by torso length. Visible joints only."""
    shared = [
        name
        for name in current
        if name in previous and current[name][2] >= 0.35 and previous[name][2] >= 0.35
    ]
    if not shared:
        return 0.0
    dists = [
        float(np.linalg.norm(np.array(current[name][:2]) - np.array(previous[name][:2])))
        for name in shared
    ]
    return float(np.mean(dists)) / torso_length(current)


def keypoint_visibility(keypoints: dict) -> float:
    if not keypoints:
        return 0.0
    return float(np.mean([point[2] for point in keypoints.values()]))


@dataclass
class SignalState:
    moving_s: float = 0.0
    presence_s: float = 0.0
    alone_s: float = 0.0
    absent_s: float = 0.0
    present: bool = False
    in_bed: bool = False
    was_in_bed: bool = False
    bath_open: bool = False
    exit_at: object | None = None
    exit_toward_bathroom: bool = False
    last_keypoints: dict | None = None
    events: list = field(default_factory=list)


def step_signals(
    state: SignalState,
    *,
    keypoints: dict | None,
    persons_in_zone: int,
    lights_on: bool,
    toward_bathroom: bool,
    dt_s: float,
    ts,
    cfg,
) -> list[dict]:
    """Advance the rule detectors by one frame interval. Returns new events."""
    events: list[dict] = []
    if state.last_keypoints is not None and keypoints is not None and persons_in_zone >= 1:
        disp = frame_displacement(keypoints, state.last_keypoints)
        if disp > cfg.move_threshold:
            state.moving_s += dt_s
        else:
            state.moving_s = 0.0
        if state.moving_s >= cfg.movement_min_s and persons_in_zone == 1:
            events.append(
                {
                    "kind": "movement",
                    "value": {"magnitude": round(disp, 4), "duration_s": round(state.moving_s, 2)},
                }
            )
            state.moving_s = 0.0
    else:
        state.moving_s = 0.0

    if persons_in_zone >= 2:
        state.presence_s += dt_s
        state.alone_s = 0.0
        if not state.present and state.presence_s >= cfg.presence_hold_s:
            state.present = True
            events.append({"kind": "presence_start", "value": {"persons": persons_in_zone}})
    else:
        state.alone_s += dt_s
        state.presence_s = 0.0
        if state.present and state.alone_s >= cfg.presence_hold_s:
            state.present = False
            events.append({"kind": "presence_end", "value": {"persons": persons_in_zone}})

    in_bed = persons_in_zone >= 1 and keypoints is not None
    if in_bed:
        state.absent_s = 0.0
        if state.exit_at is not None and state.exit_toward_bathroom:
            elapsed_min = (ts - state.exit_at).total_seconds() / 60.0
            if elapsed_min <= cfg.bathroom_return_min:
                events.append(
                    {
                        "kind": "bathroom_trip",
                        "value": {
                            "left_at": state.exit_at.isoformat(),
                            "returned_at": ts.isoformat(),
                        },
                    }
                )
            state.exit_at = None
        state.was_in_bed = True
        state.in_bed = True
    else:
        state.absent_s += dt_s
        if state.was_in_bed and state.absent_s >= cfg.bed_exit_absent_s and state.in_bed:
            state.in_bed = False
            state.exit_at = ts
            state.exit_toward_bathroom = toward_bathroom
            events.append({"kind": "bed_exit", "value": {"direction": "bathroom" if toward_bathroom else "other"}})

    visible = keypoint_visibility(keypoints or {})
    if (
        state.present
        and state.presence_s >= cfg.bath_min_presence_s
        and visible >= cfg.keypoint_visibility_min
        and lights_on
        and not state.bath_open
    ):
        state.bath_open = True
        events.append({"kind": "bath_start", "value": {"visibility": round(visible, 3)}})
    if state.bath_open and not state.present:
        state.bath_open = False
        events.append({"kind": "bath_end", "value": {"duration_s": round(state.presence_s, 1)}})

    state.last_keypoints = keypoints
    return events
