// SomaCare turn engine, scheduler, posture classifier and floor, running in the browser.
// A line-for-line port of backend/somacare_live (engine.py, scheduler.py, posture.py, state.py)
// plus the demo caregivers from tools/record_replay.py. Parity-tested against the Python version.
// Rules only: no ML model and no LLM decides anything here.

export const pyRound = (x) => { // Python round(): halves go to the even number
  const f = Math.floor(x), d = x - f;
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
};
const round1 = (x) => Math.round(x * 10) / 10;
const round2 = (x) => Math.round(x * 100) / 100;

export const POSTURES = {
  supine:  { label: "On back",        short: "back",       sites: ["sacrum", "heels"] },
  left30:  { label: "Left side, 30°", short: "left side",  sites: ["lhip"] },
  right30: { label: "Right side, 30°", short: "right side", sites: ["rhip"] },
};
export const SITES = { sacrum: "Sacrum", lhip: "Left hip", rhip: "Right hip", heels: "Heels" };
export const FINDINGS = { intact: 0, blanch: 1, stage1: 2, stage2: 3 };
export const FINDING_TEXT = {
  intact: "intact skin", blanch: "redness that fades when pressed",
  stage1: "redness that stays when pressed (Stage 1)",
  stage2: "an open or blistered area (Stage 2 or deeper)",
};
export const TIERS = ["Low", "Mild", "Moderate", "High", "Very high"];
export const DUE_COLS = ["Overdue", "Due within 30 min", "30 to 60 min", "Later tonight", "No timed turns"];
export const CFG = { frail_cfs: 7, frail_factor: 0.85, wet_factor: 0.75, blanch_factor: 0.75, floor_min: 60 };
const NIGHT_START_MIN = 22 * 60;

export function clockStr(m) {
  const v = ((pyRound(NIGHT_START_MIN + m) % 1440) + 1440) % 1440;
  return `${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`;
}
export const braden = (r) => Object.values(r.braden).reduce((a, b) => a + b, 0);

export function baseInterval(r) {
  const s = braden(r), hd = r.mattress === "hdfoam";
  if (s >= 19) return [null, `Braden ${s} (low risk): no timed turns, movement is still tracked`];
  if (s <= 9) return [120, `Braden ${s} (very high risk): every 2 h`];
  if (s <= 12) return hd ? [180, `Braden ${s} (high risk) on high-density foam: every 3 h, as in the TURN trial`]
                         : [120, `Braden ${s} (high risk) on a standard mattress: every 2 h`];
  if (s <= 14) return hd ? [240, `Braden ${s} (moderate risk) on high-density foam: every 4 h, as in the TURN trial`]
                         : [120, `Braden ${s} (moderate risk) on a standard mattress: every 2 h`];
  return [240, `Braden ${s} (mild risk): every 4 h`];
}
export function effectiveSkin(r) {
  const out = { ...r.skin };
  for (const [site, f] of Object.entries(r.skin_provisional || {}))
    if (FINDINGS[f] > FINDINGS[out[site] || "intact"]) out[site] = f;
  return out;
}
const worst = (skin, sites) => sites.map((s) => skin[s] || "intact")
  .reduce((a, b) => (FINDINGS[b] > FINDINGS[a] ? b : a));

