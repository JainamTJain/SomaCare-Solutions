"""Synthetic residents with known continence parameters.

The simulator proves the likelihood and the scheduler. It says nothing about
real residents. Clinical value is established only by pilot data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from turnwise.engine.continence import loglik_charted_dry, loglik_charted_wet


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -20, 20)
    return 1.0 / (1.0 + np.exp(-z))


def features(hours_since: float, hour: float, night: float, meal: float, diuretic: float, cat: float) -> np.ndarray:
    h = min(hours_since, 12.0) / 6.0
    meal_s = min(meal, 6.0) / 6.0
    ang = 2 * math.pi * (hour / 24.0)
    return np.array(
        [h, h * h, math.sin(ang), math.cos(ang), math.sin(2 * ang), math.cos(2 * ang), night, meal_s, diuretic, cat],
        dtype=float,
    )


# Truth used by the generator. Unused spline terms are genuinely zero.
TRUE_ALPHA = -3.05
TRUE_BETA = np.array([0.85, 0.0, 0.95, 0.2, 0.0, 0.0, 1.15, 0.05, 0.9, 0.2])
N_FEATURES = 10


@dataclass
class ContinenceReport:
    ece: float
    catch_model: float
    catch_fixed: float
    relative_improvement: float
    beta_mae: float
    alpha: float
    n_bins: int
    charted_loglik_finite: bool

    @property
    def passed(self) -> bool:
        return (
            self.ece < 0.05
            and self.relative_improvement >= 0.20
            and self.beta_mae < 0.45
            and self.charted_loglik_finite
        )


def _simulate(n_residents: int, n_days: int, seed: int):
    rng = np.random.default_rng(seed)
    u = rng.normal(0, 0.35, size=n_residents)
    rows_x = []
    rows_y = []
    rows_r = []
    rows_t = []  # minutes from start
    charted = []
    for r in range(n_residents):
        hours_since = 0.0
        meal = 1.0
        cat = float(rng.uniform(0, 1))
        # Regime: 0 exact, 1 charted checks, 2 sparse exact events.
        regime = r % 3
        interval_bins: list[int] = []
        local_ps: list[float] = []
        for day in range(n_days):
            for bin_index in range(48):
                hour = bin_index / 2.0
                night = 1.0 if hour >= 21 or hour < 7 else 0.0
                diuretic = 1.0 if 8 <= hour < 14 and r % 2 == 0 else 0.0
                x = features(hours_since, hour, night, meal, diuretic, cat)
                eta = TRUE_ALPHA + u[r] + float(x @ TRUE_BETA)
                p = float(_sigmoid(np.array([eta]))[0])
                y = 1 if rng.random() < p else 0
                minute = (day * 48 + bin_index) * 30
                rows_x.append(x)
                rows_y.append(y)
                rows_r.append(r)
                rows_t.append(minute)
                if regime == 1:
                    interval_bins.append(len(rows_y) - 1)
                    local_ps.append(p)
                    if len(interval_bins) == 4:
                        wet = any(rows_y[i] == 1 for i in interval_bins)
                        charted.append((list(interval_bins), wet))
                        interval_bins = []
                        local_ps = []
                hours_since = 0.0 if y else hours_since + 0.5
                meal = 0.0 if bin_index % 8 == 0 else meal + 0.5
    return {
        "X": np.vstack(rows_x),
        "y": np.array(rows_y, dtype=float),
        "r": np.array(rows_r, dtype=int),
        "t": np.array(rows_t, dtype=float),
        "u": u,
        "charted": charted,
        "n_residents": n_residents,
    }


def _fit(data: dict, train_mask: np.ndarray) -> np.ndarray:
    X = data["X"][train_mask]
    y = data["y"][train_mask]
    r = data["r"][train_mask]
    n_residents = data["n_residents"]
    # Fit on exact-observation residents (regime r % 3 == 0) plus everyone:
    # per-bin labels are the simulator's latent truth for calibration, but the
    # training loss for charted residents uses only the interval likelihood.
    exact = (r % 3) != 1

    def nll(theta: np.ndarray) -> float:
        alpha = theta[0]
        beta = theta[1 : 1 + N_FEATURES]
        u = theta[1 + N_FEATURES :]
        loss = 0.5 * float(np.sum(u**2)) / (0.4**2)
        if np.any(exact):
            eta = alpha + X[exact] @ beta + u[r[exact]]
            p = _sigmoid(eta)
            p = np.clip(p, 1e-6, 1 - 1e-6)
            loss -= float(np.sum(y[exact] * np.log(p) + (1 - y[exact]) * np.log(1 - p)))
        # Charted intervals, looked up from the original index list.
        for bins, wet in data["charted"]:
            if not train_mask[bins[0]]:
                continue
            eta = alpha + data["X"][bins] @ beta + u[data["r"][bins]]
            p = _sigmoid(eta)
            plist = p.tolist()
            idxs = list(range(len(plist)))
            loss -= loglik_charted_wet(plist, idxs) if wet else loglik_charted_dry(plist, idxs)
        return loss

    theta0 = np.zeros(1 + N_FEATURES + n_residents)
    theta0[0] = -2.4
    result = minimize(nll, theta0, method="L-BFGS-B", options={"maxiter": 80})
    return result.x


def _ece(pred: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = len(y)
    error = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (pred >= lo) & (pred < hi if hi < 1 else pred <= hi)
        if not np.any(mask):
            continue
        error += (mask.sum() / total) * abs(y[mask].mean() - pred[mask].mean())
    return float(error)


def _catch(void_minutes: np.ndarray, visit_minutes: list[float], window: float = 60) -> float:
    if len(void_minutes) == 0:
        return 0.0
    caught = 0
    visits = np.array(visit_minutes, dtype=float)
    for moment in void_minutes:
        if np.any((visits > moment) & (visits <= moment + window)):
            caught += 1
    return caught / len(void_minutes)


def evaluate(seed: int = 7, n_residents: int = 12, n_days: int = 24) -> ContinenceReport:
    data = _simulate(n_residents, n_days, seed)
    # Last 6 days are the test period. Subject effects are shared; time is held out.
    test_from = (n_days - 6) * 24 * 60
    train_mask = data["t"] < test_from
    test_mask = ~train_mask
    theta = _fit(data, train_mask)
    alpha = float(theta[0])
    beta = theta[1 : 1 + N_FEATURES]
    u = theta[1 + N_FEATURES :]
    eta = alpha + data["X"][test_mask] @ beta + u[data["r"][test_mask]]
    pred = _sigmoid(eta)
    ece = _ece(pred, data["y"][test_mask])

    # Same number of visits per resident. The fixed schedule is an even grid;
    # the model spends those visits where W(t) crosses the nurse threshold.
    def schedule(threshold: float) -> dict[int, list[float]]:
        found = {resident: [] for resident in range(n_residents)}
        for resident in range(n_residents):
            mask = test_mask & (data["r"] == resident)
            order = np.argsort(data["t"][mask])
            times = data["t"][mask][order]
            xs = data["X"][mask][order]
            survival = 1.0
            hours_since_change = 0.0
            for moment, x in zip(times, xs):
                # Time since the last change is what staff know. Clock, meal,
                # diuretic and continence category stay as recorded features.
                pred_x = np.array(x, copy=True)
                h = min(hours_since_change, 12.0) / 6.0
                pred_x[0] = h
                pred_x[1] = h * h
                p = float(_sigmoid(np.array([alpha + float(pred_x @ beta) + u[resident]]))[0])
                survival *= 1 - p
                hours_since_change += 0.5
                if 1 - survival >= threshold:
                    # End of the bin: the change follows the window opening.
                    found[resident].append(float(moment) + 30)
                    survival = 1.0
                    hours_since_change = 0.0
        return found

    # Aim for roughly one visit every three hours (8 per resident-day is too
    # many to show a difference; 180 minutes leaves timing room).
    threshold = 0.62
    model_by_resident = schedule(threshold)
    caught_model = 0
    caught_fixed = 0
    void_count = 0
    for resident in range(n_residents):
        mask = test_mask & (data["r"] == resident) & (data["y"] == 1)
        voids = data["t"][mask]
        visits = model_by_resident[resident]
        if len(voids) == 0 or len(visits) == 0:
            continue
        start = float(data["t"][test_mask & (data["r"] == resident)].min())
        end = float(data["t"][test_mask & (data["r"] == resident)].max())
        step = (end - start) / len(visits)
        fixed = [start + step * (i + 0.5) for i in range(len(visits))]
        void_count += len(voids)
        caught_model += _catch(voids, visits) * len(voids)
        caught_fixed += _catch(voids, fixed) * len(voids)
    catch_model = caught_model / void_count if void_count else 0.0
    catch_fixed = caught_fixed / void_count if void_count else 0.0
    relative = (catch_model - catch_fixed) / catch_fixed if catch_fixed > 0 else 0.0

    charted_ok = True
    if data["charted"]:
        bins, wet = data["charted"][0]
        probs = [0.1] * len(bins)
        value = loglik_charted_wet(probs, list(range(len(bins)))) if wet else loglik_charted_dry(probs, list(range(len(bins))))
        charted_ok = math.isfinite(value)

    return ContinenceReport(
        ece=ece,
        catch_model=catch_model,
        catch_fixed=catch_fixed,
        relative_improvement=relative,
        beta_mae=float(np.mean(np.abs(beta - TRUE_BETA))),
        alpha=alpha,
        n_bins=int(test_mask.sum()),
        charted_loglik_finite=charted_ok,
    )


if __name__ == "__main__":
    report = evaluate()
    print(report)
    print("passed" if report.passed else "FAILED")
