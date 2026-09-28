from somacare_ml.turn import TurnDetector
from somacare_ml.config import TurnConfig


def feed(det, seq):
    ev = []
    for ts, lab, conf, persons in seq:
        ev += det.update(ts, lab, conf, persons)
    return ev


def test_flicker_does_not_confirm():
    d = TurnDetector(initial="back")
    seq = [(i * 0.5, "left" if i % 4 == 0 else "back", 0.9, 1) for i in range(200)]
    assert [e for e in feed(d, seq) if e.resets_timer] == []


def test_held_change_confirms_and_resets():
    d = TurnDetector(initial="back")
    seq = [(i * 0.5, "left", 0.9, 1) for i in range(80)]
    ev = [e for e in feed(d, seq) if e.resets_timer]
    assert len(ev) == 1 and ev[0].position == "left" and ev[0].previous == "back" and not ev[0].assisted


def test_second_person_makes_it_a_caregiver_turn():
    d = TurnDetector(initial="back")
    seq = [(i * 0.5, "right", 0.9, 2 if i > 10 else 1) for i in range(80)]
    ev = [e for e in feed(d, seq) if e.resets_timer]
    assert ev and ev[0].kind == "turn" and ev[0].assisted


def test_unsure_readings_never_reset_a_timer():
    d = TurnDetector(initial="back")
    seq = [(i * 0.5, "left", 0.4, 1) for i in range(400)] + [(200 + i * 0.5, "unknown", 0.95, 1) for i in range(400)]
    assert [e for e in feed(d, seq) if e.resets_timer] == []


def test_feed_gap_discards_pending_change():
    d = TurnDetector(initial="back")
    feed(d, [(i * 0.5, "left", 0.9, 1) for i in range(40)])          # 20 s of a candidate
    ev = d.update(400.0, "left", 0.9, 1)                              # long silence, then the same reading
    assert any(e.kind == "feed_gap" for e in ev)
    assert not any(e.resets_timer for e in ev)


def test_below_hold_time_does_not_confirm():
    cfg = TurnConfig(hold_s=30)
    d = TurnDetector(cfg, initial="back")
    ev = feed(d, [(i * 0.5, "left", 0.9, 1) for i in range(50)])      # 25 s
    assert not any(e.resets_timer for e in ev)
