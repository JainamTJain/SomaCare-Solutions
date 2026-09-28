"""Physics-grounded simulator for overhead thermal (e.g. MLX90640, 32x24) readings of
the pelvic region of a covered resident. Produces per-frame ROI means, never images.

Modelled signature (every constant is a placeholder until the bench recordings replace it):
  * Brief-surface temperature rises roughly 0.5-2.0 C within about a minute of voiding
    (warm urine absorbed into the pad; figure from US patent 9545342).
  * A blanket attenuates what an overhead sensor sees (ATTEN).
  * Afterwards evaporation cools the wet area BELOW its old baseline over tens of minutes.
  * Turns, caregiver hands and room drift are the confounders the detector must survive.
"""
from dataclasses import dataclass, field
import numpy as np

CONFIG = dict(
    fps=0.5, base_pelvis=30.5, base_chest=31.0, noise_sd=0.10,
    void_rise=(0.5, 2.0), atten=(0.35, 0.8), rise_s=(20, 90),
    cool_tau_s=(600, 1500), cool_below=(0.2, 0.8),
    turn_step=(-1.0, 1.0), drift_per_h=0.4,
)

@dataclass
class Night:
    t: np.ndarray
    pelvis: np.ndarray
    chest: np.ndarray
    voids: list = field(default_factory=list)
    turns: list = field(default_factory=list)
    hands: list = field(default_factory=list)

def simulate_night(hours=8.0, n_voids=2, n_turns=3, n_hands=1, seed=0, cfg=CONFIG):
    rng = np.random.default_rng(seed)
    t = np.arange(0, hours * 3600, 1.0 / cfg["fps"])
    drift = cfg["drift_per_h"] * hours * np.sin(2 * np.pi * t / (hours * 3600) + rng.uniform(0, 6.28)) / 2
    pel = cfg["base_pelvis"] + drift
    che = cfg["base_chest"] + drift
    voids = sorted(rng.uniform(1800, t[-1] - 1800, n_voids).tolist()) if n_voids else []
    turns = sorted(rng.uniform(600, t[-1] - 600, n_turns).tolist()) if n_turns else []
    for tv in voids:
        A = rng.uniform(*cfg["void_rise"]) * rng.uniform(*cfg["atten"])
        rise = rng.uniform(*cfg["rise_s"]); tau = rng.uniform(*cfg["cool_tau_s"])
        below = rng.uniform(*cfg["cool_below"]) * rng.uniform(*cfg["atten"])
        s = t - tv
        after = np.clip(s - rise, 0, None)
        pel = pel + np.where(s < 0, 0.0, np.where(s <= rise, A * s / rise,
                                                  (A + below) * np.exp(-after / tau) - below))
    for tt in turns:
        pel = pel + np.where(t >= tt, rng.uniform(*cfg["turn_step"]), 0.0)
        che = che + np.where(t >= tt, rng.uniform(*cfg["turn_step"]), 0.0)
    hands = []
    for _ in range(n_hands):
        h0 = rng.uniform(600, t[-1] - 900); h1 = h0 + rng.uniform(60, 300)
        m = (t >= h0) & (t <= h1)
        pel = pel + m * rng.uniform(1.0, 3.0); che = che + m * rng.uniform(0.5, 2.0)
        hands.append((h0, h1))
    pel = pel + rng.normal(0, cfg["noise_sd"], t.size)
    che = che + rng.normal(0, cfg["noise_sd"], t.size)
    return Night(t, pel, che, voids, turns, hands)
