"""Descriptive patterns for a nurse. A pattern is not an order: nothing here changes a plan.
Every result carries its sample size and a p-value, and small samples return nothing."""
import numpy as np
from math import comb

MIN_N = 15


def _binom_sf(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p), exact."""
    return float(sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1)))


def hour_cluster(change_hours, window_h=3, alpha=0.01, min_n=MIN_N):
    """Do changes cluster in one window of the day? change_hours are hours of day in [0, 24)."""
    h = np.asarray(change_hours, float) % 24
    n = len(h)
    if n < min_n:
        return None
    best = None
    for start in range(24):
        inside = int((((h - start) % 24) < window_h).sum())
        p = _binom_sf(inside, n, window_h / 24.0) * 24          # Bonferroni over 24 windows
        if best is None or p < best[2]:
            best = (start, inside, p)
    start, inside, p = best
    expected = n * window_h / 24.0
    if p < alpha and inside >= 1.5 * expected:
        return dict(kind="time_of_day", n=n, start_hour=start, window_h=window_h, count=inside,
                    expected=round(expected, 1), p_value=min(p, 1.0),
                    text=(f"A pattern, not an order: {inside} of {n} changes ({inside / n:.0%}) happened between "
                          f"{start:02d}:00 and {(start + window_h) % 24:02d}:00, against about {expected:.0f} expected."))
    return None


def meals_are_regular(meal_min, max_distinct_slots=6):
    """True when meals happen at the same times every day. Then 'after a meal' and 'time of day' are the same
    thing and the data cannot tell them apart."""
    slots = {int((m % 1440) // 30) for m in meal_min}
    return len(slots) <= max_distinct_slots


def meal_pattern(change_min, meal_min, within_min=90, n_perm=2000, alpha=0.01, min_n=MIN_N, seed=0):
    """Do changes happen soon after a meal or drink round? Minutes are absolute (any consistent origin).
    Only valid when meal times vary. The null draws each meal's time independently and uniformly over the day."""
    ch = np.sort(np.asarray(change_min, float)); ml = np.sort(np.asarray(meal_min, float))
    n = len(ch)
    if n < min_n or len(ml) < 6:
        return None
    if meals_are_regular(ml):
        return dict(kind="confounded", n=n, text=("Meals happen at regular times, so an after-meal pattern cannot be "
                                                  "told apart from a time-of-day pattern. Only the time-of-day view applies."))

    def frac(meals):
        meals = np.sort(meals)
        idx = np.searchsorted(meals, ch, side="right") - 1
        ok = idx >= 0
        d = np.full(n, np.inf)
        d[ok] = ch[ok] - meals[idx[ok]]
        return float(np.mean(d <= within_min))

    obs = frac(ml)
    rng = np.random.default_rng(seed)
    span_lo, span_hi = float(ch.min()), float(ch.max())
    null = np.array([frac(rng.uniform(span_lo, span_hi, len(ml))) for _ in range(n_perm)])
    p = float((1 + (null >= obs).sum()) / (1 + n_perm))
    if p < alpha and obs >= 1.5 * max(null.mean(), 1e-9):
        return dict(kind="after_meal", n=n, within_min=within_min, fraction=round(obs, 3),
                    expected=round(float(null.mean()), 3), p_value=p,
                    text=(f"A pattern, not an order: {obs:.0%} of {n} changes happened within {within_min} minutes "
                          f"after a meal or drink round, against about {null.mean():.0%} expected by chance."))
    return None


def detect(change_min, meal_min):
    """All patterns that pass, plus a note when meals are too regular to separate from time of day."""
    hours = [(m % 1440) / 60.0 for m in change_min]
    out = [hour_cluster(hours), meal_pattern(change_min, meal_min)]
    return [o for o in out if o]
