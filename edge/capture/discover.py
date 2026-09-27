"""Decide whether a discovered camera can be read locally.

This does not scan a network by itself. A live ONVIF sweep is a site visit.
A vendor cloud address, including SafelyYou or Inspiren, is not usable:
Sorety cannot read another company's stream. No infrared night mode is not usable.
"""

from __future__ import annotations

CLOUD_MARKERS = ("safelyyou", "inspiren", "tplinkcloud", "amazonaws", "googleapis")


def classify_camera(device: dict) -> dict:
    blob = " ".join(
        str(device.get(key) or "")
        for key in ("name", "vendor", "xaddr", "rtsp")
    ).lower()
    rtsp = str(device.get("rtsp") or "")
    infrared = bool(device.get("infrared"))
    cloud = any(marker in blob for marker in CLOUD_MARKERS) or not rtsp.startswith(("rtsp://", "rtsps://"))
    if cloud:
        reason = "cloud_or_no_local_rtsp"
        usable = False
    elif not infrared:
        reason = "no_infrared"
        usable = False
    else:
        reason = "local_rtsp_infrared"
        usable = True
    return {
        "name": device.get("name"),
        "rtsp": rtsp or None,
        "infrared": infrared,
        "usable": usable,
        "reason": reason,
    }


def compatibility_report(devices: list[dict], *, continence_note: str | None = None, live_scan: bool = False) -> dict:
    rows = [classify_camera(device) for device in devices]
    return {
        "live_scan": live_scan,
        "usable_count": sum(1 for row in rows if row["usable"]),
        "cameras": rows,
        "not_usable": [row for row in rows if not row["usable"]],
        "continence_program_noted": continence_note,
    }