export function plan(r, st, now) {
  const skin = effectiveSkin(r), steps = [], nurse = [], blocked = [];
  const [base, why] = baseInterval(r); steps.push({ text: why, factor: null });
  const cur = st.posture, curSites = POSTURES[cur].sites, fCur = worst(skin, curSites);
  let interval = base;
  if (interval !== null) {
    if ((r.cfs || 0) >= CFG.frail_cfs) { interval *= CFG.frail_factor; steps.push({ text: `Clinical Frailty Scale ${r.cfs}: severely frail`, factor: "× 0.85" }); }
    if (st.wet) { interval *= CFG.wet_factor; steps.push({ text: `Wet since ${st.wet_since_clock}, not yet changed`, factor: "× 0.75" }); }
    if (fCur === "blanch") { interval *= CFG.blanch_factor; steps.push({ text: `${POSTURES[cur].label} loads skin with redness that fades when pressed`, factor: "× 0.75" }); }
    interval = pyRound(Math.max(CFG.floor_min, interval));
  }
  const nm = r.nurse_max;
  if (nm && (interval === null || nm < interval)) { interval = nm; steps.push({ text: `Nurse limit ${nm} min (the engine can shorten it, never lengthen it)`, factor: "cap" }); }
  else if (nm) steps.push({ text: `Nurse limit ${nm} min holds; the calculated interval is already shorter`, factor: null });
  if (FINDINGS[fCur] >= 2) {
    interval = 0;
    steps.push({ text: `${POSTURES[cur].label} loads ${curSites.map((s) => SITES[s].toLowerCase()).join(", ")} with ${FINDING_TEXT[fCur]}. Move off it now.`, factor: "now" });
  }
  for (const [site, f] of Object.entries(skin)) if (f === "stage2") nurse.push(`${SITES[site]}: ${FINDING_TEXT.stage2}. Nurse review and wound plan needed.`);
  for (const site of Object.keys(r.skin_provisional || {})) nurse.push(`${SITES[site]}: photo suggestion awaiting nurse confirmation.`);
  const cands = [];
  for (const k of Object.keys(POSTURES)) {
    if (k === cur) continue;
    const f = worst(skin, POSTURES[k].sites);
    const rest = Math.min(...POSTURES[k].sites.map((s) => (st.site_free_since[s] ?? null) !== null ? now - st.site_free_since[s] : 0));
    if (FINDINGS[f] >= 2) blocked.push(`${POSTURES[k].label}: ${FINDING_TEXT[f]} on ${SITES[POSTURES[k].sites[0]].toLowerCase()}`);
    else cands.push([FINDINGS[f], -rest, k, rest]);
  }
  cands.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0));
  const next = cands.length ? cands[0][2] : null;
  if (!cands.length) nurse.push("Every position loads injured skin. Nurse: consider a specialty surface.");
  const due = interval === null ? null : st.last_turn + interval;
  return { interval, due, mins_to_due: due === null ? null : due - now, next,
           next_rest: cands.length ? cands[0][3] : null, steps, blocked, nurse };
}
export function tier(r, st) {
  const b = braden(r); let t = b <= 9 ? 4 : b <= 12 ? 3 : b <= 14 ? 2 : b <= 18 ? 1 : 0;
  if (Object.values(effectiveSkin(r)).some((f) => FINDINGS[f] >= 2)) t = 4;
  if (st.wet && (r.cfs || 0) >= 7) t = Math.min(4, t + 1);
  return t;
}
export function dueCol(p) {
  const m = p.mins_to_due; if (m === null) return 4;
  return m < 0 ? 0 : m <= 30 ? 1 : m <= 60 ? 2 : 3;
}

// ---------------- scheduler ----------------
export const TASK_MIN = { turn: 6, change_turn: 9 }, TRAVEL_MIN = 2;
function cmpTuple(a, b) { for (let i = 0; i < a.length; i++) { if (a[i] < b[i]) return -1; if (a[i] > b[i]) return 1; } return 0; }
export function rank(entries) {
  const key = (e) => { const m = e.plan.mins_to_due; return [e.wet ? 0 : m !== null ? 1 : 2, m !== null ? m : 1e9, -e.tier]; };
  const timed = entries.filter((e) => e.plan.mins_to_due !== null || e.wet);
  return [...timed].sort((a, b) => cmpTuple(key(a), key(b))).concat(entries.filter((e) => !timed.includes(e)));
}
export function schedule(entries, caregivers, now, horizon = 120) {
  const freeAt = Object.fromEntries(caregivers.map((c) => [c, now])); const tasks = [];
  for (const e of rank(entries)) {
    const p = e.plan;
    if (!e.wet && (p.mins_to_due === null || p.mins_to_due > horizon)) continue;
    const kind = e.wet ? "change_turn" : "turn";
    let cg = null; for (const c of caregivers) if (cg === null || freeAt[c] < freeAt[cg]) cg = c;
    let start = Math.max(cg !== null ? freeAt[cg] : now, now) + TRAVEL_MIN;
    const due = p.due !== null ? p.due : now;
    if (!e.wet) start = Math.max(start, due - 15);
    const late = p.due !== null ? Math.max(0, start - due) : 0;
    if (cg !== null) freeAt[cg] = start + TASK_MIN[kind];
    const to = p.next ? POSTURES[p.next].short : "a position the nurse chooses";
    tasks.push({ rid: e.rid, caregiver: cg, kind, start, due, late_by: pyRound(late),
                 instruction: (kind === "change_turn" ? "Change the brief, then turn to " : "Turn to ") + to });
  }
  return tasks;
}

