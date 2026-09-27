"""Version-0 vision rules: geometry, smoothing, and no frame storage."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from edge.capture.rtsp import RtspBabyMonitor
from edge.demo import _pose, scripted_events
from edge.emit import post_event
from edge.pipeline.home import Monitor, MonitorState, tick_monitor
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


def test_color_camera_is_rejected_and_not_stored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    color = np.zeros((40, 40, 3), dtype=np.uint8)
    color[:, :] = (0, 0, 220)
    events = observe(
        keypoints=_pose("back"),
        persons_in_zone=1,
        ts=datetime(2026, 9, 27, tzinfo=UTC),
        smoother=PositionSmoother(hold_s=0),
        frame=color,
    )
    assert events[0]["value"]["camera_spectrum"] == "color_rejected"
    assert events[0]["kind"] != "position"
    assert list(Path(tmp_path).iterdir()) == []
    gray = np.full((40, 40), 90, dtype=np.uint8)
    smoother = PositionSmoother(hold_s=0)
    moment = datetime(2026, 9, 27, tzinfo=UTC)
    observe(
        keypoints=_pose("left"),
        persons_in_zone=1,
        ts=moment,
        smoother=smoother,
        frame=gray,
    )
    accepted = observe(
        keypoints=_pose("left"),
        persons_in_zone=1,
        ts=moment,
        smoother=smoother,
        frame=gray,
    )
    assert accepted[0]["kind"] == "position"
    assert accepted[0]["value"]["camera_spectrum"] == "infrared"


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


def test_rtsp_url_stays_local_and_video_only():
    with pytest.raises(ValueError):
        RtspBabyMonitor("http://192.168.1.20/stream")
    with pytest.raises(ValueError):
        RtspBabyMonitor("rtsp://user:pass@tplinkcloud.com/stream1")
    seen = []

    class Capture:
        def __init__(self):
            self.released = False

        def read(self):
            return True, np.zeros((8, 8), dtype=np.uint8)

        def release(self):
            self.released = True

    capture = Capture()

    def opener(url):
        seen.append(url)
        return capture

    camera = RtspBabyMonitor("rtsp://192.168.1.40/stream1", opener=opener)
    frame = camera.read()
    assert frame.shape == (8, 8)
    assert seen == ["rtsp://192.168.1.40/stream1"]
    camera.close()
    assert capture.released is True


def test_six_baby_monitors_emit_events_and_write_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gray = np.full((24, 24), 40, dtype=np.uint8)
    color = np.zeros((24, 24, 3), dtype=np.uint8)
    color[:, :] = (0, 0, 200)
    moment = datetime(2026, 9, 27, tzinfo=UTC)
    monitors = [
        Monitor(
            device_id=f"baby-monitor-{room}",
            room_id=f"room-{room}",
            resident_id=f"resident-{room}",
            rtsp_url=f"rtsp://192.168.1.{room}/stream1",
        )
        for room in range(1, 7)
    ]
    states = {monitor.device_id: MonitorState(smoother=PositionSmoother(hold_s=0)) for monitor in monitors}
    pose = _pose("back")
    for monitor in monitors:
        tick_monitor(
            monitor,
            states[monitor.device_id],
            frame=gray,
            ts=moment,
            keypoints=pose,
            persons_in_zone=1,
            latency_ms=40,
        )
        events = tick_monitor(
            monitor,
            states[monitor.device_id],
            frame=gray,
            ts=moment,
            keypoints=pose,
            persons_in_zone=1,
            latency_ms=40,
        )
        assert events[0]["kind"] == "position"
        assert events[0]["source"] == "camera"
        assert events[0]["device_id"] == monitor.device_id
        assert events[0]["value"]["camera_spectrum"] == "infrared"
        assert events[0]["value"]["mic"] == "off"
        assert "frame" not in events[0]
        assert "audio" not in events[0]
    rejected = tick_monitor(
        monitors[0],
        states[monitors[0].device_id],
        frame=color,
        ts=moment + timedelta(seconds=1),
        keypoints=pose,
        persons_in_zone=1,
    )
    assert rejected[0]["kind"] == "heartbeat"
    assert rejected[0]["value"]["camera_spectrum"] == "color_rejected"
    silent = tick_monitor(
        monitors[1],
        states[monitors[1].device_id],
        frame=None,
        ts=moment + timedelta(seconds=120),
        keypoints=None,
        persons_in_zone=0,
    )
    assert silent[0]["kind"] == "device_offline"
    assert silent[0]["source"] == "camera"
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
