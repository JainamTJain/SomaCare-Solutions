import numpy as np
import pytest
from somacare_ml.position import synth
from somacare_ml.position.train import train_and_evaluate, confusion_from_report
from somacare_ml.position.infer import PositionClassifier


@pytest.fixture(scope="module")
def trained():
    bg = synth.empty_background()
    ds = synth.make_dataset(n_people=5, per_cell=5, seed=4)
    rep, clf = train_and_evaluate(ds, bg)
    return rep, clf, bg


def test_report_has_the_fields_the_plan_needs(trained):
    rep, clf, _ = trained
    for k in ("ece", "by_cover", "overall", "left_right_confusion", "confusion_matrix", "people_held_out"):
        assert k in rep
    assert set(rep["by_cover"]) == {"none", "sheet", "blanket"}
    cm = confusion_from_report(rep)
    assert np.allclose(cm.sum(axis=1), 1.0)


def test_people_are_held_out(trained):
    rep, _, _ = trained
    assert rep["people_held_out"] == 5


def test_empty_bed_is_out_of_bed_and_blanket_is_unknown(trained):
    _, clf, bg = trained
    rng = np.random.default_rng(2)
    assert clf.predict(synth.render("out_of_bed", "none", 3, rng)).label in ("out_of_bed", "unknown")
    unknown = sum(clf.predict(synth.render("back", "blanket", 3, rng)).label == "unknown" for _ in range(20))
    assert unknown >= 14         # under a thick blanket the system mostly refuses to claim a position


def test_claims_are_more_accurate_than_the_average_frame(trained):
    rep, _, _ = trained
    n = rep["by_cover"]["none"]
    assert n["accuracy_when_claimed"] >= n["accuracy_all"]


def test_model_round_trips_to_disk(trained, tmp_path):
    _, clf, _ = trained
    p = tmp_path / "m.joblib"
    clf.save(p)
    clf2 = PositionClassifier.load(p)
    img = synth.render("left", "none", 2, np.random.default_rng(0))
    assert clf.predict(img).label == clf2.predict(img).label
