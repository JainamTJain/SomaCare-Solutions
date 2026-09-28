import csv, os
import numpy as np
import cv2
from somacare_ml.tools.record_and_label import RecorderCore
from somacare_ml.tools.extract_frames import extract
from somacare_ml.position.dataset import load_dataset
from somacare_ml.position import synth
from somacare_ml.turn import Event
from somacare_ml.backend_events import to_backend_event
from somacare_ml.recorded_test import poisson_upper_95, hours_needed_to_show


def test_recorder_writes_labeled_frames_and_csv(tmp_path):
    core = RecorderCore(str(tmp_path), "p01", fps=2.0)
    rng = np.random.default_rng(0)
    core.handle_key(ord("b")); core.handle_key(ord("1"))
    for i in range(6):
        core.on_frame(synth.render("back", "none", 1, rng), i * 0.5)
    core.handle_key(ord("l"))
    for i in range(6, 10):
        core.on_frame(synth.render("left", "none", 1, rng), i * 0.5)
    core.close()
    rows = list(csv.DictReader(open(core.csv_path)))
    assert len(rows) == 10 and rows[0]["label"] == "back" and rows[-1]["label"] == "left"
    ds = load_dataset(str(tmp_path))
    assert {l for _, l, _, _ in ds} == {"back", "left"}


def test_extract_frames_from_a_video(tmp_path):
    vpath = str(tmp_path / "v.mp4")
    w = cv2.VideoWriter(vpath, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (160, 120), False)
    rng = np.random.default_rng(0)
    for i in range(300):     # 30 s
        w.write(synth.render("back" if i < 150 else "left", "none", 1, rng))
    w.release()
    lp = tmp_path / "l.csv"
    lp.write_text("ts_s,label,cover,person\n0,back,none,p1\n15,left,none,p1\n")
    n = extract(vpath, str(lp), str(tmp_path / "out"), fps=2.0, margin_s=3.0)
    assert n > 20
    labels = {l for _, l, _, _ in load_dataset(str(tmp_path / "out"))}
    assert labels == {"back", "left"}


def test_backend_event_contract():
    e = Event(ts=12.0, kind="turn", position="left", previous="back", confidence=0.91, assisted=True, resets_timer=True)
    ev = to_backend_event(e, "room-1", "res-1", "position-gbdt-v0.1", persons_in_zone=2)
    assert ev["kind"] == "turn" and ev["value"]["previous"] == "back" and ev["ts"].endswith("Z")
    assert set(ev) == {"room_id", "resident_id", "ts", "kind", "value", "confidence", "model_version"}
    assert to_backend_event(Event(ts=1.0, kind="uncertain"), "r", "s", "m") is None


def test_short_clips_cannot_prove_a_low_false_confirm_rate():
    assert poisson_upper_95(0, 1.0) > 2.5           # one clean hour proves almost nothing
    assert hours_needed_to_show(0.002) == 1500.0
