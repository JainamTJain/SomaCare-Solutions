"""Image quality rules and encrypted storage for skin captures.

The visible-injury classifier stays in shadow mode: captures are stored with
shown_to_staff false until the PIID and pilot gates in the spec are met.
No frame is written unencrypted.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import cv2
import numpy as np
from cryptography.fernet import Fernet

from turnwise.config import load_config

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "var" / "skin"


def _fernet() -> Fernet:
    key = os.environ.get("TURNWISE_SKIN_KEY")
    if not key:
        # Dev-only key file, created locally and gitignored via var/.
        path = ROOT / "var" / "skin.key"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            key = path.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            path.write_text(key)
    return Fernet(key.encode() if isinstance(key, str) else key)


def assess_upload(raw: bytes) -> dict:
    config = load_config()
    arr = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return {
            "ok": False,
            "quality": 0.0,
            "model_flag": "unreadable",
            "model_version": "skin-shadow-v0",
            "image_ref": _store(raw),
        }
    from skin.quality import quality

    report = quality(image, sharp_min=config.sharp_min)
    return {
        "ok": bool(report["ok"]),
        "quality": float(report["sharpness"]),
        "model_flag": "shadow_not_deployed",
        "model_version": "skin-shadow-v0",
        "image_ref": _store(raw),
    }


def _store(raw: bytes) -> str:
    STORE.mkdir(parents=True, exist_ok=True)
    ref = f"{uuid.uuid4().hex}.bin"
    token = _fernet().encrypt(raw)
    (STORE / ref).write_bytes(token)
    return ref
