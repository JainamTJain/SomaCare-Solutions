"""Sensor-agnostic features so the SAME classifier code runs on a pressure mat (PMD),
LWIR thermal (SLP, downsampled to the MLX90640's 24x32) or our own overhead recordings.
Left/right asymmetry is the whole game, so features keep the lateral axis."""
import numpy as np

def to_grid(frame, out_hw=(24, 32)):
    """Block-average resize without extra deps. frame: (H, W) any float."""
    H, W = frame.shape; h, w = out_hw
    ys = np.linspace(0, H, h + 1).astype(int); xs = np.linspace(0, W, w + 1).astype(int)
    return np.array([[frame[ys[i]:ys[i+1], xs[j]:xs[j+1]].mean() for j in range(w)] for i in range(h)],
                    dtype=np.float32)

def frame_features(frame, lateral_axis=1):
    f = frame.astype(np.float32)
    f = f - np.percentile(f, 10)
    f = np.clip(f, 0, None); s = f.sum() + 1e-6; p = f / s
    g = to_grid(p, (16, 8) if lateral_axis == 1 else (8, 16)).ravel()
    lat = p.sum(axis=1 - lateral_axis)                    # lateral profile
    idx = np.arange(lat.size) / max(lat.size - 1, 1)
    c = (lat * idx).sum(); spread = np.sqrt((lat * (idx - c) ** 2).sum())
    skew = (lat * (idx - c) ** 3).sum() / (spread ** 3 + 1e-6)
    occ = (p > p.max() * 0.2).mean()                      # contact/hot area fraction
    return np.concatenate([g, [c, spread, skew, occ]]).astype(np.float32)

def featurize(frames, lateral_axis=1):
    return np.stack([frame_features(f, lateral_axis) for f in frames])
