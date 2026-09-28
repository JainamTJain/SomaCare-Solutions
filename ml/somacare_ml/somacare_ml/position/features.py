"""Image features for an overhead bed camera. Works on grayscale or color frames (color is reduced to gray).

Mask features describe the shape of whatever differs from an empty-bed background: size, orientation, width along the
body, sideways offset along the body, coarse occupancy. Detail features (edge density, sharpness) help tell whether the
person is covered, because a blanket hides limbs.
"""
import numpy as np
import cv2

GRID = (8, 6)
SLICES = 10
SWAP = {"left": "right", "right": "left"}


def swap_lr(label):
    return SWAP.get(label, label)


def flip_image(img):
    """Mirror the frame. Always pair with swap_lr on the label. A model that skips this learns the wrong side."""
    return np.ascontiguousarray(img[:, ::-1])


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def foreground_mask(img, bg, thr=22, bed_box=None):
    g = cv2.GaussianBlur(_gray(img), (0, 0), 1.2).astype(np.int16)
    b = cv2.GaussianBlur(_gray(bg), (0, 0), 1.2).astype(np.int16)
    m = (np.abs(g - b) > thr).astype(np.uint8)
    if bed_box is not None:
        x, y, w, h = bed_box
        keep = np.zeros_like(m); keep[y:y + h, x:x + w] = 1; m = m * keep
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return m
    keep_id = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (lab == keep_id).astype(np.uint8)


def _hu(m):
    mo = cv2.moments(m, binaryImage=True)
    hu = cv2.HuMoments(mo).flatten()
    return np.sign(hu) * np.log10(np.abs(hu) + 1e-12)


def feature_names():
    names = ["area", "bbox_aspect", "cx", "cy", "orient_cos", "orient_sin", "ecc", "solidity", "edge_density",
             "lap_var", "mean_int", "std_int", "left_right_mass"]
    names += [f"hu{i}" for i in range(7)]
    names += [f"width{i}" for i in range(SLICES)] + [f"offset{i}" for i in range(SLICES)]
    names += [f"grid{i}" for i in range(GRID[0] * GRID[1])]
    return names


FEATURE_DIM = len(feature_names())


def image_features(img, bg, bed_box=(30, 6, 100, 108)):
    g = _gray(img)
    m = foreground_mask(img, bg, bed_box=bed_box)
    x0, y0, bw, bh = bed_box
    f = np.zeros(FEATURE_DIM, np.float32)
    area = float(m.sum())
    if area < 40:                       # nothing there: an empty bed
        return f
    ys, xs = np.nonzero(m)
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = bx1 - bx0 + 1, by1 - by0 + 1
    mo = cv2.moments(m, binaryImage=True)
    cx, cy = mo["m10"] / mo["m00"], mo["m01"] / mo["m00"]
    mu20, mu02, mu11 = mo["mu20"] / mo["m00"], mo["mu02"] / mo["m00"], mo["mu11"] / mo["m00"]
    theta = 0.5 * np.arctan2(2 * mu11, mu20 - mu02)
    common = np.sqrt(max((mu20 - mu02) ** 2 + 4 * mu11 ** 2, 0))
    l1, l2 = (mu20 + mu02 + common) / 2, (mu20 + mu02 - common) / 2
    ecc = float(np.sqrt(max(1 - l2 / max(l1, 1e-6), 0)))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
    solidity = area / max(cv2.contourArea(hull), 1.0)
    edges = cv2.Canny(g, 40, 110)
    inside = cv2.dilate(m, np.ones((5, 5), np.uint8)).astype(bool)
    edge_density = float(edges[inside].mean() / 255.0)
    lap_var = float(cv2.Laplacian(g, cv2.CV_32F)[inside].var())
    vals = g[m.astype(bool)].astype(np.float32)
    mid = bx0 + w / 2
    left_mass = float(m[:, :int(cx)].sum()); right_mass = area - left_mass
    i = 0
    base = [area / (bw * bh), w / max(h, 1), (cx - x0) / bw, (cy - y0) / bh, np.cos(2 * theta), np.sin(2 * theta), ecc,
            solidity, edge_density, np.log1p(lap_var), vals.mean() / 255, vals.std() / 255,
            (left_mass - right_mass) / area]
    f[:len(base)] = base
    i = len(base)
    f[i:i + 7] = _hu(m); i += 7
    edges_y = np.linspace(by0, by1 + 1, SLICES + 1).astype(int)
    for k in range(SLICES):
        sl = m[edges_y[k]:max(edges_y[k + 1], edges_y[k] + 1), :]
        cols = np.nonzero(sl.any(axis=0))[0]
        f[i + k] = (cols.max() - cols.min() + 1) / bw if len(cols) else 0.0
        f[i + SLICES + k] = ((cols.mean() - (x0 + bw / 2)) / bw) if len(cols) else 0.0
    i += 2 * SLICES
    crop = m[y0:y0 + bh, x0:x0 + bw].astype(np.float32)
    gy, gx = GRID[1], GRID[0]
    cell = cv2.resize(crop, (gx, gy), interpolation=cv2.INTER_AREA)
    f[i:i + gx * gy] = cell.flatten()
    return f
