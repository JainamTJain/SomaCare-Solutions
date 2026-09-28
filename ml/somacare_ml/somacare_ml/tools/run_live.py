"""Run the trained classifier and the turn detector on a camera or a video, and optionally post events to the backend.

  python -m somacare_ml.tools.run_live --model models/position.joblib --source video.mp4 --room ROOM --resident RES
  add --post-url http://127.0.0.1:8000/events --token $SOMACARE_EDGE_TOKEN to send them.

No frame is written to disk. Only events leave this process."""
import argparse, json, time, urllib.request
from ..position.infer import PositionClassifier
from ..turn import TurnDetector
from ..backend_events import to_backend_event


def run(model_path, source, room, resident, post_url=None, token=None, fps=2.0, max_seconds=None, out=print):
    import cv2
    clf = PositionClassifier.load(model_path)
    det = TurnDetector()
    src = int(source) if str(source).isdigit() else source
    cap = cv2.VideoCapture(src)
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(int(round(vfps / fps)), 1)
    n, t0 = 0, time.time()
    is_file = not (isinstance(src, int) or str(src).startswith("rtsp"))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        if n % step:
            continue
        ts = (n / vfps) if is_file else time.time()
        rd = clf.predict(frame)
        for e in det.update(ts, rd.label, rd.confidence):
            ev = to_backend_event(e, room, resident, "position-gbdt-v0.1", epoch_offset=(time.time() if is_file else 0.0))
            if ev:
                out(json.dumps(ev))
                if post_url:
                    req = urllib.request.Request(post_url, data=json.dumps(ev).encode(),
                                                 headers={"Content-Type": "application/json",
                                                          "Authorization": "Bearer " + (token or "")})
                    try:
                        urllib.request.urlopen(req, timeout=5)
                    except Exception as ex:
                        out("post failed: %s" % ex)
        if max_seconds and (time.time() - t0) > max_seconds:
            break
    cap.release()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--source", required=True)
    ap.add_argument("--room", default="room-12"); ap.add_argument("--resident", default="resident-12")
    ap.add_argument("--post-url"); ap.add_argument("--token"); ap.add_argument("--max-seconds", type=float)
    a = ap.parse_args()
    run(a.model, a.source, a.room, a.resident, a.post_url, a.token, max_seconds=a.max_seconds)
