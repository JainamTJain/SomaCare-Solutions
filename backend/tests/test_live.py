import json, math, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from somacare_live import engine
from somacare_live.scheduler import schedule
from somacare_live.posture import PostureClassifier, HoldConfirmer, features
from somacare_live.state import Floor, CareClock

SEED = json.load(open(os.path.join(os.path.dirname(__file__), "..", "somacare_live", "seed_residents.json")))

class FixedClock(CareClock):
    def __init__(self, t=0.0): self.t = t
    def now(self): return self.t

def floor_at(t=0.0):
    f = Floor(SEED, clock=FixedClock(t)); return f

def row(snap, rid): return next(r for r in snap["residents"] if r["id"] == rid)

# ---------- engine ----------
def test_turn_trial_intervals_and_nurse_cap():
    f = floor_at(0); s = f.snapshot()
    rosa = row(s, 1)   # Braden 11, HD foam 180 x0.85 frail x0.75 back on blanchable sacrum = 115
    assert rosa["plan"]["interval"] == 115 and len(rosa["plan"]["steps"]) == 4
    walter = row(s, 2) # Braden 14, HD foam -> 240
    assert walter["plan"]["interval"] == 240
    harold = row(s, 5) # Braden 21 -> no timed turns
    assert harold["plan"]["interval"] is None and harold["due_col"] == 4

def test_stage1_on_loaded_site_means_now_and_blocks_that_position():
    f = floor_at(0); f.manual_posture(4, "supine")          # Ada has Stage 1 sacrum
    ada = row(f.snapshot(), 4)
    assert ada["plan"]["interval"] == 0 and ada["plan"]["next"] in ("left30", "right30")
    f2 = floor_at(0); ada2 = row(f2.snapshot(), 4)          # on left side: back is blocked
    assert ada2["plan"]["next"] == "right30" and ada2["plan"]["blocked"]

def test_wet_shortens_and_moves_to_front_of_queue():
    f = floor_at(0); before = row(f.snapshot(), 2)["plan"]["interval"]
    f.set_wet(2, True, "sensor"); s = f.snapshot()
    assert row(s, 2)["plan"]["interval"] == round(before * 0.75)
    assert s["tasks"][0]["rid"] == 2 and s["tasks"][0]["kind"] == "change_turn"

def test_photo_suggestion_only_tightens_until_nurse_confirms():
    f = floor_at(0)
    iv = row(f.snapshot(), 2)["plan"]["interval"]          # Walter on left side
    f.skin_suggestion(2, "lhip", dict(status="ok", finding="stage1", message="x"), auto_apply=True)
    s = row(f.snapshot(), 2)
    assert s["plan"]["interval"] == 0 and s["plan"]["nurse"]
    f.skin_confirm(2, "lhip", "blanch")                      # nurse press test: it blanches
    s = row(f.snapshot(), 2)
    assert s["plan"]["interval"] == round(max(60, iv * 0.75)) and not s["skin_provisional"]

def test_inputs_change_the_plan_live():
    f = floor_at(0)
    f.update_inputs(2, {"braden": {"mobility": 1, "activity": 1}})   # Braden 14 -> 12
    assert row(f.snapshot(), 2)["plan"]["interval"] == 180
    f.update_inputs(2, {"nurse_max": 120})
    assert row(f.snapshot(), 2)["plan"]["interval"] == 120

# ---------- scheduler ----------
def test_schedule_orders_by_due_and_flags_late():
    f = floor_at(60); s = f.snapshot()
    ts = s["tasks"]; assert ts, "expected tasks"
    dues = [t["due"] for t in ts if t["kind"] == "turn"]
    assert dues == sorted(dues)
    assert all(t["caregiver"] in ("Maria", "Joy") for t in ts)
    assert any(t["late_by"] > 0 for t in ts)                    # Ada and Rosa are already overdue
    assert s["residents"][0]["id"] == ts[0]["rid"]              # resident list follows the queue

def test_matrix_places_every_resident_once():
    s = floor_at(30).snapshot()
    cells = [room for row_ in s["matrix"]["cells"] for cell in row_ for room in cell]
    assert sorted(cells) == sorted(r["room"] for r in SEED)

