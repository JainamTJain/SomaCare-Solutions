"""The recorded ceiling-view test. Feed it a video's frames plus a ground-truth log and it reports what matters:
  frame accuracy by cover condition (counted over all frames, and only over frames where a claim was made)
  turn precision and recall, with the matching tolerance stated
  FALSE CONFIRMED TURNS on their own, per hour (the dangerous error), ready to feed safety_sim
  latency from a real change to the confirmed event

ground truth rows: dicts with ts (seconds), label (a position or 'transition'), cover, persons
frames: iterable of (ts, image, persons_in_zone)
"""
import numpy as np
from scipy.stats import chi2
from .turn import TurnDetector
from .config import TurnConfig

POSITIONS = {"back", "left", "right", "sitting", "out_of_bed"}


def poisson_upper_95(events, hours):
    """Upper 95 percent bound on a rate, given `events` observed in `hours`. With zero events this is about 3 / hours,
    so proving a rate of 0.002 per hour needs roughly 1,500 hours of footage. Short clips cannot prove a low rate."""
    return float(chi2.ppf(0.975, 2 * (events + 1)) / (2.0 * max(hours, 1e-9)))


def hours_needed_to_show(rate_per_hour):
    """Hours of footage with zero false confirmed turns needed before the 95 percent upper bound falls below the rate."""
    return 3.0 / rate_per_hour


def gt_label_at(rows, ts):
    lab, cov = None, None
    for r in rows:
        if r["ts"] <= ts:
            lab, cov = r["label"], r.get("cover", "none")
        else:
            break
    return lab, cov


def true_changes(rows, min_hold_s=20.0):
    """Times where the true position changes between two real positions, held at least min_hold_s."""
    segs = []
    for i, r in enumerate(rows):
        if r["label"] not in POSITIONS:
            continue
        end = rows[i + 1]["ts"] if i + 1 < len(rows) else r["ts"] + 3600
        if end - r["ts"] >= min_hold_s:
            segs.append((r["ts"], r["label"]))
    out = []
    for a, b in zip(segs, segs[1:]):
        if a[1] != b[1]:
            out.append((b[0], b[1]))
    return out


def evaluate_stream(frames, gt_rows, clf, turn_cfg: TurnConfig = TurnConfig(), tol_s=120.0, margin_s=6.0):
    gt_rows = sorted(gt_rows, key=lambda r: r["ts"])
    change_times = [t for t, _ in true_changes(gt_rows)]
    det = TurnDetector(turn_cfg)
    events, per_frame = [], []
    t0 = t1 = None
    for ts, img, persons in frames:
        t0 = ts if t0 is None else t0
        t1 = ts
        rd = clf.predict(img)
        events += det.update(ts, rd.label, rd.confidence, persons)
        lab, cov = gt_label_at(gt_rows, ts)
        near_change = any(abs(ts - c) <= margin_s for c in change_times) or lab not in POSITIONS
        if not near_change:
            per_frame.append((cov, lab, rd.label))
    # frame accuracy
    def stats(sel):
        if not sel:
            return None
        claimed = [x for x in sel if x[2] != "unknown"]
        ok_all = np.mean([x[1] == x[2] for x in sel])
        ok_claim = np.mean([x[1] == x[2] for x in claimed]) if claimed else float("nan")
        return dict(n=len(sel), accuracy_all=float(ok_all), accuracy_when_claimed=float(ok_claim),
                    unknown_rate=float(1 - len(claimed) / len(sel)))
    by_cover = {c: stats([x for x in per_frame if x[0] == c]) for c in sorted({x[0] for x in per_frame})}
    # events
    detected = [(e.ts, e.position, e.assisted) for e in events if e.kind in ("turn", "self_reposition") and e.previous]
    truth = list(true_changes(gt_rows))
    matched_truth, matched_det = set(), set()
    latencies = []
    for j, (dts, dpos, _) in enumerate(detected):
        for i, (tts, tpos) in enumerate(truth):
            if i in matched_truth:
                continue
            if tpos == dpos and 0 <= dts - tts <= tol_s:
                matched_truth.add(i); matched_det.add(j); latencies.append(dts - tts)
                break
    tp = len(matched_det)
    false_conf = len(detected) - tp
    hours = max((t1 - t0) / 3600.0, 1e-9) if t0 is not None else 1e-9
    return dict(
        frames=len(per_frame), by_cover=by_cover,
        true_changes=len(truth), detected_changes=len(detected), matched=tp,
        turn_precision=float(tp / len(detected)) if detected else float("nan"),
        turn_recall=float(tp / len(truth)) if truth else float("nan"),
        false_confirmed_turns=false_conf, false_confirms_per_hour=float(false_conf / hours),
        false_confirmed_share=float(false_conf / len(detected)) if detected else 0.0,
        false_confirms_per_hour_upper95=poisson_upper_95(false_conf, hours),
        median_latency_s=float(np.median(latencies)) if latencies else float("nan"),
        tolerance_s=tol_s, hours=float(hours),
        uncertain_events=sum(1 for e in events if e.kind == "uncertain"),
    )
