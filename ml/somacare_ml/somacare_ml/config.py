"""Every constant lives here. Values are starting hypotheses, not clinical facts.
A nurse or authorized clinician must approve anything that changes a care limit."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TurnConfig:
    hold_s: float = 30.0          # a new position must hold this long before it counts
    min_conf: float = 0.70        # mean confidence needed to confirm
    gap_s: float = 120.0          # silence longer than this means the feed dropped
    assisted_persons: int = 2     # persons in the bed zone that make a change a caregiver turn
    unknown_labels: tuple = ("unknown",)


@dataclass(frozen=True)
class SafetyConfig:
    limit_min: float = 120.0      # care-plan interval for the demo resident
    lead_min: float = 15.0        # alert this long before the limit
    tolerance_min: float = 30.0   # exposure beyond limit plus this counts as a failure
    response_mean_min: float = 8.0
    response_sd_min: float = 4.0
    hard_visit_cap_min: float = 240.0   # a human must visit at least this often, whatever the camera says
    scheduled_fallback_min: float = 120.0


@dataclass(frozen=True)
class ContinenceConfig:
    bin_min: int = 30
    threshold: float = 0.55       # wet probability that triggers a check (nurse approved)
    lead_min: int = 15
    prior_precision: float = 4.0  # how strongly the nurse's schedule anchors the first estimate
    sigma_u: float = 0.5          # spread of resident-level differences
    min_events_to_leave_learning: int = 10
