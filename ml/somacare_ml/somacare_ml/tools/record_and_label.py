"""Record labeled overhead frames for training and testing. Volunteers only, with written consent.

Run:  python -m somacare_ml.tools.record_and_label --source 0 --person p01 --out data/raw
      --source can be a webcam index, a video file, or an rtsp:// address.

Keys while it runs
  b back   l left   r right   s sitting   o out of bed   t transition (moving between positions)
  1 cover=none   2 cover=sheet   3 cover=blanket
  2/3 people in zone: press  ,  for 1 person and  .  for 2 people (a caregiver present)
  e  record 10 empty-bed frames as the background (do this first, with nobody on the bed)
  q  quit
Every saved frame goes to data/raw/<person>/<cover>/<label>/frame_XXXXXX.jpg and a row goes to labels.csv.
Left and right mean the SUBJECT's left and right side. Agree this with the team before recording."""
import argparse, csv, os, time
import numpy as np

KEYS = {ord("b"): "back", ord("l"): "left", ord("r"): "right", ord("s"): "sitting", ord("o"): "out_of_bed",
        ord("t"): "transition"}
COVER_KEYS = {ord("1"): "none", ord("2"): "sheet", ord("3"): "blanket"}


class RecorderCore:
    """All the logic, with no window and no camera, so it can be tested."""

    def __init__(self, out_dir, person, fps=2.0):
        self.out, self.person, self.fps = out_dir, person, fps
        self.label, self.cover, self.persons = "transition", "none", 1
        self.count, self._last = 0, -1e9
        self.empty_pending = 0
        self.empty = []
        os.makedirs(out_dir, exist_ok=True)
        self.csv_path = os.path.join(out_dir, person + "_labels.csv")
        new = not os.path.exists(self.csv_path)
        self._f = open(self.csv_path, "a", newline="")
        self._w = csv.writer(self._f)
        if new:
            self._w.writerow(["ts", "label", "cover", "person", "persons", "path"])

    def handle_key(self, k):
        if k in KEYS: self.label = KEYS[k]
        elif k in COVER_KEYS: self.cover = COVER_KEYS[k]
        elif k == ord(","): self.persons = 1
        elif k == ord("."): self.persons = 2
        elif k == ord("e"): self.empty_pending = 10
        return k == ord("q")

    def on_frame(self, frame, ts):
        import cv2
        if self.empty_pending > 0:
            self.empty.append(frame.copy()); self.empty_pending -= 1
            if self.empty_pending == 0:
                bg = np.median(np.stack(self.empty), axis=0).astype(np.uint8)
                cv2.imwrite(os.path.join(self.out, "background.png"), bg)
            return None
        if ts - self._last < 1.0 / self.fps:
            return None
        self._last = ts
        d = os.path.join(self.out, self.person, self.cover, self.label)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "frame_%06d.jpg" % self.count)
        cv2.imwrite(path, frame)
        self._w.writerow([round(ts, 3), self.label, self.cover, self.person, self.persons, path])
        self._f.flush(); self.count += 1
        return path

    def close(self):
        self._f.close()


def main():
    import cv2
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0"); ap.add_argument("--person", required=True)
    ap.add_argument("--out", default="data/raw"); ap.add_argument("--fps", type=float, default=2.0)
    a = ap.parse_args()
    src = int(a.source) if a.source.isdigit() else a.source
    cap = cv2.VideoCapture(src)
    core = RecorderCore(a.out, a.person, a.fps)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        core.on_frame(frame, time.time())
        vis = frame.copy()
        cv2.putText(vis, f"{core.label} | {core.cover} | persons={core.persons} | saved={core.count}", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imshow("record", vis)
        if core.handle_key(cv2.waitKey(1) & 0xFF):
            break
    core.close(); cap.release(); cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