# ---------- posture from keypoints ----------
def fake_kp(kind, rng, vis=0.9):
    kp = [(0.5, 0.5, 0.0, vis)] * 33; kp = list(kp)
    w = {"supine": 0.12, "left30": 0.035, "right30": 0.035}[kind]
    z = {"supine": 0.0, "left30": 0.12, "right30": -0.12}[kind]
    j = lambda: rng.gauss(0, 0.008)
    kp[11] = (0.5 - w + j(), 0.35 + j(), z / 2 + j(), vis); kp[12] = (0.5 + w + j(), 0.35 + j(), -z / 2 + j(), vis)
    kp[23] = (0.5 - w * 0.8 + j(), 0.62 + j(), z / 2 + j(), vis); kp[24] = (0.5 + w * 0.8 + j(), 0.62 + j(), -z / 2 + j(), vis)
    kp[0] = (0.5 + (0.03 if kind == "left30" else -0.03 if kind == "right30" else 0) + j(), 0.22, 0, vis)
    return kp

def test_rule_classifier_on_keypoints():
    rng = random.Random(0); clf = PostureClassifier()
    ok = sum(clf.predict(fake_kp(k, rng))["best"] == k for k in ("supine", "left30", "right30") for _ in range(100))
    assert ok >= 290

def test_calibration_learns_a_camera_with_flipped_depth():
    rng = random.Random(1); clf = PostureClassifier()
    flip = lambda kp: [(x, y, -z, v) for x, y, z, v in kp]  # a camera where depth sign is reversed
    samples = {k: [features(flip(fake_kp(k, rng))) for _ in range(40)] for k in ("supine", "left30", "right30")}
    clf.fit_calibration(samples)
    ok = sum(clf.predict(flip(fake_kp(k, rng)))["best"] == k for k in ("supine", "left30", "right30") for _ in range(100))
    assert ok >= 290

def test_hidden_torso_is_unsure_not_guessed():
    p = PostureClassifier().predict(fake_kp("supine", random.Random(2), vis=0.2))
    assert p["best"] is None and "cover" in p["reason"]

def test_hold_confirmer_turn_vs_shift():
    h = HoldConfirmer("supine"); P = lambda b: dict(best=b, conf=0.9, probs={})
    assert h.update(0, P("left30")) is None and h.update(1, P("left30")) is None
    ev = h.update(2, P("supine")); assert ev["type"] == "shift"
    for t in (10, 11, 12, 13): r = h.update(t, P("left30"))
    assert r["type"] == "turn" and r["to"] == "left30" and r["at"] == 10
    assert h.update(20, P("right30"), masked=True) is None      # caregiver in frame: ignored

def test_camera_turn_updates_floor_and_log():
    f = floor_at(0); clf = PostureClassifier(); rng = random.Random(3)
    for t in range(0, 5):
        f.clock.t = t; f.sensor_update(1, clf.predict(fake_kp("left30", rng)), False)
    s = f.snapshot(); r = row(s, 1)
    assert r["posture"] == "left30" and r["minutes_in_posture"] <= 4
    assert any("confirmed by the camera" in e["text"] for e in s["events"])

