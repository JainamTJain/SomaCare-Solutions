"""Posture from pose keypoints (MediaPipe 33-landmark layout), plus the hold-time rule that
turns noisy per-frame guesses into confirmed turns. Works from keypoints only, so the UI and
logs never need a frame."""
import math, json
from pathlib import Path

NOSE, LSH, RSH, LHIP, RHIP = 0, 11, 12, 23, 24
CLASSES = ["supine", "left30", "right30"]

def features(kp):
    """kp: list of 33 (x, y, z, visibility), x/y normalised to the frame."""
    ls, rs, lh, rh, no = kp[LSH], kp[RSH], kp[LHIP], kp[RHIP], kp[NOSE]
    msx, msy = (ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2
    mhx, mhy = (lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2
    ax, ay = mhx - msx, mhy - msy; L = math.hypot(ax, ay) or 1e-6
    nx, ny = -ay / L, ax / L                      # unit vector across the body
    sh_ratio = math.hypot(ls[0] - rs[0], ls[1] - rs[1]) / L
    hip_ratio = math.hypot(lh[0] - rh[0], lh[1] - rh[1]) / L
    nose_off = ((no[0] - msx) * nx + (no[1] - msy) * ny) / L
    zdiff = ((ls[2] - rs[2]) + (lh[2] - rh[2])) / 2   # MediaPipe: smaller z = closer to camera
    a1 = math.atan2(ls[1] - rs[1], ls[0] - rs[0]); a2 = math.atan2(lh[1] - rh[1], lh[0] - rh[0])
    twist = abs((math.degrees(a1 - a2) + 180) % 360 - 180)
    vis = min(ls[3], rs[3], lh[3], rh[3])
    return dict(width=(sh_ratio + hip_ratio) / 2, zdiff=zdiff, nose_off=nose_off, twist=twist, vis=vis)

def _softmax(xs):
    m = max(xs); e = [math.exp(x - m) for x in xs]; s = sum(e); return [v / s for v in e]

class PostureClassifier:
    """Uncalibrated: geometric rule. Calibrated: nearest centroid per camera (recommended,
    because camera height and angle change every ratio)."""
    KEYS = ["width", "zdiff", "nose_off"]
    def __init__(self, calib_path=None):
        self.calib = None; self.calib_path = calib_path
        if calib_path and Path(calib_path).exists(): self.calib = json.loads(Path(calib_path).read_text())
    def predict(self, kp):
        f = features(kp)
        if f["vis"] < 0.5:
            return dict(probs={c: 1 / 3 for c in CLASSES}, best=None, conf=0.0, reason="shoulders or hips not visible (cover?)", feat=f)
        if self.calib:
            d = []
            for c in CLASSES:
                mu, sd = self.calib[c]["mean"], self.calib[c]["sd"]
                d.append(-0.5 * sum(((f[k] - mu[k]) / max(sd[k], 1e-3)) ** 2 for k in self.KEYS))
            p = _softmax(d)
        else:
            side = (0.38 - f["width"]) / 0.08
            lr = f["zdiff"] / 0.06
            p = _softmax([-side, side / 2 + lr, side / 2 - lr])
        probs = dict(zip(CLASSES, p)); best = max(probs, key=probs.get)
        return dict(probs=probs, best=best, conf=probs[best], reason=None, feat=f)
    def fit_calibration(self, samples):
        """samples: {class: [feature dicts]} gathered while a person holds each posture."""
        out = {}
        for c, fs in samples.items():
            mu = {k: sum(x[k] for x in fs) / len(fs) for k in self.KEYS}
            sd = {k: (sum((x[k] - mu[k]) ** 2 for x in fs) / max(len(fs) - 1, 1)) ** 0.5 + 0.02 for k in self.KEYS}
            out[c] = dict(mean=mu, sd=sd, n=len(fs))
        self.calib = out
        if self.calib_path: Path(self.calib_path).write_text(json.dumps(out, indent=1))
        return out

class HoldConfirmer:
    """A new posture must hold for HOLD minutes of care time at >= MIN_CONF before it counts
    as a turn. Anything shorter is logged as a shift. Frames with a second person are ignored."""
    def __init__(self, posture, hold_min=3.0, min_conf=0.6):
        self.confirmed, self.hold, self.min_conf = posture, hold_min, min_conf
        self.cand = None; self.since = None
    def update(self, t, pred, masked=False):
        if masked or pred["best"] is None or pred["conf"] < self.min_conf: return None
        b = pred["best"]
        if b == self.confirmed:
            if self.cand is not None:
                ev = dict(type="shift", toward=self.cand, minutes=round(t - self.since, 1))
                self.cand = None; return ev
            return None
        if b != self.cand: self.cand, self.since = b, t; return None
        if t - self.since >= self.hold:
            ev = dict(type="turn", frm=self.confirmed, to=b, at=self.since)
            self.confirmed, self.cand = b, None; return ev
        return None
