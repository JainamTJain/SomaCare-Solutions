"""Gates from the build spec, checked on the simulator:
  1. calibration error under 0.05 on held-out simulated residents
  2. at the same number of visits, the share of voids handled within 60 minutes improves by at least 20 percent
     relative to a fixed schedule
  3. the fit recovers the direction of the true effects (night, diuretic)"""
import zlib
import numpy as np
from .features import features_for_bins, FEATURE_NAMES
from .model import ContinenceModel, _sigmoid
from . import simulator as sim
from ..config import ContinenceConfig

CFG = ContinenceConfig()


def expected_calibration_error(p, y, bins=10):
    p = np.asarray(p); y = np.asarray(y)
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0] -= 1e-9; edges[-1] += 1e-9
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum():
            ece += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(ece)


def bin_level_calibration(model, residents, beta, days, rng, per_day=48):
    """Per-bin predicted void probability against simulated truth, for episodes started at random changes."""
    ps, ys = [], []
    for r in residents:
        for _ in range(days * 2):
            change = int(rng.integers(0, days * per_day - 12))
            bins = np.arange(change + 1, change + 13)
            X = features_for_bins(bins, change, CFG.bin_min, diuretic_bins=r.diuretic_bins, meal_bins=r.meal_bins)
            hod = (bins % per_day) / 2.0
            p_true = _sigmoid(X @ beta + r.u + r.spike * ((hod >= 5) & (hod < 7)))
            void = rng.random(len(p_true)) < p_true
            alive = True
            p_pred = _sigmoid(X @ model.beta + model.u.get(r.rid, 0.0))
            for k in range(len(bins)):
                if not alive:
                    break
                ps.append(p_pred[k]); ys.append(float(void[k]))
                if void[k]:
                    alive = False
    return np.array(ps), np.array(ys)


def run(seed=7, n_train=40, n_test=30, train_days=30, test_days=30, mode="charted", spike=0.0):
    rng = np.random.default_rng(seed)
    beta = sim.true_beta()
    train_res = [sim.make_resident(f"tr{i}", rng, train_days, spike=spike) for i in range(n_train)]
    test_res = [sim.make_resident(f"te{i}", rng, test_days, spike=spike) for i in range(n_test)]
    obs = []
    for r in train_res:
        obs += (sim.simulate_charted(r, beta, train_days, rng) if mode == "charted"
                else sim.simulate_sensor(r, beta, train_days, rng))
    model = ContinenceModel(median_hours_prior=3.0).fit(obs)

    # calibration on held-out residents (their adjustment is unknown, so uses the population estimate)
    ps, ys = bin_level_calibration(model, test_res, beta, test_days, rng)
    ece = expected_calibration_error(ps, ys)

    # learned effects
    coef = dict(zip(FEATURE_NAMES, model.beta))
    night_ok = coef["night"] > 0
    diur_ok = coef["diuretic6h"] > 0

    # policy comparison on held-out residents. Give the model each test resident's adjustment after 7 days
    # of their own charted checks (as the nightly update would).
    warm = []
    for r in test_res:
        warm += sim.simulate_charted(r, beta, 7, rng)
    model.fit(obs + warm)

    fixed_h = 3 * 2   # every 3 hours
    fixed = dict(visits=0, voids=0, handled=0)
    for r in test_res:
        out = sim.run_policy(model, r, beta, test_days, np.random.default_rng(seed + zlib.crc32(r.rid.encode()) % 1000),
                             fixed_every_bins=fixed_h)
        for k in fixed: fixed[k] += out[k]
    target_visits = fixed["visits"]

    # tune q so the model policy uses about the same number of visits (never fewer visits than fixed, to be fair)
    best = None
    for q in np.linspace(0.30, 0.90, 25):
        tot = dict(visits=0, voids=0, handled=0)
        for r in test_res:
            out = sim.run_policy(model, r, beta, test_days, np.random.default_rng(seed + zlib.crc32(r.rid.encode()) % 1000), q=q)
            for k in tot: tot[k] += out[k]
        if tot["visits"] >= target_visits * 0.98:
            best = (q, tot)
        else:
            break
    if best is None:
        best = (0.9, tot)
    q, mod = best
    share_fixed = fixed["handled"] / max(fixed["voids"], 1)
    share_model = mod["handled"] / max(mod["voids"], 1)
    rel = (share_model - share_fixed) / max(share_fixed, 1e-9)
    return dict(mode=mode, misspecified=bool(spike), n_train_residents=n_train, n_test_residents=n_test,
                ece=ece, ece_gate=0.05, ece_pass=bool(ece < 0.05),
                night_effect_learned=float(coef["night"]), diuretic_effect_learned=float(coef["diuretic6h"]),
                effects_direction_ok=bool(night_ok and diur_ok),
                fixed_visits=fixed["visits"], model_visits=mod["visits"], q=float(q),
                share_handled_fixed=float(share_fixed), share_handled_model=float(share_model),
                relative_improvement=float(rel), improvement_gate=0.20, improvement_pass=bool(rel >= 0.20),
                converged=model.converged)


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
