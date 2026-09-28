"""Discrete-time hazard model for wetness, fitted by MAP with analytic gradients (numpy and scipy only).

For resident r and bin k after a change:  p = sigmoid(x_k . beta + u_r),  u_r ~ Normal(0, sigma_u^2)
Wet probability since the last change:    W(t) = 1 - prod_k (1 - p_k)

Three kinds of observation share one likelihood. Each covers bins (start, end] after the pad was put on:
  dry     a check found it dry       no void in the interval
  wet     a check found it wet       at least one void in the interval (interval censored)
  exact   a sensor or bathroom trip  the first void happened exactly in bin `end`

Cold start: with no data the model reproduces the nurse's schedule (median time to wetness), and the fit
shrinks toward that prior, so it behaves like today's schedule until real observations say otherwise.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from .features import D, features_for_bins
from ..config import ContinenceConfig


@dataclass
class Observation:
    resident: str
    kind: str                 # 'dry' | 'wet' | 'exact'
    start_bin: int            # left edge (exclusive)
    end_bin: int              # right edge (inclusive)
    change_bin: int           # when the current pad went on (sets 'hours since')
    diuretic_bins: tuple = ()
    meal_bins: tuple = ()


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def cold_start_beta(median_hours, bin_min=30):
    """Constant hazard whose median time to wetness matches the nurse's current schedule."""
    n = max(median_hours * 60.0 / bin_min, 1.0)
    p0 = 1.0 - 0.5 ** (1.0 / n)
    beta = np.zeros(D)
    beta[0] = np.log(p0 / (1.0 - p0))
    return beta


def wet_probability_curve(beta, u, start_bin, n_bins, cfg=ContinenceConfig(), diuretic_bins=(), meal_bins=()):
    """W(t) for the bins after `start_bin`, as an array of length n_bins."""
    bins = np.arange(start_bin + 1, start_bin + 1 + n_bins)
    X = features_for_bins(bins, start_bin, cfg.bin_min, diuretic_bins=diuretic_bins, meal_bins=meal_bins)
    p = _sigmoid(X @ beta + u)
    return 1.0 - np.exp(np.cumsum(np.log1p(-p)))


class ContinenceModel:
    def __init__(self, cfg: ContinenceConfig = ContinenceConfig(), median_hours_prior: float = 3.0):
        self.cfg = cfg
        self.beta0 = cold_start_beta(median_hours_prior, cfg.bin_min)
        self.beta = self.beta0.copy()
        self.u = {}
        self.n_events = 0
        self.converged = True

    def _prep(self, obs):
        cache = []
        for o in obs:
            bins = np.arange(o.start_bin + 1, o.end_bin + 1)
            if len(bins) == 0:
                continue
            X = features_for_bins(bins, o.change_bin, self.cfg.bin_min,
                                  diuretic_bins=o.diuretic_bins, meal_bins=o.meal_bins)
            cache.append((o.resident, o.kind, X))
        return cache

    def _objective(self, theta, cache, residents, prior_beta, prec_beta, sigma_u):
        beta = theta[:D]
        u = dict(zip(residents, theta[D:]))
        nll = 0.0
        g_beta = np.zeros(D)
        g_u = {r: 0.0 for r in residents}
        for r, kind, X in cache:
            z = X @ beta + u[r]
            p = _sigmoid(z)
            log1mp = np.log1p(-np.clip(p, 0, 1 - 1e-12))
            if kind == "dry":
                ll = log1mp.sum(); dz = -p
            elif kind == "exact":
                ll = log1mp[:-1].sum() + np.log(np.clip(p[-1], 1e-12, 1))
                dz = -p.copy(); dz[-1] = 1.0 - p[-1]
            else:  # wet, interval censored: log(1 - Q), Q = prod(1 - p)
                Q = np.exp(log1mp.sum())
                omq = max(1.0 - Q, 1e-12)
                ll = np.log(omq)
                dz = (Q / omq) * p
            nll -= ll
            g_beta -= X.T @ dz
            g_u[r] -= dz.sum()
        d = beta - prior_beta
        nll += 0.5 * prec_beta * float(d @ d)
        g_beta += prec_beta * d
        gu = []
        for r in residents:
            nll += 0.5 * (u[r] ** 2) / sigma_u ** 2
            g_u[r] += u[r] / sigma_u ** 2
            gu.append(g_u[r])
        return nll, np.concatenate([g_beta, np.array(gu)])

    def fit(self, observations):
        """MAP fit of population beta and each resident's adjustment. Shrinks toward the cold-start prior."""
        obs = [o for o in observations if o.end_bin > o.start_bin]
        if not obs:
            return self
        residents = sorted({o.resident for o in obs})
        cache = self._prep(obs)
        theta0 = np.concatenate([self.beta0.copy(), np.zeros(len(residents))])
        res = minimize(self._objective, theta0,
                       args=(cache, residents, self.beta0, self.cfg.prior_precision, self.cfg.sigma_u),
                       jac=True, method="L-BFGS-B", options={"maxiter": 500})
        self.beta = res.x[:D]
        self.u = dict(zip(residents, res.x[D:]))
        self.n_events = sum(1 for o in obs if o.kind in ("wet", "exact"))
        self.converged = bool(res.success)
        return self

    @property
    def learning(self):
        return self.n_events < self.cfg.min_events_to_leave_learning

    def curve(self, resident, start_bin, n_bins, diuretic_bins=(), meal_bins=()):
        return wet_probability_curve(self.beta, self.u.get(resident, 0.0), start_bin, n_bins, self.cfg,
                                     diuretic_bins, meal_bins)

    def next_check_bin(self, resident, from_bin, change_bin, threshold=None, horizon_bins=48,
                       diuretic_bins=(), meal_bins=()):
        """Earliest bin after `from_bin` where the probability of a void since `from_bin`
        (given a dry pad then) reaches the threshold. Returns (bin, probability_at_that_bin)."""
        thr = self.cfg.threshold if threshold is None else threshold
        bins = np.arange(from_bin + 1, from_bin + 1 + horizon_bins)
        X = features_for_bins(bins, change_bin, self.cfg.bin_min, diuretic_bins=diuretic_bins, meal_bins=meal_bins)
        p = _sigmoid(X @ self.beta + self.u.get(resident, 0.0))
        w = 1.0 - np.exp(np.cumsum(np.log1p(-p)))
        hit = np.nonzero(w >= thr)[0]
        k = int(hit[0]) if len(hit) else horizon_bins - 1
        return int(bins[k]), float(w[k])
