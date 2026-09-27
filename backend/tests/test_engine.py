"""Unit tests required by the engineering spec, plus the floor and pilot guards."""

from datetime import datetime, timedelta, timezone

import pytest

from turnwise.config import EngineConfig
from turnwise.engine.alerts import AlertState, advance_alert
from turnwise.engine.budget import Budget, LimitContext, PilotModeError, PlanView, limit
from turnwise.engine.continence import (
    cumulative_wet,
    loglik_charted_dry,
    loglik_charted_wet,
    loglik_exact,
    schedule_from_hazard,
)
from turnwise.engine.risk_rules import ResidentRisk, braden_band, extra_risk_steps
from turnwise.engine.scheduler import SchedTask, can_verify_check, merge_tasks

UTC = timezone.utc


def _plan(**kwargs) -> PlanView:
    base = dict(lying_limit_min=120, sitting_limit_min=60, night_lying_limit_min=None)
    base.update(kwargs)
    return PlanView(**base)


def _ctx(resident=None, **kwargs) -> LimitContext:
    base = dict(
        position="back",
        is_night=False,
        resident=resident or ResidentRisk(),
        moist_minutes_24h=0,
    )
    base.update(kwargs)
    return LimitContext(**base)


def test_back_loads_sacrum_and_heels_not_hips():
    cfg = EngineConfig()
    budget = Budget()
    budget.step("back", datetime(2026, 9, 27, tzinfo=UTC), 180, cfg)
    assert budget.load["sacrum"] == 180
    assert budget.load["heels"] == 180
    assert budget.load["left_hip"] == 0
    assert budget.load["right_hip"] == 0


def test_turn_to_left_resets_sacrum_after_relief():
    cfg = EngineConfig(relief_min=20)
    budget = Budget()
    t0 = datetime(2026, 9, 27, tzinfo=UTC)
    budget.step("back", t0, 180, cfg)
    t1 = t0 + timedelta(minutes=180)
    budget.step("left", t1, 1, cfg)
    assert budget.load["sacrum"] == 180
    t2 = t1 + timedelta(minutes=20)
    budget.step("left", t2, 20, cfg)
    assert budget.load["sacrum"] == 0
    assert budget.load["left_hip"] == 21


def test_unknown_keeps_loading_and_out_of_room_freezes():
    cfg = EngineConfig()
    budget = Budget()
    t0 = datetime(2026, 9, 27, tzinfo=UTC)
    budget.step("back", t0, 30, cfg)
    t1 = t0 + timedelta(minutes=30)
    budget.step("unknown", t1, 10, cfg)
    assert budget.load["sacrum"] == 40
    assert budget.last_known == "back"
    frozen = dict(budget.load)
    t2 = t1 + timedelta(minutes=10)
    budget.step("out_of_room", t2, 50, cfg)
    assert budget.load == frozen


def test_pilot_mode_rejects_multiplier_above_one():
    cfg = EngineConfig(pilot_mode=True, m_risk={0: 1.2, 1: 0.85, 2: 0.7})
    with pytest.raises(PilotModeError):
        limit("sacrum", _plan(), _ctx(), cfg)


def test_pilot_mode_only_tightens():
    cfg = EngineConfig(pilot_mode=True)
    resident = ResidentRisk(
        braden_total=12,
        factors={"prior_injury", "diabetes"},
        braden_friction_shear=1,
    )
    tightened = limit("left_hip", _plan(lying_limit_min=120), _ctx(resident), cfg)
    assert tightened < 120
    assert extra_risk_steps(resident) == 2


def test_limit_does_not_fall_below_floor_without_nurse_override():
    cfg = EngineConfig(limit_floor_min=60, pilot_mode=True)
    # 50 * 0.70 = 35, which is under the floor.
    resident = ResidentRisk(factors={"prior_injury", "diabetes"}, braden_friction_shear=1)
    assert extra_risk_steps(resident) == 2
    got = limit("sacrum", _plan(lying_limit_min=50), _ctx(resident), cfg)
    assert got == 60
    overridden = limit(
        "sacrum",
        _plan(lying_limit_min=50),
        _ctx(resident, nurse_override_floor_min=30),
        cfg,
    )
    assert overridden == pytest.approx(35)


@pytest.mark.parametrize(
    "total,band",
    [
        (9, "very_high"),
        (10, "high"),
        (12, "high"),
        (13, "moderate"),
        (14, "moderate"),
        (15, "mild"),
        (18, "mild"),
        (19, "none"),
    ],
)
def test_braden_bands_at_boundaries(total, band):
    assert braden_band(total) == band


