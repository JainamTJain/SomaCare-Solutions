"""Version-0 vision rules: geometry, smoothing, and no frame storage."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from edge.demo import _pose, scripted_events
from edge.emit import post_event
from edge.pipeline.position_rules import classify_keypoints
from edge.pipeline.rules import SignalState, frame_displacement, step_signals
from edge.pipeline.run import observe
from edge.pipeline.smooth import PositionSmoother
from turnwise.config import EngineConfig

UTC = timezone.utc


def test_geometry_labels():
    for name in ("back", "left", "right", "sitting"):
        label, confidence = classify_keypoints(_pose(name), 1)
        assert label == name, name
        assert confidence >= 0.7
    assert classify_keypoints(None, 0)[0] == "out_of_bed"


def test_smoother_holds_for_30_seconds():
    smoother = PositionSmoother(hold_s=30, min_confidence=0.7)
    t0 = datetime(2026, 9, 27, tzinfo=UTC)
    assert smoother.update("left", 0.9, t0) is None
    assert smoother.update("left", 0.9, t0 + timedelta(seconds=29)) is None
    changed = smoother.update("left", 0.91, t0 + timedelta(seconds=30))
    assert changed == (None, "left")
    # Flicker below the confidence gate does not move the class.
    assert smoother.update("right", 0.4, t0 + timedelta(seconds=40)) is None
    assert smoother.current == "left"


def test_scripted_sequence_emits_position_without_touching_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    events = scripted_events(hold_s=30)
    labels = [event["value"]["position"] for event in events]
    assert labels == ["back", "right"]
    assert all(event["model_version"] == "position-v0.0.0-rules" for event in events)
    assert list(Path(tmp_path).rglob("*")) == []


def test_observe_discards_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    observe(
        keypoints=_pose("back"),
        persons_in_zone=1,
        ts=datetime(2026, 9, 27, tzinfo=UTC),
        smoother=PositionSmoother(),
        frame=frame,
    )
    assert list(Path(tmp_path).iterdir()) == []


def test_emit_refuses_frames():
    try:
        post_event("http://127.0.0.1:9", "token", {"kind": "position", "frame": b"nope"})
    except ValueError as exc:
        assert "frames" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_self_movement_presence_and_bed_exit():
    cfg = EngineConfig()
    state = SignalState()
    t0 = datetime(2026, 9, 27, tzinfo=UTC)
    still = _pose("back")
    shifted = {
        name: (point[0] + 30, point[1] + 5, point[2]) for name, point in still.items()
    }
    assert frame_displacement(shifted, still) > cfg.move_threshold
    events = []
    # Two seconds of movement, one person: a self-movement event.
    events += step_signals(
        state,
        keypoints=still,
        persons_in_zone=1,
        lights_on=False,
        toward_bathroom=False,
        dt_s=1,
        ts=t0,
        cfg=cfg,
    )
    events += step_signals(
        state,
        keypoints=shifted,
        persons_in_zone=1,
        lights_on=False,
        toward_bathroom=False,
        dt_s=2,
        ts=t0 + timedelta(seconds=2),
        cfg=cfg,
    )
    assert any(event["kind"] == "movement" for event in events)

    state = SignalState()
    events = []
    for second in range(0, 12):
        events += step_signals(
            state,
            keypoints=still,
            persons_in_zone=2,
            lights_on=True,
            toward_bathroom=False,
            dt_s=1,
            ts=t0 + timedelta(seconds=second),
            cfg=cfg,
        )
    assert any(event["kind"] == "presence_start" for event in events)

    state = SignalState(was_in_bed=True, in_bed=True)
    events = step_signals(
        state,
        keypoints=None,
        persons_in_zone=0,
        lights_on=False,
        toward_bathroom=True,
        dt_s=20,
        ts=t0 + timedelta(seconds=20),
        cfg=cfg,
    )
    assert any(event["kind"] == "bed_exit" and event["value"]["direction"] == "bathroom" for event in events)
    events = step_signals(
        state,
        keypoints=still,
        persons_in_zone=1,
        lights_on=False,
        toward_bathroom=False,
        dt_s=1,
        ts=t0 + timedelta(minutes=10),
        cfg=cfg,
    )
    assert any(event["kind"] == "bathroom_trip" for event in events)