// ---------------- posture from keypoints ----------------
export const CLASSES = ["supine", "left30", "right30"];
const NOSE = 0, LSH = 11, RSH = 12, LHIP = 23, RHIP = 24;
export function features(kp) { // kp: 33 x [x, y, z, visibility]
  const ls = kp[LSH], rs = kp[RSH], lh = kp[LHIP], rh = kp[RHIP], no = kp[NOSE];
  const msx = (ls[0] + rs[0]) / 2, msy = (ls[1] + rs[1]) / 2, mhx = (lh[0] + rh[0]) / 2, mhy = (lh[1] + rh[1]) / 2;
  const ax = mhx - msx, ay = mhy - msy, L = Math.hypot(ax, ay) || 1e-6, nx = -ay / L, ny = ax / L;
  const sh = Math.hypot(ls[0] - rs[0], ls[1] - rs[1]) / L, hip = Math.hypot(lh[0] - rh[0], lh[1] - rh[1]) / L;
  const nose_off = ((no[0] - msx) * nx + (no[1] - msy) * ny) / L;
  const zdiff = ((ls[2] - rs[2]) + (lh[2] - rh[2])) / 2;
  const a1 = Math.atan2(ls[1] - rs[1], ls[0] - rs[0]), a2 = Math.atan2(lh[1] - rh[1], lh[0] - rh[0]);
  const deg = ((((a1 - a2) * 180 / Math.PI) + 180) % 360 + 360) % 360 - 180;
  return { width: (sh + hip) / 2, zdiff, nose_off, twist: Math.abs(deg), vis: Math.min(ls[3], rs[3], lh[3], rh[3]) };
}
const softmax = (xs) => { const m = Math.max(...xs), e = xs.map((x) => Math.exp(x - m)), s = e.reduce((a, b) => a + b); return e.map((v) => v / s); };
export class PostureClassifier {
  static KEYS = ["width", "zdiff", "nose_off"];
  constructor(calib = null) { this.calib = calib; }
  predict(kp) {
    const f = features(kp);
    if (f.vis < 0.5) return { probs: { supine: 1 / 3, left30: 1 / 3, right30: 1 / 3 }, best: null, conf: 0, reason: "shoulders or hips not visible (cover?)", feat: f };
    let p;
    if (this.calib) {
      p = softmax(CLASSES.map((c) => { const { mean, sd } = this.calib[c];
        return -0.5 * PostureClassifier.KEYS.reduce((a, k) => a + ((f[k] - mean[k]) / Math.max(sd[k], 1e-3)) ** 2, 0); }));
    } else {
      const side = (0.38 - f.width) / 0.08, lr = f.zdiff / 0.06;
      p = softmax([-side, side / 2 + lr, side / 2 - lr]);
    }
    const probs = Object.fromEntries(CLASSES.map((c, i) => [c, p[i]]));
    let best = CLASSES[0]; for (const c of CLASSES) if (probs[c] > probs[best]) best = c;
    return { probs, best, conf: probs[best], reason: null, feat: f };
  }
  fitCalibration(samples) {
    const out = {};
    for (const [c, fs] of Object.entries(samples)) {
      const mean = {}, sd = {};
      for (const k of PostureClassifier.KEYS) {
        mean[k] = fs.reduce((a, x) => a + x[k], 0) / fs.length;
        sd[k] = Math.sqrt(fs.reduce((a, x) => a + (x[k] - mean[k]) ** 2, 0) / Math.max(fs.length - 1, 1)) + 0.02;
      }
      out[c] = { mean, sd, n: fs.length };
    }
    this.calib = out; return out;
  }
}
export class HoldConfirmer {
  constructor(posture, holdMin = 3.0, minConf = 0.6) { this.confirmed = posture; this.hold = holdMin; this.minConf = minConf; this.cand = null; this.since = null; }
  update(t, pred, masked = false) {
    if (masked || pred.best === null || pred.conf < this.minConf) return null;
    const b = pred.best;
    if (b === this.confirmed) {
      if (this.cand !== null) { const ev = { type: "shift", toward: this.cand, minutes: round1(t - this.since) }; this.cand = null; return ev; }
      return null;
    }
    if (b !== this.cand) { this.cand = b; this.since = t; return null; }
    if (t - this.since >= this.hold) { const ev = { type: "turn", frm: this.confirmed, to: b, at: this.since }; this.confirmed = b; this.cand = null; return ev; }
    return null;
  }
}

