// node liveDemo.test.mjs ../../public/demo/residents.json ../../public/demo/demo_script.json
import fs from "fs";
import { LiveDemo } from "./liveDemo.js";
globalThis.performance ??= { now: () => Date.now() };
const [,, RES = "../../public/demo/residents.json", SCR = "../../public/demo/demo_script.json"] = process.argv;
const residents = JSON.parse(fs.readFileSync(RES)), script = JSON.parse(fs.readFileSync(SCR));
let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 0.016;
function kp(kind, vis = 0.9) {   // same synthetic body as the Python tests
  const w = { supine: 0.12, left30: 0.035, right30: 0.035 }[kind], z = { supine: 0, left30: 0.12, right30: -0.12 }[kind];
  const k = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, z: 0, visibility: vis }));
  k[11] = { x: 0.5 - w + rnd(), y: 0.35 + rnd(), z: z / 2 + rnd(), visibility: vis }; k[12] = { x: 0.5 + w + rnd(), y: 0.35 + rnd(), z: -z / 2 + rnd(), visibility: vis };
  k[23] = { x: 0.5 - w * 0.8 + rnd(), y: 0.62 + rnd(), z: z / 2 + rnd(), visibility: vis }; k[24] = { x: 0.5 + w * 0.8 + rnd(), y: 0.62 + rnd(), z: -z / 2 + rnd(), visibility: vis };
  k[0] = { x: 0.5 + (kind === "left30" ? 0.03 : kind === "right30" ? -0.03 : 0), y: 0.22, z: 0, visibility: vis };
  return k;
}
const poseAt = (t) => { const k = t < 60 ? "supine" : t < 200 ? "left30" : "right30"; const people = [kp(t >= 40 && t < 41 ? "right30" : k)];
  if (t >= 190 && t < 197) people.push(kp("supine")); return { landmarks: people }; };
const lm = { detectForVideo: (v) => poseAt(v.currentTime) };
const assert = (c, m) => { if (!c) { console.error("FAIL:", m); process.exitCode = 1; } else console.log("ok:", m); };

const demo = new LiveDemo({ residents, script, landmarker: lm }); const video = { currentTime: 0, duration: 300 };
const orders = new Set(), cells = new Set(); let maxLate = 0;
demo.onUpdate(({ snapshot }) => { orders.add(snapshot.residents.map((r) => r.id).join()); snapshot.residents.forEach((r) => cells.add(r.room + r.due_col));
  snapshot.tasks.forEach((t) => (maxLate = Math.max(maxLate, t.late_by))); });
for (let t = 0; t <= 300; t += 0.25) { video.currentTime = t; demo.tick(video); }
const ev = demo.lastUpdate.snapshot.events.map((e) => `${e.room}: ${e.text}`);
assert(ev.filter((e) => e.startsWith("Room 1: Turn")).length === 2, "two camera-confirmed turns in Room 1");
assert(ev.some((e) => e.includes("Brief shift")), "a brief shift is logged and not counted");
assert(ev.some((e) => e.startsWith("Room 2: Wet")), "scripted wet report reaches the floor");
assert(orders.size >= 5 && cells.size >= 10, `queue reorders (${orders.size}) and matrix moves (${cells.size})`);
const before = demo.careT; demo.setTimeScale(120); video.currentTime = 300.5; demo.tick(video);
assert(demo.careT - before === 1, "speed change keeps the care clock moving forward");
video.currentTime = 10; demo.tick(video); assert(demo.careT === 0, "scrubbing back restarts the night");
const d2 = new LiveDemo({ residents, landmarker: lm }); const v2 = { currentTime: 0, duration: 100, loop: true };
for (let t = 0; t <= 99; t += 0.5) { v2.currentTime = t; d2.tick(v2); } const c1 = d2.careT; v2.currentTime = 0.5; d2.tick(v2);
assert(d2.careT > c1, "a looping video continues the night");
const d3 = new LiveDemo({ residents, landmarker: lm }); const v3 = { currentTime: 0, duration: 300 };
for (const [lbl, t0] of [["supine", 5], ["left30", 100], ["right30", 250]]) { d3.calibrate(lbl, 10); for (let i = 0; i < 12; i++) { v3.currentTime = t0 + i * 0.25; d3.tick(v3); } }
assert(!!d3.calib, "calibration buttons fit this camera");
