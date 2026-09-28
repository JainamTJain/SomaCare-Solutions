"""Turn engine: resident inputs + sensor state + skin findings -> interval, due time,
next position and a plain-language reason for every step. Rules only, no ML, no LLM.
Every number here is a starting point a nurse must approve (see README)."""
POSTURES = {
    "supine":  {"label": "On back",          "short": "back",       "sites": ["sacrum", "heels"]},
    "left30":  {"label": "Left side, 30°",   "short": "left side",  "sites": ["lhip"]},
    "right30": {"label": "Right side, 30°",  "short": "right side", "sites": ["rhip"]},
}
SITES = {"sacrum": "Sacrum", "lhip": "Left hip", "rhip": "Right hip", "heels": "Heels"}
FINDINGS = {"intact": 0, "blanch": 1, "stage1": 2, "stage2": 3}
FINDING_TEXT = {"intact": "intact skin", "blanch": "redness that fades when pressed",
                "stage1": "redness that stays when pressed (Stage 1)",
                "stage2": "an open or blistered area (Stage 2 or deeper)"}
TIERS = ["Low", "Mild", "Moderate", "High", "Very high"]
DUE_COLS = ["Overdue", "Due within 30 min", "30 to 60 min", "Later tonight", "No timed turns"]

CFG = dict(frail_cfs=7, frail_factor=0.85, wet_factor=0.75, blanch_factor=0.75, floor_min=60)

def braden(r):
    return sum(r["braden"].values())

def base_interval(r):
    s, hd = braden(r), r.get("mattress") == "hdfoam"
    if s >= 19: return None, f"Braden {s} (low risk): no timed turns, movement is still tracked"
    if s <= 9:  return 120, f"Braden {s} (very high risk): every 2 h"
    if s <= 12: return (180, f"Braden {s} (high risk) on high-density foam: every 3 h, as in the TURN trial") if hd \
                  else (120, f"Braden {s} (high risk) on a standard mattress: every 2 h")
    if s <= 14: return (240, f"Braden {s} (moderate risk) on high-density foam: every 4 h, as in the TURN trial") if hd \
                  else (120, f"Braden {s} (moderate risk) on a standard mattress: every 2 h")
    return 240, f"Braden {s} (mild risk): every 4 h"

def effective_skin(r):
    """Confirmed findings, tightened by any provisional photo suggestion (never loosened)."""
    out = dict(r["skin"])
    for site, f in r.get("skin_provisional", {}).items():
        if FINDINGS[f] > FINDINGS[out.get(site, "intact")]: out[site] = f
    return out

def worst(skin, sites):
    return max((skin.get(s, "intact") for s in sites), key=lambda f: FINDINGS[f])

def plan(r, st, now):
    skin = effective_skin(r)
    steps, nurse, blocked = [], [], []
    base, why = base_interval(r); steps.append({"text": why, "factor": None})
    cur = st["posture"]; cur_sites = POSTURES[cur]["sites"]; f_cur = worst(skin, cur_sites)
    interval = base
    if interval is not None:
        if r.get("cfs", 0) >= CFG["frail_cfs"]:
            interval *= CFG["frail_factor"]; steps.append({"text": f"Clinical Frailty Scale {r['cfs']}: severely frail", "factor": "× 0.85"})
        if st.get("wet"):
            interval *= CFG["wet_factor"]; steps.append({"text": f"Wet since {st['wet_since_clock']}, not yet changed", "factor": "× 0.75"})
        if f_cur == "blanch":
            interval *= CFG["blanch_factor"]; steps.append({"text": f"{POSTURES[cur]['label']} loads skin with redness that fades when pressed", "factor": "× 0.75"})
        interval = round(max(CFG["floor_min"], interval))
    nm = r.get("nurse_max")
    if nm and (interval is None or nm < interval):
        interval = nm; steps.append({"text": f"Nurse limit {nm} min (the engine can shorten it, never lengthen it)", "factor": "cap"})
    elif nm:
        steps.append({"text": f"Nurse limit {nm} min holds; the calculated interval is already shorter", "factor": None})
    if FINDINGS[f_cur] >= 2:
        interval = 0
        steps.append({"text": f"{POSTURES[cur]['label']} loads {', '.join(SITES[s].lower() for s in cur_sites)} with {FINDING_TEXT[f_cur]}. Move off it now.", "factor": "now"})
    for site, f in skin.items():
        if f == "stage2": nurse.append(f"{SITES[site]}: {FINDING_TEXT['stage2']}. Nurse review and wound plan needed.")
    for site in r.get("skin_provisional", {}):
        nurse.append(f"{SITES[site]}: photo suggestion awaiting nurse confirmation.")
    cands = []
    for k in POSTURES:
        if k == cur: continue
        f = worst(skin, POSTURES[k]["sites"])
        rest = min(now - st["site_free_since"].get(s, now) if st["site_free_since"].get(s) is not None else 0
                   for s in POSTURES[k]["sites"])
        if FINDINGS[f] >= 2: blocked.append(f"{POSTURES[k]['label']}: {FINDING_TEXT[f]} on {SITES[POSTURES[k]['sites'][0]].lower()}")
        else: cands.append((FINDINGS[f], -rest, k, rest))
    cands.sort()
    nxt = cands[0][2] if cands else None
    if not cands: nurse.append("Every position loads injured skin. Nurse: consider a specialty surface.")
    due = None if interval is None else st["last_turn"] + interval
    return dict(interval=interval, due=due, mins_to_due=None if due is None else due - now,
                next=nxt, next_rest=cands[0][3] if cands else None, steps=steps, blocked=blocked, nurse=nurse)

def tier(r, st):
    b = braden(r); t = 4 if b <= 9 else 3 if b <= 12 else 2 if b <= 14 else 1 if b <= 18 else 0
    if any(FINDINGS[f] >= 2 for f in effective_skin(r).values()): t = 4
    if st.get("wet") and r.get("cfs", 0) >= 7: t = min(4, t + 1)
    return t

def due_col(p):
    m = p["mins_to_due"]
    if m is None: return 4
    return 0 if m < 0 else 1 if m <= 30 else 2 if m <= 60 else 3
