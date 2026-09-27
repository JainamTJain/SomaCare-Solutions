"""Gate 1 scorer. These trials are synthetic. No camera was read."""

import pytest

from turnwise.engine.gate1 import Trial, live_status, score_trials


def _row(cover, truth, predicted, confidence, fusion):
    return Trial(cover, truth, predicted, confidence, fusion)


def test_live_status_is_not_run():
    status = live_status()
    assert status["status"] == "not_run"
    assert status["hardware_hours"] == 0
    assert status["per_side_under_blanket"] == "not_claimed"
    assert status["covers"] == {"none": "not_run", "sheet": "not_run", "blanket": "not_run"}


def test_empty_trials_stay_not_run():
    report = score_trials([])
    assert report["status"] == "not_run"
    assert report["architecture"] == "withheld"
    assert report["per_side_under_blanket"] == "not_claimed"


def test_confident_wrong_blanket_label_fails_closed():
    trials = []
    for _ in range(10):
        trials.append(_row("none", "left", "left", 0.93, "likely"))
        trials.append(_row("sheet", "left", "left", 0.93, "likely"))
    for _ in range(9):
        trials.append(_row("blanket", "right", None, 0.2, "uncertain"))
    trials.append(_row("blanket", "right", "left", 0.96, "likely"))
    report = score_trials(trials)
    assert report["status"] == "fail"
    assert report["unsafe_confirmed"] is True
    assert report["architecture"] == "movement_stillness_only"
    assert report["per_side_under_blanket"] == "not_claimed"
    assert "blanket_false_confirmed" in report["reasons"]
    assert report["by_cover"]["blanket"]["false_confirmed"] == 1


def test_silent_blanket_is_a_cliff_not_a_pass():
    trials = []
    for _ in range(10):
        trials.append(_row("none", "back", "back", 0.9, "likely"))
        trials.append(_row("sheet", "back", "back", 0.9, "likely"))
        trials.append(_row("blanket", "back", None, 0.15, "uncertain"))
    report = score_trials(trials)
    assert report["status"] == "fail"
    assert report["unsafe_confirmed"] is False
    assert report["cliff"] is True
    assert report["architecture"] == "movement_stillness_only"
    assert report["by_cover"]["blanket"]["uncertain_rate"] == 1.0
    assert report["by_cover"]["blanket"]["false_confirmed"] == 0


def test_pass_requires_every_cover_and_does_not_claim_hardware():
    trials = []
    for cover in ("none", "sheet", "blanket"):
        for _ in range(10):
            trials.append(_row(cover, "right", "right", 0.92, "likely"))
    report = score_trials(trials)
    assert report["status"] == "pass"
    assert report["hardware_hours"] == 0
    assert report["cliff"] is False
    assert "Scored from labeled trials" in report["note"]


def test_unknown_cover_is_rejected():
    with pytest.raises(ValueError):
        score_trials([_row("quilt", "back", "back", 0.9, "likely")])
