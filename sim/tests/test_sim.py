"""Facility replay and continence simulator gates."""

from sim.continence_sim import evaluate
from sim.facility import run_facility


def test_fourteen_day_hall_stays_inside_the_rules():
    report = run_facility(days=14, seed=3)
    assert report["violations"] == []
    assert report["max_alerts_in_an_hour"] <= report["alert_budget"]
    assert report["verified_while_offline"] == 0
    assert report["unresolved_checks"] == 0


def test_continence_simulator_meets_its_gate():
    report = evaluate(seed=7)
    assert report.ece < 0.05
    assert report.relative_improvement >= 0.20
    assert report.beta_mae < 0.45
    assert report.charted_loglik_finite
    assert report.passed
