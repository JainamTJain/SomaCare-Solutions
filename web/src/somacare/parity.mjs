import fs from "fs";
const [,, IN = "/tmp/parity_in.json", PY = "/tmp/py_replay.json", RES = "../../public/demo/residents.json"] = process.argv;
import { Simulation, clockStr, CLASSES } from "./engine.js";
const inp = JSON.parse(fs.readFileSync(IN)), py = JSON.parse(fs.readFileSync(PY));
const residents = JSON.parse(fs.readFileSync(RES));
const sim = new Simulation(residents, { script: inp.script });
let lastSnap = -1e9, seen = 0, fi = 0, si = 0, bad = 0;
const r2 = (x) => Math.round(x * 100) / 100, r1 = (x) => Math.round(x * 10) / 10;
const compact = (snap) => ({
  residents: snap.residents.map((r) => [r.id, r.posture, r.minutes_in_posture, r.wet, r.tier_name, r.due_col, r.plan.interval, r.plan.due_clock, r.plan.next_label, r.plan.steps.map((s) => s[0] ?? s.text)]),
  tasks: snap.tasks.map((t) => [t.rid, t.caregiver, t.start_clock, t.due_clock, t.late_by, t.instruction]),
  matrix: snap.matrix.cells });
const pyCompact = (f) => ({
  residents: f.residents.map((r) => [r.id, r.posture, r.mins, r.wet, r.tier, r.due_col, r.interval, r.due, r.next, r.steps.map((s) => s[0])]),
  tasks: f.tasks.map((t) => [t.rid, t.cg, t.start, t.due, t.late, t.what]), matrix: f.matrix });
function check(label, a, b) { const A = JSON.stringify(a), B = JSON.stringify(b); if (A !== B) { if (bad++ < 5) { let i = 0; while (A[i] === B[i]) i++; console.log("MISMATCH", label, "\n js:", A.slice(i - 120, i + 200), "\n py:", B.slice(i - 120, i + 200)); } } }
for (const st of inp.steps) {
  const t = st.vt * 60 / 60; const { pred, masked, hold } = sim.step(t, st.people);
  const pf = py.frames[fi++];
  check(`frame ${fi}`, [pred.best, r2(pred.conf), CLASSES.map((c) => r2(pred.probs[c])), hold.cand, hold.cand ? r1(t - hold.since) : null, sim.floor.S[1].posture],
                       [pf.best, pf.conf, pf.p, pf.cand, pf.hold, pf.confirmed]);
  if (t - lastSnap >= 1) {
    const snap = sim.floor.snapshot(); const ev = sim.floor.events;
    const nw = ev.length > seen ? ev.slice(0, ev.length - seen).reverse().map((e) => [e.clock, e.room, e.text]) : []; seen = ev.length;
    const ps = py.snapshots[si++];
    check(`snapshot ${si} @${ps.clock}`, [snap.clock, compact(snap), nw], [ps.clock, pyCompact(ps.floor), ps.new_events.map((e) => [e.clock, e.room, e.text])]);
    lastSnap = t;
  }
}
if (bad) process.exitCode = 1;
console.log(`compared ${fi} frames and ${si} snapshots: ${bad === 0 ? "IDENTICAL" : bad + " mismatches"}`);
