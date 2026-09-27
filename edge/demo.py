"""Replay a scripted posture sequence through the rule classifier.

Webcam capture is optional (`--source webcam`) and is not required for tests.
No frame is written.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from edge.pipeline.position_rules import classify_keypoints
from edge.pipeline.run import observe
from edge.pipeline.smooth import PositionSmoother


def _pose(kind: str) -> dict:
    conf = 0.95
    if kind == "back":
        return {
            "left_shoulder": (80, 100, conf),
            "right_shoulder": (160, 100, conf),
            "left_hip": (90, 220, conf),
            "right_hip": (150, 220, conf),
        }
    if kind == "left":
        return {
            "left_shoulder": (120, 150, conf),
            "right_shoulder": (140, 90, conf),
            "left_hip": (118, 230, conf),
            "right_hip": (145, 180, conf),
        }
    if kind == "right":
        return {
            "left_shoulder": (140, 90, conf),
            "right_shoulder": (120, 150, conf),
            "left_hip": (145, 180, conf),
            "right_hip": (118, 230, conf),
        }
    if kind == "sitting":
        return {
            "left_shoulder": (70, 100, conf),
            "right_shoulder": (210, 102, conf),
            "left_hip": (90, 145, conf),
            "right_hip": (190, 148, conf),
        }
    raise ValueError(kind)


def scripted_events(hold_s: float = 30) -> list[dict]:
    """Back, then right, each held long enough to pass the smoother."""
    smoother = PositionSmoother(hold_s=hold_s, min_confidence=0.7)
    start = datetime(2026, 9, 27, 2, 0, tzinfo=timezone.utc)
    events = []
    sequence = [("back", 0), ("back", hold_s), ("right", hold_s + 1), ("right", 2 * hold_s + 1)]
    for label, second in sequence:
        ts = start + timedelta(seconds=second)
        events.extend(
            observe(
                keypoints=_pose(label),
                persons_in_zone=1,
                ts=ts,
                smoother=smoother,
                frame=None,
            )
        )
    return events


def main():
    parser = argparse.ArgumentParser(description="TurnWise edge demo (version 0 rules)")
    parser.add_argument("--source", choices=["scripted", "webcam"], default="scripted")
    args = parser.parse_args()
    if args.source == "webcam":
        raise SystemExit(
            "Webcam mode needs OpenCV and a camera on this machine. "
            "Use --source scripted to replay a posture sequence."
        )
    for event in scripted_events():
        label, conf = event["value"]["position"], event["confidence"]
        print(f"{event['ts']} {label} conf={conf:.2f} model={event['model_version']}")
    # Sanity: the geometry itself, before smoothing.
    for name in ("back", "left", "right", "sitting"):
        label, _ = classify_keypoints(_pose(name), 1)
        print(f"instant {name} -> {label}")


if __name__ == "__main__":
    main()
