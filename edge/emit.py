"""Post events to the backend. Frames are never part of the payload."""

from __future__ import annotations

import json
import urllib.request


def post_event(base_url: str, token: str, event: dict) -> dict:
    if "frame" in event or "image" in event or "jpeg" in event:
        raise ValueError("events must not carry frames")
    body = json.dumps(event).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/events",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())
