import numpy as np
from somacare_ml import patterns


def test_regular_meals_are_flagged_as_confounded():
    meals = [d * 1440 + h * 60 for d in range(20) for h in (8, 12, 18)]
    ch = [m + 45 for m in meals]
    kinds = [x["kind"] for x in patterns.detect(ch, meals)]
    assert "confounded" in kinds and "after_meal" not in kinds


def test_irregular_meals_with_real_pattern_detected():
    rng = np.random.default_rng(0)
    meals = sorted(float(d * 1440 + rng.uniform(300, 1300)) for d in range(20) for _ in range(3))
    ch = [m + rng.uniform(20, 80) for m in meals if rng.random() < 0.7] + [rng.uniform(0, 20 * 1440) for _ in range(10)]
    assert any(x["kind"] == "after_meal" for x in patterns.detect(ch, meals))


def test_small_samples_return_nothing():
    assert patterns.detect([100, 200, 300], [50, 150, 250]) == []


def test_uniform_data_rarely_flags():
    fp = 0
    for s in range(60):
        r = np.random.default_rng(500 + s)
        meals = sorted(float(d * 1440 + r.uniform(300, 1300)) for d in range(20) for _ in range(3))
        ch = list(r.uniform(0, 20 * 1440, 50))
        fp += any(x["kind"] in ("after_meal", "time_of_day") for x in patterns.detect(ch, meals))
    assert fp / 60 < 0.08
