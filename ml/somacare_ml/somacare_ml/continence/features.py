"""Features for the wetness hazard model. Time is divided into bins (default 30 minutes).

x for bin k, when the current pad was put on at bin s:
  intercept
  hours since the change, as a piecewise-linear basis (hinges at 0, 2, 4, 6 hours), capped
  time of day, sine and cosine at 24 and 12 hours
  night flag
  diuretic given in the last 6 hours
  hours since the last meal or drink round, capped at 6
"""
import numpy as np

FEATURE_NAMES = ["intercept", "h_since", "h_since_gt2", "h_since_gt4", "h_since_gt6",
                 "sin24", "cos24", "sin12", "cos12", "night", "diuretic6h", "h_since_meal"]
D = len(FEATURE_NAMES)


def features_for_bins(bins, start_bin, bin_min=30, night_start_h=22.0, night_end_h=6.0,
                      diuretic_bins=None, meal_bins=None):
    """bins: iterable of global bin indices (bin 0 = midnight of day 0). Returns (len(bins), D)."""
    bins = np.asarray(list(bins), dtype=int)
    per_day = int(24 * 60 / bin_min)
    hours_since = np.minimum((bins - start_bin) * bin_min / 60.0, 12.0)
    hod = ((bins % per_day) * bin_min / 60.0)
    ang24 = 2 * np.pi * hod / 24.0
    night = ((hod >= night_start_h) | (hod < night_end_h)).astype(float)
    X = np.zeros((len(bins), D))
    X[:, 0] = 1.0
    X[:, 1] = hours_since
    X[:, 2] = np.maximum(hours_since - 2, 0)
    X[:, 3] = np.maximum(hours_since - 4, 0)
    X[:, 4] = np.maximum(hours_since - 6, 0)
    X[:, 5] = np.sin(ang24); X[:, 6] = np.cos(ang24)
    X[:, 7] = np.sin(2 * ang24); X[:, 8] = np.cos(2 * ang24)
    X[:, 9] = night
    if diuretic_bins is not None and len(diuretic_bins):
        d = np.asarray(sorted(diuretic_bins), dtype=int)
        span = int(6 * 60 / bin_min)
        idx = np.searchsorted(d, bins, side="right") - 1
        ok = idx >= 0
        X[ok, 10] = ((bins[ok] - d[idx[ok]]) <= span).astype(float)
    if meal_bins is not None and len(meal_bins):
        m = np.asarray(sorted(meal_bins), dtype=int)
        idx = np.searchsorted(m, bins, side="right") - 1
        ok = idx >= 0
        X[ok, 11] = np.minimum((bins[ok] - m[idx[ok]]) * bin_min / 60.0, 6.0)
        X[~ok, 11] = 6.0
    else:
        X[:, 11] = 6.0
    return X
