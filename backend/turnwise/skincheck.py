"""Image quality rules and encrypted storage for skin captures.

Skin and wound image analysis is off the near-term roadmap. It is a research
track with no date. Captures stay encrypted and shown_to_staff stays false.
No frame is written unencrypted. Nothing here is a diagnosis.
"""

from __future__ import annotations

import os
import uuid

import cv2
import numpy as np
from cryptography.fernet import Fernet

from turnwise.config import load_config
from turnwise.imaging import quality
from turnwise.paths import data_dir

STORE = data_dir() / "skin"


def _fernet() -> Fernet:
    key = os.environ.get("TURNWISE_SKIN_KEY")
    if not key:
        # Dev-only key file, created locally and gitignored via var/.
        path = data_dir() / "skin.key"
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