# ---------- API ----------
def test_api_end_to_end():
    import io
    from PIL import Image
    from fastapi.testclient import TestClient
    from somacare_live import api
    c = TestClient(api.app)
    assert c.get("/api/health").json()["ok"]
    buf = io.BytesIO(); Image.new("RGB", (400, 400), (200, 160, 140)).save(buf, "JPEG")
    r = c.post("/api/residents/2/skin-photo", data={"site": "lhip"}, files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")})
    # no weights -> model_not_loaded; published checkpoint -> a suggestion (plain skin is usually Invalid)
    assert r.json()["suggestion"]["status"] in ("model_not_loaded", "no_injury", "ok", "unsure")
    r = c.post("/api/residents/2/skin-finding", json={"site": "lhip", "finding": "stage1"})
    assert row(r.json(), 2)["plan"]["interval"] == 0
    r = c.post("/api/residents/2/posture", json={"posture": "supine"})
    assert row(r.json(), 2)["posture"] == "supine"
    assert c.post("/api/residents/2/posture", json={"posture": "sideways"}).status_code == 400

def test_replay_recorder_captures_camera_turns_and_floor(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from record_replay import record
    rng = random.Random(5)
    def fake_source():   # 8 min of video at 2 Hz, time scale 60: back, then left side, a caregiver, then right side
        for i in range(960):
            vt = i / 2; t = vt
            kind = "supine" if t < 120 else "left30" if t < 300 else "right30"
            people = [fake_kp(kind, rng)]
            if 290 <= t < 300: people.append(fake_kp("supine", rng))      # caregiver in view
            yield vt, people
    script = [{"t": 40, "rid": 2, "action": "wet"}, {"t": 75, "rid": 6, "action": "skin_finding", "site": "rhip", "finding": "stage1"}]
    out = tmp_path / "replay.json"
    res = record(fake_source(), os.path.join(os.path.dirname(__file__), "..", "somacare_live", "seed_residents.json"),
                 out, time_scale=60, script=script)
    assert out.exists() and len(res["frames"]) == 960 and res["frames"][0]["kp"]
    evs = [e for s in res["snapshots"] for e in s["new_events"]]
    cam = [e["text"] for e in evs if e["room"] == "Room 1" and e["kind"] == "turn"]
    assert len(cam) == 2 and "left side" in cam[0] and "right side" in cam[1]
    assert any(f["reason"] == "second person at bedside" for f in res["frames"])
    assert any(f["cand"] and f["hold"] is not None for f in res["frames"])     # the hold timer is visible
    assert any(e["room"] == "Room 2" and e["kind"] == "wet" for e in evs)
    assert any(e["room"] != "Room 1" and e["kind"] == "turn" for e in evs)     # other beds turned by caregivers
    assert "data:" not in out.read_text() and out.stat().st_size < 3_000_000   # no images, small file

def test_calibrate_from_windows(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from record_replay import calibrate_from_windows
    rng = random.Random(9)
    flip = lambda kp: [(x, y, -z, v) for x, y, z, v in kp]
    def src():
        for i in range(600):
            vt = i / 2; k = "supine" if vt < 100 else "left30" if vt < 200 else "right30"
            yield vt, [flip(fake_kp(k, rng))]
    path = tmp_path / "calib.json"
    calibrate_from_windows(src(), "supine:10-60,left30:120-170,right30:220-270", str(path))
    clf = PostureClassifier(str(path))
    assert sum(clf.predict(flip(fake_kp(k, rng)))["best"] == k for k in ("supine", "left30", "right30") for _ in range(50)) >= 145

def test_photo_folder_becomes_timed_events(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from record_replay import photo_events, record
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (400, 400), (200, 160, 140)).save(buf, "JPEG")
    (tmp_path / "room6_rhip_t75_nurse-blanch.jpg").write_bytes(buf.getvalue())
    (tmp_path / "holiday.jpg").write_bytes(b"x")
    evs = photo_events(tmp_path)
    assert [e["action"] for e in evs] == ["skin_suggestion", "skin_finding"] and evs[1]["t"] == 82
    rng = random.Random(1)
    src = ((i / 2, [fake_kp("supine", rng)]) for i in range(240))
    res = record(src, os.path.join(os.path.dirname(__file__), "..", "somacare_live", "seed_residents.json"),
                 tmp_path / "r.json", time_scale=60, script=evs)
    assert res["photos"][0]["file"] == "room6_rhip_t75_nurse-blanch.jpg"
    evtext = [e["text"] for s in res["snapshots"] for e in s["new_events"] if e["room"] == "Room 6"]
    assert any("bath photo" in t for t in evtext) and any("confirmed right hip" in t for t in evtext)

def test_published_model_output_maps_to_engine_findings():
    from somacare_live import skin
    P = lambda i, c: [c if j == i else (1 - c) / 6 for j in range(7)]
    assert skin.interpret(P(0, 0.9))["finding"] == "intact" and skin.interpret(P(0, 0.9))["status"] == "no_injury"
    assert skin.interpret(P(2, 0.8))["finding"] == "stage1"
    assert all(skin.interpret(P(i, 0.8))["finding"] == "stage2" for i in (1, 3, 4, 5, 6))
    u = skin.interpret(P(3, 0.4)); assert u["status"] == "unsure" and u["finding"] is None
    f = floor_at(0)
    iv = row(f.snapshot(), 2)["plan"]["interval"]
    f.skin_suggestion(2, "lhip", skin.interpret(P(0, 0.9)), auto_apply=True)
    assert row(f.snapshot(), 2)["plan"]["interval"] == iv and not row(f.snapshot(), 2)["skin_provisional"]