// ---------------- the floor ----------------
export class Floor {
  constructor(residents, caregivers = ["Maria", "Joy"]) {
    this.t = 0; this.R = {}; this.S = {}; this.order = [];
    for (const r0 of residents) {
      const r = structuredClone(r0); r.skin_provisional = r.skin_provisional || {};
      this.R[r.id] = r; this.order.push(r.id);
      const p = r.start_posture;
      this.S[r.id] = { posture: p, last_turn: r.last_turn, wet: false, wet_since_clock: null,
        site_free_since: Object.fromEntries(Object.keys(SITES).map((s) => [s, POSTURES[p].sites.includes(s) ? null : r.last_turn])),
        hold: new HoldConfirmer(p), live: null, done_pending: null };
    }
    this.caregivers = [...caregivers]; this.events = []; this.version = 0; this.lastPhoto = {}; this.busy = {};
  }
  now() { return this.t; }
  setTime(t) { this.t = t; }
  _log(rid, text, kind = "info") {
    this.events.unshift({ t: round1(this.t), clock: clockStr(this.t), room: rid ? this.R[rid].room : "", text, kind });
    if (this.events.length > 200) this.events.pop(); this.version++;
  }
  _applyTurn(rid, frm, to, at, how) {
    const s = this.S[rid];
    for (const site of POSTURES[frm].sites) s.site_free_since[site] = at;
    for (const site of POSTURES[to].sites) s.site_free_since[site] = null;
    s.posture = to; s.last_turn = at; s.hold.confirmed = to;
    this._log(rid, `Turn to ${POSTURES[to].short} ${how}. Clock reset.`, "turn");
    if (s.done_pending) s.done_pending = null;
  }
  sensorUpdate(rid, pred, masked, keypoints = null) {
    const t = this.t, s = this.S[rid];
    s.live = { best: pred.best, conf: round2(pred.conf), probs: Object.fromEntries(Object.entries(pred.probs).map(([k, v]) => [k, round2(v)])),
               reason: pred.reason || (masked ? "second person at bedside" : null),
               twist: pred.feat ? pyRound(pred.feat.twist) : null, keypoints, t: round1(t) };
    const ev = s.hold.update(t, pred, masked);
    if (ev && ev.type === "turn") this._applyTurn(rid, ev.frm, ev.to, ev.at, "confirmed by the camera after a 3 min hold");
    else if (ev && ev.type === "shift") this._log(rid, `Brief shift toward ${POSTURES[ev.toward].short} (${ev.minutes.toFixed(1)} min). Not counted as a turn.`, "shift");
    this.version++;
  }
  manualPosture(rid, posture, who = "caregiver") { const s = this.S[rid]; if (posture !== s.posture) this._applyTurn(rid, s.posture, posture, this.t, `recorded by ${who}`); }
  setWet(rid, wet, source = "caregiver") {
    const s = this.S[rid]; s.wet = wet; s.wet_since_clock = wet ? clockStr(this.t) : null;
    this._log(rid, (wet ? "Wet: " : "Changed and dry: ") + `reported by ${source}.`, "wet");
  }
  updateInputs(rid, patch) {
    const r = this.R[rid];
    for (const k of ["braden", "cfs", "mattress", "nurse_max"]) if (k in patch) r[k] = k === "braden" ? { ...r[k], ...patch[k] } : patch[k];
    this._log(rid, "Resident inputs updated: " + Object.keys(patch).join(", "), "input");
  }
  skinSuggestion(rid, site, sug, autoApply = true) {
    this.lastPhoto[rid] = { site, ...sug, clock: clockStr(this.t) };
    const f = sug.finding;
    if (autoApply && f && f !== "intact") {
      this.R[rid].skin_provisional[site] = f;
      this._log(rid, `Bath photo, ${SITES[site].toLowerCase()}: model suggests ${FINDING_TEXT[f]}. Plan tightened until a nurse confirms.`, "skin");
    } else this._log(rid, `Bath photo, ${SITES[site].toLowerCase()}: ${sug.message || "saved for nurse review"}.`, "skin");
  }
  skinConfirm(rid, site, finding, nurse = "Nurse") {
    this.R[rid].skin[site] = finding; delete this.R[rid].skin_provisional[site];
    this._log(rid, `${nurse} confirmed ${SITES[site].toLowerCase()}: ${FINDING_TEXT[finding]}.`, "skin");
  }
  snapshot() {
    const now = this.t, rows = [];
    for (const rid of this.order) {
      const r = this.R[rid], s = this.S[rid];
      if (s.done_pending && now - s.done_pending.at > 8 && r.source === "video") {
        this._log(rid, `Round marked done by ${s.done_pending.by} but no turn seen by the camera. Please check.`, "alert"); s.done_pending = null;
      }
      const p = plan(r, s, now), tr = tier(r, s);
      rows.push({ id: rid, room: r.room, name: r.name, age: r.age, source: r.source, braden: braden(r), braden_parts: r.braden,
        cfs: r.cfs, mattress: r.mattress, nurse_max: r.nurse_max, skin: r.skin, skin_provisional: r.skin_provisional,
        posture: s.posture, posture_label: POSTURES[s.posture].label, minutes_in_posture: pyRound(now - s.last_turn),
        wet: s.wet, live: s.live, tier: tr, tier_name: TIERS[tr], due_col: dueCol(p),
        plan: { ...p, due_clock: p.due !== null ? clockStr(p.due) : null, next_label: p.next ? POSTURES[p.next].label : null },
        last_photo: this.lastPhoto[rid] || null });
    }
    const tasks = schedule(rows.map((x) => ({ rid: x.id, plan: x.plan, tier: x.tier, wet: x.wet })), this.caregivers, now);
    for (const tk of tasks) { tk.start_clock = clockStr(tk.start); tk.due_clock = clockStr(tk.due); tk.room = this.R[tk.rid].room; tk.name = this.R[tk.rid].name; }
    const taskIds = tasks.map((t) => t.rid), order = taskIds.concat(rows.map((x) => x.id).filter((id) => !taskIds.includes(id)));
    rows.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    const cells = [4, 3, 2, 1, 0].map((ti) => [0, 1, 2, 3, 4].map((ci) => rows.filter((x) => x.tier === ti && x.due_col === ci).map((x) => x.room)));
    return { now: round2(now), clock: clockStr(now), version: this.version, residents: rows, tasks,
             matrix: { rows: [...TIERS].reverse(), cols: DUE_COLS, cells }, events: this.events.slice(0, 40) };
  }
  // Demo only: beds without a camera are turned by the caregivers when their task starts.
  caregiversAct(videoBed) {
    let snap = this.snapshot();
    for (const cg of this.caregivers) {
      if ((this.busy[cg] ?? -1) > this.t) continue;
      const mine = snap.tasks.filter((t) => t.caregiver === cg && (t.rid !== videoBed || t.kind === "change_turn"));
      if (!mine.length || mine[0].start > this.t + TRAVEL_MIN + 0.01) continue;
      const t = mine[0], rid = t.rid, r = snap.residents.find((x) => x.id === rid);
      if (r.wet) this.setWet(rid, false, cg);
      if (r.plan.next && rid !== videoBed) this.manualPosture(rid, r.plan.next, cg);
      this.busy[cg] = this.t + TASK_MIN[t.kind] + TRAVEL_MIN;
      snap = this.snapshot();
    }
  }
}

