"""Quality rules reject a blurry frame and correct a known color card."""

import numpy as np

from skin.quality import ColorCard, color_correct, detect_color_card, quality


def _paint_card(image: np.ndarray) -> None:
    h, w = image.shape[:2]
    y0, x0 = int(h * 0.7), int(w * 0.6)
    image[y0:, x0:] = 0
    inner = image[y0 + 4 : -4, x0 + 4 : -4]
    colors = [
        (68, 82, 115),
        (130, 150, 194),
        (157, 122, 98),
        (67, 108, 87),
        (177, 128, 133),
        (170, 189, 103),
    ]
    rh, rw = inner.shape[:2]
    for index, color in enumerate(colors):
        row, col = divmod(index, 3)
        yy0, yy1 = int(row * rh / 2), int((row + 1) * rh / 2)
        xx0, xx1 = int(col * rw / 3), int((col + 1) * rw / 3)
        inner[yy0:yy1, xx0:xx1] = color


def _card_image(sharp: bool) -> np.ndarray:
    image = np.full((120, 160, 3), 140, dtype=np.uint8)
    if sharp:
        rng = np.random.default_rng(0)
        noise = rng.integers(0, 50, size=image.shape, dtype=np.uint8)
        image = np.clip(image.astype(int) + noise - 25, 0, 255).astype(np.uint8)
    _paint_card(image)
    return image


def test_blurry_frame_fails_and_sharp_card_passes():
    blur = np.full((120, 160, 3), 140, dtype=np.uint8)
    assert quality(blur, sharp_min=80)["ok"] is False
    sharp = _card_image(True)
    report = quality(sharp, sharp_min=5)
    assert report["card"] is True
    assert detect_color_card(sharp) is not None


def test_color_matrix_maps_patches_toward_reference():
    measured = np.array([[10.0, 20.0, 30.0], [40.0, 50.0, 60.0], [5.0, 5.0, 5.0]])
    reference = measured @ np.array([[1.0, 0.1, 0.0], [0.0, 1.0, 0.2], [0.0, 0.0, 1.0]])
    card = ColorCard(measured_rgb=measured, reference_rgb=reference)
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[0, 0] = [30, 20, 10]  # BGR of the first measured RGB
    corrected = color_correct(image, card)
    # The fitted matrix should move that pixel toward the reference RGB.
    got_rgb = corrected[0, 0][::-1].astype(float)
    assert np.linalg.norm(got_rgb - reference[0]) < np.linalg.norm(
        np.array([10, 20, 30]) - reference[0]
    )
