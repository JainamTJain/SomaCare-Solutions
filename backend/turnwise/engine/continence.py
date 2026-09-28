"""Discrete-time continence hazard.

Time is split into bins (default 30 minutes). For resident r in bin k:

    p_{r,k} = sigmoid(alpha + u_r + beta · x_{r,k})

Three observation likelihoods match the engineering spec. Scheduling uses the
cumulative probability of at least one void since the last change. During the
learning period a prediction never removes a nurse-scheduled check.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta


def _clip_prob(p: float) -> float:
    return min(max(p, 1e-12), 1 - 1e-12)


def loglik_exact(p: list[float], k: int, bins_before: list[int]) -> float:
    """Bathroom trip or wetness-sensor alert in bin k."""
    return math.log(_clip_prob(p[k])) + sum(
        math.log(_clip_prob(1 - p[j])) for j in bins_before
    )


def loglik_charted_wet(p: list[float], bins: list[int]) -> float:
    """Charted wet at T, previous change at S: at least one void in (S, T]."""
    survival = 1.0
    for j in bins:
        survival *= 1 - p[j]
    return math.log(_clip_prob(1 - survival))


def loglik_charted_dry(p: list[float], bins: list[int]) -> float:
    """Charted dry at T: no void in (S, T]."""
    return sum(math.log(_clip_prob(1 - p[j])) for j in bins)


# Same column order as sim/continence_sim.py features(). Diuretic is index 8.
FEATURE_NAMES = (
    "hours_since",
    "hours_since_sq",
    "sin_hour",
    "cos_hour",
    "sin_2hour",
    "cos_2hour",
    "night",
    "meal",
    "diuretic",
    "continence_category",
)
DIURETIC_INDEX = 8


def continence_features(
    *,
    hours_since: float,
    hour: float,
    night: float,
    meal: float,
    diuretic: float,
    category: float,
) -> list[float]:
    """The hazard feature vector. Diuretic is 1 after a dose inside the window."""
    h = min(max(hours_since, 0.0), 12.0) / 6.0
    ang = 2 * math.pi * (hour % 24) / 24.0
    return [
        h,
        h * h,
        math.sin(ang),
        math.cos(ang),
        math.sin(2 * ang),
        math.cos(2 * ang),
        float(night),
        float(meal),
        1.0 if diuretic else 0.0,
        float(category),
    ]


def cumulative_wet(probs: list[float]) -> float:
    """W(t) = 1 - ∏ (1 - p_k) over bins since the last change."""
    survival = 1.0
    for p in probs:
        survival *= 1 - p
    return 1 - survival


@dataclass
class ScheduledCare:
    due_at: datetime
    wet_probability: float
    source: str  # "model" or "nurse_schedule"
    reason_code: str
    reason_params: dict


def schedule_from_hazard(
    *,
    bin_starts: list[datetime],
    probs: list[float],
    threshold: float,
    lead_min: float,
    nurse_checks: list[datetime] | None = None,
    learning_period: bool = True,
    last_change: datetime | None = None,
) -> list[ScheduledCare]:
    """Earliest time W(t) reaches the nurse's threshold, minus lead time.

    Nurse-scheduled checks are always kept while `learning_period` is true.
    """
    if len(bin_starts) != len(probs):
        raise ValueError("bin_starts and probs must align")
    visits: list[ScheduledCare] = []
    window: list[float] = []
    for start, p in zip(bin_starts, probs):
        if last_change is not None and start <= last_change:
            continue
        window.append(p)
        w = cumulative_wet(window)
        if w >= threshold:
            due = start - timedelta(minutes=lead_min)
            if last_change is not None and due < last_change:
                due = last_change
            visits.append(
                ScheduledCare(
                    due_at=due,
                    wet_probability=w,
                    source="model",
                    reason_code="continence.reason.threshold",
                    reason_params={
                        "wet_probability": round(w, 2),
                        "threshold": threshold,
                    },
                )
            )
            window = []
            last_change = start

    if learning_period:
        for check in nurse_checks or []:
            visits.append(
                ScheduledCare(
                    due_at=check,
                    wet_probability=0.0,
                    source="nurse_schedule",
                    reason_code="continence.reason.nurse_check",
                    reason_params={},
                )
            )
    visits.sort(key=lambda v: v.due_at)
    return visits
