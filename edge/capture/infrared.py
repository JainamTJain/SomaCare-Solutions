"""Night cameras on this product are near-infrared.

A color frame has chroma. An infrared frame, or a mono frame from an IR
sensor, does not. Color frames are rejected so a hallway webcam cannot be
treated as the night camera. The frame itself is never stored.
"""

from __future__ import annotations

import numpy as np

# Mean HSV saturation above this is a color camera. 0.08 leaves a little
# sensor noise and still rejects a tinted webcam image.
SATURATION_MAX = 0.08


def frame_is_infrared(frame: np.ndarray, saturation_max: float = SATURATION_MAX) -> tuple[bool, float]:
    """Return (accepted, mean_saturation). The caller discards `frame`."""
    if frame is None:
        return False, 1.0
    if frame.ndim == 2 or (frame.ndim == 3 and frame.shape[2] == 1):
        return True, 0.0
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    saturation = float(hsv[:, :, 1].mean()) / 255.0
    return saturation <= saturation_max, saturation
