import numpy as np
from scipy.optimize import minimize_scalar


def apply_temperature(P, T):
    """Soften (T > 1) or sharpen (T < 1) probabilities. P has shape (n, classes)."""
    L = np.log(np.clip(P, 1e-9, 1.0)) / T
    L -= L.max(axis=1, keepdims=True)
    E = np.exp(L)
    return E / E.sum(axis=1, keepdims=True)


def fit_temperature(P, y_idx):
    """Choose T by minimizing negative log likelihood on out-of-fold predictions."""
    def nll(T):
        Q = apply_temperature(P, T)
        return -np.mean(np.log(np.clip(Q[np.arange(len(y_idx)), y_idx], 1e-9, 1)))
    r = minimize_scalar(nll, bounds=(0.3, 5.0), method="bounded")
    return float(r.x)


def ece_top_label(P, y_idx, bins=10):
    conf = P.max(axis=1); pred = P.argmax(axis=1); ok = (pred == y_idx).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        m = (conf > a) & (conf <= b)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - ok[m].mean())
    return float(e)
