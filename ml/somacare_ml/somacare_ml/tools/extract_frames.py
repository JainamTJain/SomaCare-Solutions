"""Turn a recorded video plus a labels file into the same folder layout the recorder writes.

Video:  any file OpenCV can read.  Labels csv columns: ts_s,label,cover,person   (ts_s = seconds from video start,
each row means 'from this time on, this is the label'). Frames within margin_s of a change are dropped."""
import argparse, csv, os
import cv2


def extract(video, labels_csv, out_dir, fps=2.0, margin_s=3.0):
    rows = list(csv.DictReader(open(labels_csv)))
    rows = sorted(rows, key=lambda r: float(r["ts_s"]))
    times = [float(r["ts_s"]) for r in rows]
    cap = cv2.VideoCapture(video)
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(int(round(vfps / fps)), 1)
    n, saved, i = 0, 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if n % step == 0:
            t = n / vfps
            idx = max([k for k, x in enumerate(times) if x <= t], default=None)
            if idx is not None and rows[idx]["label"] != "transition":
                near = any(abs(t - x) < margin_s for x in times)
                if not near:
                    r = rows[idx]
                    d = os.path.join(out_dir, r["person"], r["cover"], r["label"])
                    os.makedirs(d, exist_ok=True)
                    cv2.imwrite(os.path.join(d, "frame_%06d.jpg" % saved), frame); saved += 1
        n += 1
    cap.release()
    return saved


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("labels"); ap.add_argument("--out", default="data/raw")
    ap.add_argument("--fps", type=float, default=2.0); ap.add_argument("--margin", type=float, default=3.0)
    a = ap.parse_args()
    print("saved", extract(a.video, a.labels, a.out, a.fps, a.margin))
