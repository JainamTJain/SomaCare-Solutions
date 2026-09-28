"""Error-injection simulation. Question: is the system still safe when the position model is wrong?

True world (per resident, per minute): true exposure = minutes since a real repositioning.
System world: believed exposure = minutes since the last CONFIRMED repositioning.
Errors injected from a measured confusion profile:
  missed_reposition_prob   a real self-reposition is not seen        (safe direction: extra alert)
  false_confirm_per_hour   a repositioning is 'confirmed' that never happened (dangerous: resets the belief)
Fail-safes:
  alerts fire at limit - lead, on believed exposure
  hard_visit_cap_min       a human visit at least this often no matter what the camera says
  a resident with no camera falls back to scheduled visits every scheduled_fallback_min

A failure is a stretch where TRUE exposure exceeds limit + tolerance. We count failure episodes.
"""
from dataclasses import dataclass
import numpy as np
from .config import SafetyConfig


@dataclass
class Scenario:
    name: str
    camera: bool = True
    missed_reposition_prob: float = 0.0
    false_confirm_per_hour: float = 0.0
    hard_cap_min: object = 240.0          # None disables. A human must visit at least this often
    self_reposition_per_hour: float = 0.25
    missed_visit_prob: float = 0.10       # a caregiver misses or delays a scheduled visit (paper reality)


def simulate(scn: Scenario, cfg: SafetyConfig = SafetyConfig(), residents=24, days=14, seed=0):
    rng = np.random.default_rng(seed)
    minutes = days * 24 * 60
    fail_eps = 0
    res_with_fail = 0
    max_exp = 0.0
    visits = 0
    alerts = 0
    false_confirms = 0
    for r in range(residents):
        true_exp = 0.0
        belief = 0.0
        last_visit = 0.0
        pending_response = None     # minute at which the caregiver reaches an open alert
        alert_open = False
        in_fail = False
        had_fail = False
        for t in range(minutes):
            true_exp += 1; belief += 1; last_visit += 1
            # real self repositioning
            if rng.random() < scn.self_reposition_per_hour / 60.0:
                true_exp = 0.0
                if scn.camera and rng.random() >= scn.missed_reposition_prob:
                    belief = 0.0
            # false confirmation: belief resets, truth does not
            if scn.camera and rng.random() < scn.false_confirm_per_hour / 60.0:
                belief = 0.0; false_confirms += 1
            if scn.camera:
                if belief >= cfg.limit_min - cfg.lead_min and not alert_open:
                    alert_open = True; alerts += 1
                    pending_response = t + max(1.0, rng.normal(cfg.response_mean_min, cfg.response_sd_min))
                if alert_open and t >= pending_response:
                    if rng.random() >= scn.missed_visit_prob:
                        true_exp = 0.0; belief = 0.0; last_visit = 0.0; visits += 1
                    else:
                        pending_response = t + 20
                    if belief == 0.0:
                        alert_open = False
                if belief < cfg.limit_min - cfg.lead_min:
                    alert_open = False if belief == 0.0 else alert_open
                if scn.hard_cap_min is not None and last_visit >= scn.hard_cap_min:
                    true_exp = 0.0; belief = 0.0; last_visit = 0.0; visits += 1
            else:
                if last_visit >= cfg.scheduled_fallback_min:
                    if rng.random() >= scn.missed_visit_prob:
                        true_exp = 0.0; last_visit = 0.0; visits += 1
                    else:
                        last_visit = cfg.scheduled_fallback_min - 20     # retry soon
            max_exp = max(max_exp, true_exp)
            over = true_exp > cfg.limit_min + cfg.tolerance_min
            if over and not in_fail:
                fail_eps += 1; in_fail = True; had_fail = True
            if not over:
                in_fail = False
        res_with_fail += int(had_fail)
    per_res_day = fail_eps / (residents * days)
    return dict(scenario=scn.name, failure_episodes=fail_eps, residents_with_a_failure=res_with_fail,
                failures_per_resident_day=round(per_res_day, 4), max_true_exposure_min=round(max_exp, 1),
                alerts=alerts, human_visits=visits, false_confirms=false_confirms)


def standard_scenarios(cfg: SafetyConfig = SafetyConfig()):
    tight = cfg.limit_min + cfg.tolerance_min      # cap that actually bounds exposure to the failure line
    return [
        Scenario("paper: scheduled visits only, no camera", camera=False),
        Scenario("camera, perfect model", camera=True, hard_cap_min=None),
        Scenario("camera, misses 30% of self-repositions", camera=True, missed_reposition_prob=0.30, hard_cap_min=None),
        Scenario("camera, 1 false confirm per 10 h, no cap", camera=True, false_confirm_per_hour=0.1, hard_cap_min=None),
        Scenario("camera, 1 false confirm per 10 h, cap 240 min", camera=True, false_confirm_per_hour=0.1, hard_cap_min=240.0),
        Scenario("camera, 1 false confirm per 10 h, cap = limit + tolerance", camera=True, false_confirm_per_hour=0.1, hard_cap_min=tight),
    ]


def run_all(seed=0, residents=24, days=14, cfg=SafetyConfig()):
    return [simulate(s, cfg, residents, days, seed) for s in standard_scenarios(cfg)]


def sweep_false_confirms(rates=(0.0, 0.01, 0.02, 0.05, 0.1, 0.2), seed=0, residents=24, days=14, cfg=SafetyConfig()):
    """Failures per resident-day as a function of false confirmed turns per hour, for three cap policies.
    Use it to set the false-confirm gate: feed it the rate measured in the recorded test."""
    tight = cfg.limit_min + cfg.tolerance_min
    out = []
    for rate in rates:
        row = {"false_confirms_per_hour": rate}
        for label, cap in (("no_cap", None), ("cap_240", 240.0), ("cap_limit_plus_tolerance", tight)):
            r = simulate(Scenario(label, camera=True, false_confirm_per_hour=rate, hard_cap_min=cap), cfg, residents, days, seed)
            row[label] = r["failures_per_resident_day"]
            row[label + "_visits_per_resident_day"] = round(r["human_visits"] / (residents * days), 2)
        out.append(row)
    base = simulate(Scenario("paper", camera=False), cfg, residents, days, seed)
    return dict(paper_failures_per_resident_day=base["failures_per_resident_day"],
                paper_visits_per_resident_day=round(base["human_visits"] / (residents * days), 2), rows=out)