def test_merge_window_20_merges_40_does_not():
    t0 = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
    turn = SchedTask(id="t", resident_id="r", kind="turn", due_at=t0, priority=1.2, room_order=3)
    close = SchedTask(
        id="c",
        resident_id="r",
        kind="continence",
        due_at=t0 + timedelta(minutes=20),
        priority=0.4,
        room_order=3,
    )
    visits = merge_tasks([turn, close], 30)
    assert len(visits) == 1
    assert visits[0].due_at == t0
    assert visits[0].kinds == ["turn", "continence"]
    assert close.merged_into == "t"

    far = SchedTask(
        id="f",
        resident_id="r",
        kind="continence",
        due_at=t0 + timedelta(minutes=40),
        room_order=3,
    )
    turn2 = SchedTask(id="t2", resident_id="r", kind="turn", due_at=t0, room_order=3)
    visits = merge_tasks([turn2, far], 30)
    assert len(visits) == 2
    assert far.merged_into is None


def test_verified_check_never_when_camera_offline():
    assert (
        can_verify_check(
            camera_online=False,
            in_bed=True,
            settled=True,
            confidence=0.95,
            open_alert=False,
        )
        is False
    )
    assert (
        can_verify_check(
            camera_online=True,
            in_bed=True,
            settled=True,
            confidence=0.95,
            open_alert=False,
        )
        is True
    )
    assert (
        can_verify_check(
            camera_online=True,
            in_bed=True,
            settled=True,
            confidence=0.79,
            open_alert=False,
        )
        is False
    )


def test_charted_likelihoods_match_hand_computation():
    import math

    p = [0.2, 0.5]
    expected_dry = math.log(0.8) + math.log(0.5)
    assert loglik_charted_dry(p, [0, 1]) == pytest.approx(expected_dry)
    expected_wet = math.log(1 - (0.8 * 0.5))
    assert loglik_charted_wet(p, [0, 1]) == pytest.approx(expected_wet)
    expected_exact = math.log(0.5) + math.log(0.8)
    assert loglik_exact(p, 1, [0]) == pytest.approx(expected_exact)
    assert cumulative_wet([0.2, 0.5]) == pytest.approx(1 - 0.8 * 0.5)


def test_learning_period_keeps_nurse_checks():
    start = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
    bins = [start + timedelta(minutes=30 * i) for i in range(4)]
    probs = [0.1, 0.1, 0.1, 0.1]
    nurse = [start + timedelta(hours=2)]
    visits = schedule_from_hazard(
        bin_starts=bins,
        probs=probs,
        threshold=0.99,
        lead_min=15,
        nurse_checks=nurse,
        learning_period=True,
    )
    assert any(v.source == "nurse_schedule" and v.due_at == nurse[0] for v in visits)
    dropped = schedule_from_hazard(
        bin_starts=bins,
        probs=probs,
        threshold=0.99,
        lead_min=15,
        nurse_checks=nurse,
        learning_period=False,
    )
    assert all(v.source != "nurse_schedule" for v in dropped)


def test_escalation_at_5_and_20_and_resolution_on_turn():
    cfg = EngineConfig()
    t0 = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
    alert = AlertState(
        id="a",
        task_id="task",
        staff_id="cna",
        created_at=t0,
        rule="turn_due",
        inputs={"minutes_left": 12, "worst_area": "sacrum"},
        plan_version=3,
        model_version="position-v0",
    )
    actions = advance_alert(alert, t0 + timedelta(minutes=5), cfg, saw_confirming_event=False)
    assert actions == ["resend", "notify_charge"]
    assert alert.charge_notified is True
    again = advance_alert(alert, t0 + timedelta(minutes=6), cfg, saw_confirming_event=False)
    assert "resend" not in again
    escalated = advance_alert(alert, t0 + timedelta(minutes=20), cfg, saw_confirming_event=False)
    assert escalated == ["escalate"]
    assert alert.status == "escalated"
    resolved = advance_alert(alert, t0 + timedelta(minutes=22), cfg, saw_confirming_event=True)
    assert resolved == ["resolved"]
    assert alert.status == "resolved"
    assert alert.resolved_at is not None


def test_out_of_bed_relieves_after_relief_window():
    cfg = EngineConfig(relief_min=20)
    budget = Budget()
    t0 = datetime(2026, 9, 27, tzinfo=UTC)
    budget.step("back", t0, 100, cfg)
    t1 = t0 + timedelta(minutes=100)
    budget.step("out_of_bed", t1, 1, cfg)
    t2 = t1 + timedelta(minutes=20)
    budget.step("out_of_bed", t2, 20, cfg)
    assert all(v == 0 for v in budget.load.values())
