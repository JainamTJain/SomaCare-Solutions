"""Step 1 of the skin pipeline: quality and color correction. Rules, no training."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class ColorCard:
    measured_rgb: np.ndarray  # (n, 3)
    reference_rgb: np.ndarray  # (n, 3)


def gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def quality(img: np.ndarray, sharp_min: float = 80.0) -> dict:
    sharpness = float(cv2.Laplacian(gray(img), cv2.CV_64F).var())
    exposure = float(gray(img).mean()) / 255.0
    card = detect_color_card(img)
    ok = sharpness > sharp_min and 0.2 < exposure < 0.85 and card is not None
    return {
        "ok": ok,
        "sharpness": sharpness,
        "exposure": exposure,
        "card": card is not None,
    }


def detect_color_card(img: np.ndarray) -> ColorCard | None:
    """A printed reference card is a 2x3 block of known patches with a black border.

    The detector looks for that border in the lower-right of the frame. Team
    photos include the card; images without it fail the quality rule.
    """
    if img.ndim != 3 or img.shape[0] < 40 or img.shape[1] < 60:
        return None
    h, w = img.shape[:2]
    region = img[int(h * 0.7) :, int(w * 0.6) :]
    if region.size == 0:
        return None
    gray_region = gray(region)
    # A black border is a run of dark pixels around a brighter interior.
    if gray_region[0, :].mean() > 40 or gray_region[-1, :].mean() > 40:
        return None
    if gray_region[:, 0].mean() > 40 or gray_region[:, -1].mean() > 40:
        return None
    inner = region[4:-4, 4:-4]
    if inner.size == 0:
        return None
    patches = []
    rh, rw = inner.shape[:2]
    for row in range(2):
        for col in range(3):
            y0, y1 = int(row * rh / 2), int((row + 1) * rh / 2)
            x0, x1 = int(col * rw / 3), int((col + 1) * rw / 3)
            patch = inner[y0:y1, x0:x1]
            if patch.size == 0:
                return None
            # OpenCV is BGR. Store RGB to match the reference card.
            bgr = patch.reshape(-1, 3).mean(axis=0)
            patches.append([bgr[2], bgr[1], bgr[0]])
    measured = np.array(patches, dtype=float)
    reference = np.array(
        [
            [115, 82, 68],
            [194, 150, 130],
            [98, 122, 157],
            [87, 108, 67],
            [133, 128, 177],
            [103, 189, 170],
        ],
        dtype=float,
    )
    return ColorCard(measured_rgb=measured, reference_rgb=reference)


def color_correct(img: np.ndarray, card: ColorCard) -> np.ndarray:
    """Fit a 3x3 matrix from the card's measured patches to their known values."""
    matrix, *_ = np.linalg.lstsq(card.measured_rgb, card.reference_rgb, rcond=None)
    flat = img.reshape(-1, 3).astype(float)
    # img is BGR; convert to RGB, apply, convert back.
    rgb = flat[:, ::-1]
    corrected = rgb @ matrix
    corrected = np.clip(corrected, 0, 255)
    bgr = corrected[:, ::-1]
    return bgr.reshape(img.shape).astype(np.uint8)
