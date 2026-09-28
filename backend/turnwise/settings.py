"""Environment names. SOMACARE_* wins. TURNWISE_* still works."""

from __future__ import annotations

import os


def setting(suffix: str, default: str | None = None) -> str | None:
    """Read SOMACARE_<suffix>, then TURNWISE_<suffix>."""
    for key in (f"SOMACARE_{suffix}", f"TURNWISE_{suffix}"):
        value = os.environ.get(key)
        if value:
            return value
    return default


def demo_mode() -> bool:
    raw = os.environ.get("DEMO_MODE", os.environ.get("SOMACARE_DEMO_MODE", "false"))
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def public_config() -> dict:
    facility = os.environ.get("FACILITY_NAME") or os.environ.get("SOMACARE_FACILITY_NAME") or None
    logo = os.environ.get("LOGO_URL") or os.environ.get("SOMACARE_LOGO_URL") or None
    return {
        "demoMode": demo_mode(),
        "facilityName": facility or None,
        "logoUrl": logo or None,
    }


# Known demo PINs. They are not stored in the database, and the roster
# returns them only while demo mode is on.
DEMO_PINS = {
    "Maria Santos": "2468",
    "Joy Reyes": "1357",
    "Devon Brooks": "8024",
    "Grace Adeyemi": "5913",
    "Sam Patel": "4470",
    "Riley Chen": "9130",
    "Helen Cho": "6204",
}