// A running demo: one camera bed driven by pose keypoints, the rest by caregivers and a script.
export class Simulation {
  constructor(residents, { videoBed = 1, script = [], calib = null, caregivers = ["Maria", "Joy"] } = {}) {
    this.floor = new Floor(residents, caregivers); this.videoBed = videoBed;
    this.script = [...script].sort((a, b) => a.t - b.t); this.clf = new PostureClassifier(calib);
  }
  runScript(upto) {
    const f = this.floor;
    while (this.script.length && this.script[0].t <= upto) {
      const e = this.script.shift(), rid = e.rid;
      if (e.action === "wet") f.setWet(rid, true, e.source || "thermal sensor");
      else if (e.action === "skin_suggestion") f.skinSuggestion(rid, e.site, { status: e.finding ? "ok" : "unsure", finding: e.finding, message: e.message || "model suggestion" }, true);
      else if (e.action === "skin_finding") f.skinConfirm(rid, e.site, e.finding, e.nurse || "Nurse");
      else if (e.action === "inputs") f.updateInputs(rid, e.patch);
    }
  }
  // careMinute: care time now; people: array of 33-point keypoint arrays for each person seen.
  step(careMinute, people) {
    const f = this.floor; f.setTime(careMinute); this.runScript(careMinute);
    const masked = people.length > 1;
    const pred = people.length ? this.clf.predict(people[0])
      : { probs: { supine: 1 / 3, left30: 1 / 3, right30: 1 / 3 }, best: null, conf: 0, reason: "no person found", feat: null };
    f.sensorUpdate(this.videoBed, pred, masked, people.length ? people[0] : null);
    f.caregiversAct(this.videoBed);
    return { pred, masked, hold: f.S[this.videoBed].hold };
  }
}
