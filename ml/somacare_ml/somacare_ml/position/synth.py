"""Synthetic overhead bed scenes. Used ONLY to prove the pipeline runs end to end and to unit test it.
Results on these images are not evidence about real people. Real accuracy comes from real recordings."""
import numpy as np
import cv2

W, H = 160, 120
BED = (30, 6, 100, 108)          # x, y, w, h
POSITIONS = ["back", "left", "right", "sitting", "out_of_bed"]
COVERS = ["none", "sheet", "blanket"]


def _base(rng, tone_bed=170):
    img = np.full((H, W), 95, np.float32)
    x, y, w, h = BED
    img[y:y + h, x:x + w] = tone_bed
    gx = np.linspace(-1, 1, W)[None, :] * rng.uniform(-8, 8)
    gy = np.linspace(-1, 1, H)[:, None] * rng.uniform(-8, 8)
    return img + gx + gy


def _ell(m, c, ax, ang=0, val=255):
    cv2.ellipse(m, (int(c[0]), int(c[1])), (max(int(ax[0]), 1), max(int(ax[1]), 1)), ang, 0, 360, val, -1)


def person_mask(position, rng, s=1.0):
    m = np.zeros((H, W), np.uint8)
    cx = 80
    if position == "back":
        _ell(m, (cx, 22), (9 * s, 9 * s)); _ell(m, (cx, 52), (18 * s, 26 * s))
        for sx in (-1, 1):
            _ell(m, (cx + sx * 26 * s, 52), (5 * s, 22 * s), sx * 8)
            _ell(m, (cx + sx * 7 * s, 92), (7 * s, 20 * s))
    elif position in ("left", "right"):
        sg = -1 if position == "left" else 1
        _ell(m, (cx + sg * 3, 22), (8 * s, 9 * s)); _ell(m, (cx + sg * 2, 52), (12 * s, 27 * s))
        _ell(m, (cx + sg * 14 * s, 50), (4 * s, 16 * s), sg * 18)                 # arm forward
        _ell(m, (cx + sg * 15 * s, 84), (6 * s, 15 * s), sg * 25)                 # thigh, knee bent out
        _ell(m, (cx + sg * 6 * s, 100), (5 * s, 11 * s), -sg * 20)                # shin
    elif position == "sitting":
        _ell(m, (cx, 24), (9 * s, 9 * s)); _ell(m, (cx, 46), (19 * s, 18 * s))
        for sx in (-1, 1):
            _ell(m, (cx + sx * 9 * s, 78), (6 * s, 16 * s))
    return m


def render(position, cover="none", person=0, rng=None):
    rng = rng or np.random.default_rng()
    prng = np.random.default_rng(1000 + person)
    s = float(prng.uniform(0.85, 1.15))
    tone = float(prng.uniform(55, 200))
    img = _base(rng, tone_bed=170)
    if position != "out_of_bed":
        m = person_mask(position, rng, s)
        ang = rng.uniform(-6, 6); dx, dy = rng.uniform(-5, 5), rng.uniform(-4, 4)
        M = cv2.getRotationMatrix2D((80, 60), ang, 1.0); M[:, 2] += (dx, dy)
        m = cv2.warpAffine(m, M, (W, H))
        body = m.astype(np.float32) / 255.0
        limb_detail = cv2.GaussianBlur(body, (0, 0), 0.8)
        person_img = tone + 10 * rng.standard_normal((H, W)).astype(np.float32) * 0.3
        if cover == "none":
            a = limb_detail
        elif cover == "sheet":
            a = cv2.GaussianBlur(body, (0, 0), 2.2) * 0.72
        else:  # thick blanket: a soft lump, limbs lost
            a = cv2.GaussianBlur(body, (0, 0), 5.5) * 0.42
            a = a * (1 + 0.15 * np.sin(np.linspace(0, 9, W))[None, :])
        img = img * (1 - a) + person_img * a
    img = img * rng.uniform(0.85, 1.15) + rng.normal(0, 5, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def empty_background(rng=None):
    rng = rng or np.random.default_rng(0)
    return np.median(np.stack([render("out_of_bed", "none", 0, rng) for _ in range(9)]), axis=0).astype(np.uint8)


def make_dataset(n_people=8, per_cell=14, covers=COVERS, positions=POSITIONS, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for p in range(n_people):
        for c in covers:
            for pos in positions:
                for _ in range(per_cell):
                    out.append((render(pos, c, p, rng), pos, p, c))
    return out
