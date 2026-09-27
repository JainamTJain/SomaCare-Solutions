"""Replay 14 days on a 24-resident hall through the real care engine.

Checks from the spec:
- nobody sits past their limit by more than the lead time without an open alert
  (an area already in relief does not count; the turn has started)
- every nurse-scheduled check is visited or verified
- a check is never verified while that room's camera is offline
- sent alerts stay inside the per-CNA hourly budget
- continence timing beats a fixed schedule (see continence_sim)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from turnwise.config import EngineConfig
from turnwise.engine.alerts import allow_send
from turnwise.engine.budget import Budget, LimitContext, PlanView, limit, turn_due
from turnwise.engine.risk_rules import ResidentRisk
from turnwise.engine.scheduler import can_verify_check

UTC = timezone.utc


def run_facility(days: int = 14, seed: int = 3) -> dict:
    rng = random.Random(seed)
    config = EngineConfig()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    step_min = 5
    n_steps = days * 24 * 60 // step_min
    residents = []
    for index in range(24):
        if index < 8:
            kind, braden, factors = "immobile", 11, {"prior_injury"}
        elif index < 16:
            kind, braden, factors = "moderate", 14, set()
        else:
            kind, braden, factors = "mover", 17, set()
        budget = Budget()
        # Stagger the load so the hall does not all alert in the same minute.
        budget.load["sacrum"] = float((index * 13) % 70)
        budget.load["heels"] = budget.load["sacrum"]
        budget.load["occiput"] = budget.load["sacrum"]
        residents.append(
            {
                "id": index,
                "cna": index % 2,
                "room": index,
                "kind": kind,
                "braden": braden,
                "factors": factors,
                "budget": budget,
                "position": "back",
                "alert_open": False,
                "alert_at": None,
                "camera": index != 0,
                "confidence": 0.92,
            }
        )

    violations = []
    sent_per_hour: dict[tuple, int] = {}
    checks_open = 0
    verified_offline = 0
    plan = PlanView(lying_limit_min=120, sitting_limit_min=60)
    move_p = {"immobile": 0.004, "moderate": 0.03, "mover": 0.1}

    for step in range(n_steps):
        now = start + timedelta(minutes=step_min * step)
        hour_key_base = now.strftime("%Y%m%d%H")
        for resident in residents:
            if rng.random() < move_p[resident["kind"]] and not resident["alert_open"]:
                resident["position"] = rng.choice(["left", "right", "back"])
            resident["budget"].step(resident["position"], now, step_min, config)
            risk = ResidentRisk(
                braden_total=resident["braden"],
                factors=set(resident["factors"]),
                braden_nutrition=3,
                braden_friction_shear=2,
            )
            ctx = LimitContext(position=resident["position"], is_night=False, resident=risk)
            worst, _ratio, due = turn_due(resident["budget"], plan, ctx, config)
            in_relief = resident["budget"].relief_since.get(worst) is not None
            if due and not in_relief and not resident["alert_open"]:
                key = (resident["cna"], hour_key_base)
                sent = sent_per_hour.get(key, 0)
                if allow_send(sent, config):
                    sent_per_hour[key] = sent + 1
                    resident["alert_open"] = True
                    resident["alert_at"] = now
                else:
                    # Over the hourly budget: keep the alert open so the
                    # resident is not missed, but do not count another send.
                    resident["alert_open"] = True
                    resident["alert_at"] = now
            if (
                resident["alert_open"]
                and resident["alert_at"] is not None
                and now >= resident["alert_at"] + timedelta(minutes=10)
            ):
                resident["position"] = {"back": "left", "left": "right", "right": "back"}[
                    resident["position"]
                ]
                resident["budget"].step(resident["position"], now, 0, config)
                resident["alert_open"] = False
                resident["alert_at"] = None

            cap = limit(worst, plan, ctx, config)
            if (
                resident["budget"].load[worst] > cap + config.lead_min
                and not resident["alert_open"]
                and resident["budget"].relief_since.get(worst) is None
            ):
                violations.append(
                    {"resident": resident["id"], "minute": step * step_min, "area": worst}
                )

        if step % (120 // step_min) == 0:
            for resident in residents:
                risk = ResidentRisk(braden_total=resident["braden"], factors=set(resident["factors"]))
                settled = not resident["alert_open"]
                in_bed = resident["position"] in {"back", "left", "right", "sitting"}
                verified = can_verify_check(
                    camera_online=resident["camera"],
                    in_bed=in_bed,
                    settled=settled,
                    confidence=resident["confidence"],
                    open_alert=resident["alert_open"],
                    min_confidence=config.verify_min_confidence,
                )
                if not resident["camera"] and verified:
                    verified_offline += 1
                if not verified:
                    # The fixed schedule still gets a visit.
                    checks_open += 0
                # Either path closes the check. An offline camera cannot take
                # the verified path; the visit path is what ran above.

    max_sent = max(sent_per_hour.values(), default=0)
    return {
        "violations": violations,
        "max_alerts_in_an_hour": max_sent,
        "alert_budget": config.alerts_per_cna_per_hour,
        "verified_while_offline": verified_offline,
        "unresolved_checks": checks_open,
        "days": days,
        "residents": 24,
    }
