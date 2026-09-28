"""Record a replay of the REAL pipeline on a clip, for the website to play back fast-forwarded.
The output holds keypoints, predictions and decisions only. No frames, no images.

  python tools/record_replay.py --video clips/bed1.mp4 --time-scale 60 \
      --script tools/demo_script.json --out ../web/public/demo/replay.json

--time-scale: care seconds per video second (60 = each video second is one care minute).
--script: optional scripted floor events at care minutes (wet reports, bath findings) so the
          replay also shows the rest of the floor reacting. Bed 1 turns come ONLY from the camera."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from somacare_live.state import Floor, clock_str
from somacare_live.posture import PostureClassifier, CLASSES
from somacare_live.scheduler import TASK_MIN, TRAVEL_MIN

KP_KEEP = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]   # enough for a stick figure

class ManualClock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t

def mediapipe_source(video, sample_hz=2.0):
    """Yields (video_seconds, people) where people is a list of 33-keypoint lists."""
    import cv2, mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    from somacare_live.video import ensure_model
    opts = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=ensure_model()),
        running_mode=vision.RunningMode.VIDEO, num_poses=2,
        min_pose_detection_confidence=0.3, min_tracking_confidence=0.3)
    cap = cv2.VideoCapture(video); fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / sample_hz))); i = 0
    with vision.PoseLandmarker.create_from_options(opts) as lm:
        while True:
            ok, frame = cap.read()
            if not ok: break
            i += 1
            if i % step: continue
            vt = i / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(vt * 1000))
            del frame, rgb
            yield vt, [[(p.x, p.y, p.z, p.visibility) for p in person] for person in (res.pose_landmarks or [])]
    cap.release()

def compact_floor(snap):
    rs = [dict(id=r["id"], room=r["room"], name=r["name"], posture=r["posture"], label=r["posture_label"],
               mins=r["minutes_in_posture"], wet=r["wet"], tier=r["tier_name"], due_col=r["due_col"],
               interval=r["plan"]["interval"], due=r["plan"]["due_clock"], next=r["plan"]["next_label"],
               steps=[[s["text"], s["factor"]] for s in r["plan"]["steps"]], blocked=r["plan"]["blocked"],
               nurse=r["plan"]["nurse"], skin=r["skin"], skin_provisional=r["skin_provisional"])
          for r in snap["residents"]]
    ts = [dict(rid=t["rid"], room=t["room"], cg=t["caregiver"], start=t["start_clock"], due=t["due_clock"],
               late=t["late_by"], what=t["instruction"]) for t in snap["tasks"]]
    return dict(residents=rs, tasks=ts, matrix=snap["matrix"]["cells"])

def record(source, residents_path, out, time_scale=60.0, video_bed=1, script=None, calib=None,
           snapshot_every=1.0, auto_caregivers=True):
    clock = ManualClock()
    floor = Floor.from_file(residents_path, clock=clock)
    clf = PostureClassifier(calib)
    script = sorted(script or [], key=lambda e: e["t"])
    frames, snaps, busy_until, photos = [], [], {}, []
    last_snap, n_events_seen = -1e9, 0
    def run_script(upto):
        while script and script[0]["t"] <= upto:
            e = script.pop(0); rid = e["rid"]
            if e["action"] == "wet": floor.set_wet(rid, True, e.get("source", "thermal sensor"))
            elif e["action"] == "skin_suggestion":
                floor.skin_suggestion(rid, e["site"], dict(status="ok" if e["finding"] else "unsure", finding=e["finding"],
                                      message=e.get("message", "model suggestion")), auto_apply=True)
                if e.get("photo"): photos.append(dict(t=round(clock.t, 2), rid=rid, site=e["site"], file=e["photo"],
                                                      finding=e["finding"], message=e.get("message")))
            elif e["action"] == "skin_finding": floor.skin_confirm(rid, e["site"], e["finding"], e.get("nurse", "Nurse"))
            elif e["action"] == "inputs": floor.update_inputs(rid, e["patch"])
    def caregivers_act():
        """Other beds have no camera in the demo: each free caregiver takes their first task once
        it is due to start, and records the turn in the app. The camera bed is never touched."""
        snap = floor.snapshot()
        for cg in floor.caregivers:
            if busy_until.get(cg, -1) > clock.t: continue
            mine = [t for t in snap["tasks"] if t["caregiver"] == cg and
                    (t["rid"] != video_bed or t["kind"] == "change_turn")]
            if not mine or mine[0]["start"] > clock.t + TRAVEL_MIN + 0.01: continue
            t = mine[0]; rid = t["rid"]
            r = next(x for x in snap["residents"] if x["id"] == rid)
            if r["wet"]: floor.set_wet(rid, False, cg)
            if r["plan"]["next"] and rid != video_bed:      # camera bed: turns come only from the camera
                floor.manual_posture(rid, r["plan"]["next"], cg)
            busy_until[cg] = clock.t + TASK_MIN[t["kind"]] + TRAVEL_MIN
            snap = floor.snapshot()
    for vt, people in source:
        clock.t = vt * time_scale / 60.0
        run_script(clock.t)
        masked = len(people) > 1
        if people:
            kp = people[0]; pred = clf.predict(kp)
            kps = [[round(kp[i][0], 3), round(kp[i][1], 3), round(kp[i][3], 2)] for i in KP_KEEP]
        else:
            pred = dict(probs={c: 1 / 3 for c in CLASSES}, best=None, conf=0.0, reason="no person found", feat=None); kps = None
        floor.sensor_update(video_bed, pred, masked, None)
        h = floor.S[video_bed]["hold"]
        frames.append(dict(vt=round(vt, 2), t=round(clock.t, 2), clock=clock_str(clock.t), kp=kps,
                           p=[round(pred["probs"][c], 2) for c in CLASSES], best=pred["best"],
                           conf=round(pred["conf"], 2), reason=pred.get("reason") or ("second person at bedside" if masked else None),
                           people=len(people), confirmed=floor.S[video_bed]["posture"],
                           cand=h.cand, hold=round(clock.t - h.since, 1) if h.cand else None))
        if auto_caregivers: caregivers_act()
        if clock.t - last_snap >= snapshot_every:
            snap = floor.snapshot()
            ev = list(snap["events"]); new = ev[:len(ev) - n_events_seen] if len(ev) > n_events_seen else []
            n_events_seen = len(ev)
            snaps.append(dict(t=round(clock.t, 2), clock=snap["clock"], floor=compact_floor(snap),
                              new_events=[dict(clock=e["clock"], room=e["room"], text=e["text"], kind=e["kind"]) for e in reversed(new)]))
            last_snap = clock.t
    result = dict(version=1, video_bed=video_bed, time_scale=time_scale, kp_index=KP_KEEP,
                  classes=CLASSES, frames=frames, snapshots=snaps, photos=photos,
                  note="Recorded from the SomaCare pipeline. Keypoints and decisions only; no images.")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, separators=(",", ":")))
    return result

def photo_events(folder):
    """Bath photos named room{ID}_{site}_t{careMinute}.jpg, e.g. room6_rhip_t75.jpg, become
    scripted events: at that care minute the real skin model runs on the photo and its
    suggestion goes to the floor (tightens until a nurse confirms). The file name also says
    which nurse finding to apply 7 min later, if you add _nurse-{finding}, e.g.
    room6_rhip_t75_nurse-blanch.jpg"""
    import re
    from somacare_live import skin
    evs = []
    for f in sorted(Path(folder).glob("*")):
        m = re.match(r"room(\d+)_(sacrum|lhip|rhip|heels)_t(\d+)(?:_nurse-(intact|blanch|stage1|stage2))?\.(jpe?g|png)$", f.name, re.I)
        if not m:
            print("skipped (name does not match room{ID}_{site}_t{minute}.jpg):", f.name); continue
        rid, site, t, nurse = int(m[1]), m[2], float(m[3]), m[4]
        sug = skin.suggest(f.read_bytes())
        evs.append(dict(t=t, rid=rid, action="skin_suggestion", site=site, finding=sug.get("finding"),
                        message=f"bath photo {f.name}: {sug['message']}", photo=f.name))
        if nurse: evs.append(dict(t=t + 7, rid=rid, action="skin_finding", site=site, finding=nurse, nurse="Nurse"))
    return evs

def parse_windows(spec):
    out = {}
    for part in spec.split(","):
        label, rng = part.split(":"); lo, hi = rng.split("-"); out[label.strip()] = (float(lo), float(hi))
    return out

def calibrate_from_windows(source, spec, calib_path):
    """First pass: collect features while the person holds each labelled posture, then fit."""
    from somacare_live.posture import features
    wins, samples = parse_windows(spec), {}
    for vt, people in source:
        if len(people) != 1: continue
        for label, (lo, hi) in wins.items():
            if lo <= vt <= hi:
                f = features(people[0])
                if f["vis"] >= 0.5: samples.setdefault(label, []).append(f)
    missing = [c for c in CLASSES if len(samples.get(c, [])) < 5]
    if missing: raise SystemExit(f"calibration windows too short or person not visible for: {missing}")
    fit = PostureClassifier(calib_path).fit_calibration(samples)
    print("calibrated:", {k: v["n"] for k, v in fit.items()}, "->", calib_path)
    return fit

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True); ap.add_argument("--out", default="../web/public/demo/replay.json")
    ap.add_argument("--time-scale", type=float, default=60.0); ap.add_argument("--sample-hz", type=float, default=2.0)
    ap.add_argument("--script"); ap.add_argument("--calib", default="data/calibration_bed1.json")
    ap.add_argument("--calib-windows", help='video seconds per posture, e.g. "supine:5-25,left30:130-150,right30:310-330"')
    ap.add_argument("--photos", help="folder of bath photos named room{ID}_{site}_t{minute}[_nurse-{finding}].jpg")
    ap.add_argument("--residents", default=str(Path(__file__).resolve().parents[1] / "somacare_live" / "seed_residents.json"))
    a = ap.parse_args()
    scr = json.loads(Path(a.script).read_text()) if a.script else []
    if a.photos: scr += photo_events(a.photos)
    if a.calib_windows:
        calibrate_from_windows(mediapipe_source(a.video, a.sample_hz), a.calib_windows, a.calib)
    res = record(mediapipe_source(a.video, a.sample_hz), a.residents, a.out, a.time_scale, script=scr, calib=a.calib)
    turns = [e for s in res["snapshots"] for e in s["new_events"] if e["kind"] == "turn" and e["room"] == "Room 1"]
    print(f"{len(res['frames'])} frames, {len(res['snapshots'])} snapshots, {len(turns)} camera turns in Room 1 -> {a.out}")
