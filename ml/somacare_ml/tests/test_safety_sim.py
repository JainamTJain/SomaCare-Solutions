from somacare_ml.safety_sim import simulate, Scenario


def test_false_confirms_hurt_without_a_tight_cap_and_a_tight_cap_fixes_it():
    kw = dict(residents=8, days=7, seed=1)
    none = simulate(Scenario("a", camera=True, false_confirm_per_hour=0.1, hard_cap_min=None), **kw)
    tight = simulate(Scenario("b", camera=True, false_confirm_per_hour=0.1, hard_cap_min=150.0), **kw)
    assert none["failures_per_resident_day"] > 0.3
    assert tight["failures_per_resident_day"] == 0.0
    assert tight["max_true_exposure_min"] <= 150.0


def test_deterministic():
    a = simulate(Scenario("x", camera=True), residents=4, days=3, seed=9)
    b = simulate(Scenario("x", camera=True), residents=4, days=3, seed=9)
    assert a == b
