"""Rule-based detector (no ML, no LLM).
1. d = pelvis - chest  (cancels room drift)
2. Mask windows around turns (from the position pipeline) and caregiver-present windows,
   because both cause warm steps that are not voids.
3. Baseline = median of the previous BASELINE_S of clean samples in the same clean segment
   (a turn starts a new segment, so the baseline re-learns the new posture).
4. One-sided CUSUM on d - baseline -> 'possible wet' (silent, fast).
5. 'likely wet' when d later falls below the pre-event baseline (evaporative cooling)."""
import numpy as np

DET = dict(baseline_s=900, warmup_s=120, cusum_k=0.15, cusum_h=1.5, min_rise=0.25, peak_window_s=600,
           mask_pad_before_s=30, mask_after_turn_s=300, mask_after_hands_s=120,
           confirm_within_s=2400, confirm_drop=0.15, refractory_s=1800)

def build_mask(t, turns=(), hands=(), p=DET):
    m = np.zeros(t.size, bool)
    for tt in turns:
        m |= (t >= tt - p["mask_pad_before_s"]) & (t <= tt + p["mask_after_turn_s"])
    for h0, h1 in hands:
        m |= (t >= h0 - p["mask_pad_before_s"]) & (t <= h1 + p["mask_after_hands_s"])
    return m

def detect(t, pelvis, chest, turns=(), hands=(), fps=0.5, p=DET):
    d = np.asarray(pelvis) - np.asarray(chest)
    mask = build_mask(t, turns, hands, p)
    nb, nw = int(p["baseline_s"] * fps), int(p["warmup_s"] * fps)
    events, last_evt = [], -1e18
    seg_start, S, i = None, 0.0, 0
    base = np.full(t.size, np.nan)
    while i < t.size:
        if mask[i]:
            seg_start, S = None, 0.0; i += 1; continue
        if seg_start is None: seg_start = i
        if i - seg_start < nw:          # learning the new posture's level
            i += 1; continue
        lo = max(seg_start, i - nb)
        base[i] = np.median(d[lo:i])
        S = max(0.0, S + (d[i] - base[i]) - p["cusum_k"])
        if S > p["cusum_h"] and t[i] - last_evt > p["refractory_s"]:
            b0 = base[i]
            k_end = min(t.size, i + int(p["confirm_within_s"] * fps))
            k_pk = min(t.size, i + int(p["peak_window_s"] * fps))
            nxt = np.flatnonzero(mask[i:k_pk])
            if nxt.size: k_pk = i + int(nxt[0])      # never let a later turn/hand inflate the peak
            peak = float(d[i:max(k_pk, i + 1)].max() - b0)
            conf = None
            for k in range(i, k_end):
                if mask[k]: break
                if d[k] < b0 - p["confirm_drop"]:
                    conf = float(t[k]); break
            if peak >= p["min_rise"]:
                events.append(dict(t_possible=float(t[i]), t_confirmed=conf, peak_rise=peak))
                last_evt = t[i]
                # freeze baseline through the event so the wet level is not absorbed
                seg_start = None
                i = min(t.size, i + int(p["refractory_s"] * fps) // 4)
                S = 0.0
                continue
            S = 0.0
        i += 1
    return events

def score(nights, tol_s=900, **kw):
    tp = fn = fp = conf = 0; lat = []
    for nt in nights:
        ev = detect(nt.t, nt.pelvis, nt.chest, nt.turns, nt.hands, **kw)
        used = set()
        for v in nt.voids:
            hit = [k for k, e in enumerate(ev) if 0 <= e["t_possible"] - v <= tol_s and k not in used]
            if hit:
                tp += 1; used.add(hit[0]); lat.append(ev[hit[0]]["t_possible"] - v)
                conf += ev[hit[0]]["t_confirmed"] is not None
            else: fn += 1
        fp += len(ev) - len(used)
    return dict(sensitivity=round(tp / max(tp + fn, 1), 3),
                confirmed_share=round(conf / max(tp, 1), 3),
                false_possible_per_night=round(fp / len(nights), 3),
                median_latency_s=float(np.median(lat)) if lat else None, nights=len(nights))
