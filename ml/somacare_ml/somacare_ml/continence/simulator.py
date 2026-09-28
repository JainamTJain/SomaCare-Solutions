"""Synthetic residents with KNOWN parameters, used to prove the code learns and to test the gates.
It says nothing about real residents. Clinical value is only established with pilot data."""
from dataclasses import dataclass
import numpy as np
from .features import D, features_for_bins
from .model import Observation, _sigmoid
from ..config import ContinenceConfig

CFG = ContinenceConfig()


def true_beta(base_median_h=3.0, night_effect=0.5, diuretic_effect=0.7):
    """A plausible true hazard: rises with hours since a change, higher at night, higher after a diuretic."""
    from .model import cold_start_beta
    b = cold_start_beta(base_median_h, CFG.bin_min).copy()
    b[1] = 0.10; b[2] = 0.05        # risk grows with time on the pad
    b[5] = 0.25; b[6] = 0.10        # mild daily rhythm
    b[9] = night_effect
    b[10] = diuretic_effect
    return b


@dataclass
class SimResident:
    rid: str
    u: float
    diuretic_bins: tuple
    meal_bins: tuple
    spike: float = 0.0     # extra early-morning hazard the fitted model cannot represent exactly (misspecification test)


def make_resident(rid, rng, days, sigma_u=0.5, per_day=48, spike=0.0):
    u = rng.normal(0, sigma_u)
    meals = tuple(d * per_day + h * 2 for d in range(days) for h in (8, 12, 18))
    diur = tuple(d * per_day + 2 * 9 for d in range(days))       # a morning diuretic
    return SimResident(rid, float(u), diur, meals, spike)


def first_void_after(res, beta, change_bin, rng, horizon=48 * 2):
    """Sample the first void bin after a change from the true hazard. Returns bin or None."""
    bins = np.arange(change_bin + 1, change_bin + 1 + horizon)
    X = features_for_bins(bins, change_bin, CFG.bin_min, diuretic_bins=res.diuretic_bins, meal_bins=res.meal_bins)
    hod = (bins % 48) / 2.0
    extra = res.spike * ((hod >= 5) & (hod < 7))
    p = _sigmoid(X @ beta + res.u + extra)
    hit = rng.random(len(p)) < p
    k = np.nonzero(hit)[0]
    return int(bins[k[0]]) if len(k) else None


def simulate_charted(res, beta, days, rng, check_every_bins=6, per_day=48):
    """Training data as a facility produces today: a check every few hours. Wet means change (episode ends),
    dry means the episode continues. Returns observations (interval censored, no sensor)."""
    obs = []
    end = days * per_day
    change = 0
    void = first_void_after(res, beta, change, rng)
    last = change
    t = change + check_every_bins
    while t < end:
        if void is not None and void <= t:
            obs.append(Observation(res.rid, "wet", last, t, change, res.diuretic_bins, res.meal_bins))
            change = t; last = t
            void = first_void_after(res, beta, change, rng)
        else:
            obs.append(Observation(res.rid, "dry", last, t, change, res.diuretic_bins, res.meal_bins))
            last = t
        t += check_every_bins
    return obs


def simulate_sensor(res, beta, days, rng, response_bins=1, per_day=48):
    """Data with a wetness sensor: the first void is seen exactly, and a change follows shortly after."""
    obs = []
    end = days * per_day
    change = 0
    while change < end:
        void = first_void_after(res, beta, change, rng)
        if void is None or void >= end:
            break
        obs.append(Observation(res.rid, "exact", change, void, change, res.diuretic_bins, res.meal_bins))
        change = void + response_bins
    return obs


def run_policy(model, res, beta, days, rng, visits_per_day=None, fixed_every_bins=None, q=None, per_day=48,
               sensor=False):
    """Compare when a check is scheduled. Returns dict with visits, voids and how many were handled within 60 min.
    Fixed policy: visit every `fixed_every_bins`. Model policy: next visit when the modelled probability of a void
    since the last visit reaches q. A wet pad found at a visit is changed (new episode)."""
    end = days * per_day
    change = 0
    last = 0
    void = first_void_after(res, beta, change, rng)
    t = 0
    visits = 0
    handled = 0
    voids = 0
    delays = []
    while True:
        if fixed_every_bins is not None:
            t = last + fixed_every_bins
        else:
            t, _ = model.next_check_bin(res.rid, last, change, threshold=q, horizon_bins=per_day,
                                        diuretic_bins=res.diuretic_bins, meal_bins=res.meal_bins)
        if t >= end:
            break
        visits += 1
        if void is not None and void <= t:
            voids += 1
            delay_min = (t - void) * CFG.bin_min
            delays.append(delay_min)
            if delay_min <= 60:
                handled += 1
            change = t
            void = first_void_after(res, beta, change, rng)
        last = t
    return dict(visits=visits, voids=voids, handled=handled, delays=delays)
