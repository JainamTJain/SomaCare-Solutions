"""One home computer watches every infrared baby monitor.

Each tick reads one frame per camera, runs the shoulder-hip rule, and
returns events. Frames are not written and are not placed on the event.
Silence for `offline_s` seconds emits `device_offline` once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from edge.pipeline.run import observe
from turnwise.engine.gate1 import live_status
from edge.pipeline.smooth import PositionSmoother


@dataclass
class Monitor:
    device_id: str
    room_id: str
    resident_id: str
    rtsp_url: str


@dataclass
class MonitorState:
    smoother: PositionSmoother
    started_at: datetime | None = None
    last_frame_at: datetime | None = None
    offline_sent: bool = False
    frames: int = 0


@dataclass
class HomeComputer:
    monitors: list[Monitor]
    states: dict[str, MonitorState] = field(default_factory=dict)
    offline_s: float = 120

    def state_for(self, monitor: Monitor) -> MonitorState:
        if monitor.device_id not in self.states:
            self.states[monitor.device_id] = MonitorState(smoother=PositionSmoother())
        return self.states[monitor.device_id]


def _stamp(event: dict, monitor: Monitor, *, fps: float | None, latency_ms: float | None) -> dict:
    if any(key in event for key in ("frame", "image", "jpeg", "audio")):
        raise ValueError("baby monitor events must not carry frames or audio")
    event["source"] = "camera"
    event["device_id"] = monitor.device_id
    event["room_id"] = monitor.room_id
    event["resident_id"] = monitor.resident_id
    value = dict(event.get("value") or {})
    value["mic"] = "off"
    value["cloud"] = "off"
    value.setdefault("cover", "unknown")
    value["gate1"] = live_status()["status"]
    if fps is not None:
        value["fps"] = round(fps, 2)
    if latency_ms is not None:
        value["latency_ms"] = round(latency_ms, 1)
    event["value"] = value
    return event


def tick_monitor(
    monitor: Monitor,
    state: MonitorState,
    *,
    frame,
    ts: datetime,
    keypoints: dict | None,
    persons_in_zone: int,
    latency_ms: float | None = None,
    offline_s: float = 120,
) -> list[dict]:
    """One camera, one moment. `frame` is discarded inside observe()."""
    moment = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if state.started_at is None:
        state.started_at = moment
    if frame is None:
        anchor = state.last_frame_at or state.started_at
        silent = (moment - anchor).total_seconds() >= offline_s
        if silent and not state.offline_sent:
            state.offline_sent = True
            return [
                _stamp(
                    {
                        "ts": moment.astimezone(timezone.utc).isoformat(),
                        "kind": "device_offline",
                        "value": {
                            "reason": "no_frame",
                            "silence_s": round((moment - anchor).total_seconds(), 1),
                        },
                        "confidence": None,
                        "model_version": "position-v0.0.0-rules",
                    },
                    monitor,
                    fps=0.0,
                    latency_ms=None,
                )
            ]
        return []

    state.last_frame_at = moment
    state.offline_sent = False
    state.frames += 1
    elapsed = max((moment - state.started_at).total_seconds(), 0.001)
    fps = state.frames / elapsed
    events = observe(
        keypoints=keypoints,
        persons_in_zone=persons_in_zone,
        ts=moment,
        smoother=state.smoother,
        frame=frame,
    )
    return [
        _stamp(event, monitor, fps=fps, latency_ms=latency_ms)
        for event in events
    ]
