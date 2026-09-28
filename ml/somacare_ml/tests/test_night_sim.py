import pytest
from somacare_ml.night_sim import experiments


@pytest.fixture(scope="module")
def table():
    return {row["name"]: row for row in experiments(40, seed=1)}


def test_ordinary_nights_only_fail_when_a_wrong_camera_is_trusted(table):
    paper = table["Paper"]["ordinary"]
    stay = table["SomaCare, human checks stay"]["ordinary"]
    trust = table["SomaCare, trust the camera"]["ordinary"]
    wrong = table["Trusted, and sometimes wrong"]["ordinary"]
    stay_wrong = table["Human checks stay, camera sometimes wrong"]["ordinary"]
    assert paper["nights_past"] == 0
    assert stay["nights_past"] == 0
    assert trust["nights_past"] == 0
    assert stay_wrong["nights_past"] == 0
    assert wrong["nights_past"] > 20
    assert trust["visits"] < paper["visits"] - 2
    assert abs(stay["visits"] - paper["visits"]) < 0.6
    assert stay["records"] > paper["records"] + 5
    assert stay_wrong["records"] > stay["records"]


def test_a_stretched_night_is_safer_when_the_camera_orders_the_visits(table):
    paper = table["Paper"]["stretched"]
    stay = table["SomaCare, human checks stay"]["stretched"]
    wrong = table["Trusted, and sometimes wrong"]["stretched"]
    assert stay["nights_past"] < paper["nights_past"] / 2
    assert stay["longest_past"] < paper["longest_past"]
    assert wrong["nights_past"] > paper["nights_past"]
