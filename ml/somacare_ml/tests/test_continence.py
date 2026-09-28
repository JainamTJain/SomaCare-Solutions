import numpy as np
from scipy.optimize import check_grad
from somacare_ml.continence import ContinenceModel, Observation
from somacare_ml.continence.model import cold_start_beta
from somacare_ml.continence.features import D, FEATURE_NAMES
from somacare_ml.continence import simulator as sim, evaluate


def test_cold_start_matches_the_nurses_schedule():
    m = ContinenceModel(median_hours_prior=3.0)
    w = m.curve("a", 0, 12)            # 30 minute bins, 6 bins = 3 hours
    assert abs(w[5] - 0.5) < 0.02


def test_gradient_is_correct():
    m = ContinenceModel()
    obs = [Observation("a", "dry", 0, 4, 0), Observation("a", "wet", 4, 9, 0), Observation("a", "exact", 20, 27, 20),
           Observation("b", "wet", 0, 6, 0), Observation("b", "dry", 6, 10, 0)]
    res = sorted({o.resident for o in obs}); cache = m._prep(obs)
    f = lambda th: m._objective(th, cache, res, m.beta0, 4.0, 0.5)[0]
    g = lambda th: m._objective(th, cache, res, m.beta0, 4.0, 0.5)[1]
    th = np.concatenate([m.beta0, [0.2, -0.1]]) + np.random.default_rng(0).normal(0, 0.1, D + 2)
    assert check_grad(f, g, th) < 1e-4


def test_no_data_keeps_the_prior_and_learning_flag_is_on():
    m = ContinenceModel().fit([])
    assert m.learning and np.allclose(m.beta, m.beta0)


def test_fit_learns_direction_of_night_and_diuretic_effects():
    rng = np.random.default_rng(3)
    beta = sim.true_beta()
    res = [sim.make_resident(f"r{i}", rng, 20) for i in range(20)]
    obs = [o for r in res for o in sim.simulate_charted(r, beta, 20, rng)]
    m = ContinenceModel().fit(obs)
    c = dict(zip(FEATURE_NAMES, m.beta))
    assert c["night"] > 0 and c["diuretic6h"] > 0 and not m.learning


def test_next_check_never_before_from_bin_and_probability_reaches_threshold():
    m = ContinenceModel(median_hours_prior=3.0)
    b, p = m.next_check_bin("a", 10, 10, threshold=0.5)
    assert b > 10 and p >= 0.5


def test_gates_on_the_simulator():
    r = evaluate.run(seed=11, n_train=25, n_test=15, train_days=20, test_days=20)   # about 500 resident-days; fewer is unstable
    assert r["ece_pass"] and r["effects_direction_ok"] and r["improvement_pass"]
