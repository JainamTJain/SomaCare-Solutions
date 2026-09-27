"""Version-0 position classifier.

Shoulder-hip geometry, used until a model trained on SLP is exported.
It is a rule, not a clinical model, and events are labeled
`position-v0.0.0-rules`.
"""

from __future__ import annotations

import math

import numpy as np

MODEL_VERSION = "position-v0.0.0-rules"
_JOINTS = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")


def classify_keypoints(keypoints: dict | None, persons_in_zone: int = 1) -> tuple[str, float]:
    """Return (position, confidence).

    Image axes: x to the right, y down, camera looking along the bed from the
    foot toward the head. Lying on the back puts the shoulder line near
    horizontal and wide. A rolled shoulder line means a side. Sitting brings
    the shoulders and hips to a similar height.
    """
    if persons_in_zone <= 0 or not keypoints:
        return "out_of_bed", 0.95
    if any(name not in keypoints or keypoints[name][2] < 0.35 for name in _JOINTS):
        return "unknown", 0.4

    points = {name: np.array(keypoints[name][:2], dtype=float) for name in _JOINTS}
    left_shoulder, right_shoulder = points["left_shoulder"], points["right_shoulder"]
    left_hip, right_hip = points["left_hip"], points["right_hip"]
    mid_shoulder = (left_shoulder + right_shoulder) / 2
    mid_hip = (left_hip + right_hip) / 2
    shoulder_width = float(np.linalg.norm(left_shoulder - right_shoulder))
    torso = float(np.linalg.norm(mid_shoulder - mid_hip))
    if torso < 1.0:
        return "unknown", 0.35

    shoulder_angle = math.degrees(
        math.atan2(left_shoulder[1] - right_shoulder[1], left_shoulder[0] - right_shoulder[0])
    )
    # atan2 reports a left-to-right horizontal line as 180 degrees when the
    # left joint is on the left of the frame. Fold it into [-90, 90].
    if shoulder_angle > 90:
        shoulder_angle -= 180
    elif shoulder_angle < -90:
        shoulder_angle += 180
    along_bed = abs(mid_shoulder[1] - mid_hip[1]) / torso
    ratio = shoulder_width / torso
    confidence = float(np.mean([keypoints[name][2] for name in _JOINTS]))

    # Sitting up foreshortens the torso, so the shoulders look wide
    # relative to the hip-shoulder distance.
    if ratio > 1.15 or (along_bed < 0.45 and ratio > 0.65):
        return "sitting", min(0.95, confidence)
    if abs(shoulder_angle) > 25 or ratio < 0.45:
        # The lower shoulder in the image is the side against the mattress.
        if left_shoulder[1] > right_shoulder[1]:
            return "left", min(0.9, confidence)
        return "right", min(0.9, confidence)
    return "back", min(0.92, confidence)
