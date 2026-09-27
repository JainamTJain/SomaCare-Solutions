"""When a skin crop is allowed to be considered. It is not a CNA button.

The window is a second person, the lights on, and the body area uncovered.
Signed skin consent is required first. This module does not take a picture,
does not write a file, and does not show a finding to staff.
"""

from __future__ import annotations


def skin_window(
    *,
    consent_signed: bool,
    persons_in_zone: int,
    lights_on: bool,
    keypoint_visibility: float,
    visibility_min: float = 0.75,
) -> dict:
    if not consent_signed:
        return {"open": False, "reason": "consent_missing"}
    if persons_in_zone < 2:
        return {"open": False, "reason": "no_second_person"}
    if not lights_on:
        return {"open": False, "reason": "lights_off"}
    if keypoint_visibility < visibility_min:
        return {"open": False, "reason": "occluded"}
    return {"open": True, "reason": "care_already_happening"}
