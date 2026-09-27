"""Gate 1: can a near-infrared camera name the side of a body under covers?

No trial in this repository was filmed. `live_status` stays `not_run`.
`score_trials` is the scorer for a future labeled set. It is built to
notice a cliff and a confident wrong label, not to assume a smooth drop
from uncovered to blanket.

A failed gate means the product claim narrows to movement and stillness.
It does not mean a bed sensor exists here.
"""

from __future__ import annotations

from dataclasses import dataclass

COVERS = ("none", "sheet", "blanket")
RESETTING = {"likely", "confirmed"}


@dataclass(frozen=True)
class Trial:
    cover: str
    truth: str
    predicted: str | None
    confidence: float
    fusion: str


def live_status() -> dict:
    """The only status this build is allowed to report."""
    return {
        "status": "not_run",
        "covers": {"none": "not_run", "sheet": "not_run", "blanket": "not_run"},
        "false_confirmed_rate": None,
        "hardware_hours": 0,
        "per_side_under_blanket": "not_claimed",
        "note": (
            "Near-infrared reflects off fabric. No uncovered, sheet, or blanket "
            "trial has been scored. A side-of-body label under a cover does not reset the pressure timer."
        ),
        "if_fail": (
            "Narrow the claim to movement and stillness. Do not ship a per-side pressure budget from the camera."
        ),
    }


def _cover_row(rows: list[Trial], *, min_conf: float) -> dict:
    n = len(rows)
    if n == 0:
        return {
            "trials": 0,
            "status": "not_run",
            "agreement": None,
            "uncertain_rate": None,
            "false_confirmed_rate": None,
            "false_confirmed": 0,
        }
    agreed = 0
    uncertain = 0
    false_confirmed = 0
    for trial in rows:
        if trial.fusion == "uncertain":
            uncertain += 1
        resetting = trial.fusion in RESETTING and trial.confidence >= min_conf
        if resetting and trial.predicted == trial.truth:
            agreed += 1
        elif resetting and trial.predicted != trial.truth:
            false_confirmed += 1
    return {
        "trials": n,
        "status": "scored",
        "agreement": round(agreed / n, 4),
        "uncertain_rate": round(uncertain / n, 4),
        "false_confirmed_rate": round(false_confirmed / n, 4),
        "false_confirmed": false_confirmed,
    }


def score_trials(
    trials: list[Trial],
    *,
    min_conf: float = 0.7,
    false_confirmed_cap: float = 0.02,
    agreement_min: float = 0.80,
    cliff_drop: float = 0.15,
) -> dict:
    """Score labeled trials. An empty list is `not_run`, never a pass."""
    if not trials:
        report = live_status()
        report["by_cover"] = {cover: _cover_row([], min_conf=min_conf) for cover in COVERS}
        report["architecture"] = "withheld"
        return report
    unknown = sorted({trial.cover for trial in trials if trial.cover not in COVERS})
    if unknown:
        raise ValueError(f"unknown cover {unknown[0]}")
    by_cover = {cover: _cover_row([trial for trial in trials if trial.cover == cover], min_conf=min_conf) for cover in COVERS}
    reasons = []
    unsafe = False
    for cover, row in by_cover.items():
        if row["status"] != "scored":
            continue
        if row["false_confirmed_rate"] > false_confirmed_cap:
            unsafe = True
            reasons.append(f"{cover}_false_confirmed")
        elif row["agreement"] < agreement_min:
            reasons.append(f"{cover}_agreement")
    none_row = by_cover["none"]
    blanket_row = by_cover["blanket"]
    cliff = False
    if none_row["agreement"] is not None and blanket_row["agreement"] is not None:
        if none_row["agreement"] - blanket_row["agreement"] >= cliff_drop:
            cliff = True
            reasons.append("blanket_cliff")
    complete = all(by_cover[cover]["status"] == "scored" for cover in COVERS)
    if not reasons and complete and not cliff:
        status = "pass"
        architecture = "vision_per_side"
    elif not reasons and not complete:
        status = "not_run"
        architecture = "withheld"
    else:
        status = "fail"
        architecture = "movement_stillness_only"
    return {
        "status": status,
        "architecture": architecture,
        "unsafe_confirmed": unsafe,
        "cliff": cliff,
        "reasons": reasons,
        "by_cover": by_cover,
        "per_side_under_blanket": "claimed" if status == "pass" else "not_claimed",
        "hardware_hours": 0,
        "note": (
            "Scored from labeled trials supplied by the caller. "
            "This function does not read a camera."
        ),
        "if_fail": live_status()["if_fail"],
    }
