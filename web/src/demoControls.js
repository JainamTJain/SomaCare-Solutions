// Camera and simulated-resident controls around LiveDemo.
// Keypoints go into the engine; this file does not score risk or choose a turn.

let seed = 11;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 0.01;

function fakeKp(kind) {
  const w = { supine: 0.12, left30: 0.035, right30: 0.035 }[kind];
  const z = { supine: 0, left30: 0.12, right30: -0.12 }[kind];
  const vis = 0.92;
  const kp = Array.from({ length: 33 }, () => [0.5, 0.5, 0, vis]);
  kp[11] = [0.5 - w + rnd(), 0.35 + rnd(), z / 2, vis];
  kp[12] = [0.5 + w + rnd(), 0.35 + rnd(), -z / 2, vis];
  kp[23] = [0.5 - w * 0.8 + rnd(), 0.62 + rnd(), z / 2, vis];
  kp[24] = [0.5 + w * 0.8 + rnd(), 0.62 + rnd(), -z / 2, vis];
  kp[0] = [0.5 + (kind === "left30" ? 0.03 : kind === "right30" ? -0.03 : 0), 0.22, 0, vis];
  return kp;
}

function rotatePoint(p, deg) {
  const x = p[0], y = p[1];
  if (deg === 90) return [1 - y, x, p[2], p[3] ?? 1];
  if (deg === 180) return [1 - x, 1 - y, p[2], p[3] ?? 1];
  if (deg === 270) return [y, 1 - x, p[2], p[3] ?? 1];
  return [x, y, p[2], p[3] ?? 1];
}

function uprightScore(person, deg) {
  if (!person || person.length < 25) return -1;
  const p = person.map((pt) => rotatePoint(pt, deg));
  const ls = p[11], rs = p[12], lh = p[23], rh = p[24];
  const vis = Math.min(ls[3] ?? 1, rs[3] ?? 1, lh[3] ?? 1, rh[3] ?? 1);
  const sy = (ls[1] + rs[1]) / 2, hy = (lh[1] + rh[1]) / 2;
  return vis * 2 + (hy - sy);
}

function rotationChoice(landmarks, setting) {
  const person = landmarks?.[0];
  const fixed = setting === 0 || setting === 90 || setting === 180 || setting === 270;
  if (!person) return { deg: fixed ? setting : 0, text: "Finding the best angle..." };
  if (fixed) return { deg: setting, text: `Reading angle: ${setting}°` };
  const options = [0, 90, 180, 270].map((deg) => ({ deg, score: uprightScore(person, deg) }));
  options.sort((a, b) => b.score - a.score);
  if (options[0].score < 0.35 || options[0].score - options[1].score < 0.08) {
    return { deg: options[0].deg, text: "Finding the best angle..." };
  }
  return { deg: options[0].deg, text: `Reading angle: ${options[0].deg}°` };
}

export function prepareDemo(demo) {
  demo.rotation = "auto";
  demo._pose = "supine";
  demo._simT = 0;
  demo._shift = null;
  demo._noPersonFor = 0;
  demo._rotationText = null;
  demo.setMode = (mode) => { demo.mode = mode; };
  demo.setRotation = (value) => { demo.rotation = value === "auto" ? "auto" : Number(value); };
  demo.turnSimulated = (posture) => { demo._pose = posture; demo._shift = null; };
  demo.shiftSimulated = (posture) => { demo._shift = { pose: posture, until: demo._simT + 0.9 }; };
  const origReset = demo.reset.bind(demo);
  demo.reset = () => {
    origReset();
    demo._simT = 0;
    demo._pose = "supine";
    demo._shift = null;
    demo._noPersonFor = 0;
    demo._prevEmitVT = null;
  };
  const origEmit = demo._emit.bind(demo);
  demo._emit = (snapshot, frame) => {
    if (frame) {
      const vt = frame.videoT;
      const dt = demo._prevEmitVT == null || vt == null ? 0 : Math.max(0, vt - demo._prevEmitVT);
      if (vt != null) demo._prevEmitVT = vt;
      const noPerson = !(frame.people && frame.people.length);
      demo._noPersonFor = noPerson ? (demo._noPersonFor || 0) + dt : 0;
      frame.noPersonFor = demo._noPersonFor;
      frame.rotation = demo.mode === "simulated" ? null : demo._rotationText;
    }
    return origEmit(snapshot, frame);
  };
  demo.runSimulated = (intervalMs = 250) => {
    demo.mode = "simulated";
    let stop = false;
    const timer = setInterval(() => {
      if (stop) return;
      demo._simT += (intervalMs / 1000) * (demo.timeScale / 60);
      const pose = demo._shift && demo._simT < demo._shift.until ? demo._shift.pose : demo._pose;
      const people = [fakeKp(pose)];
      const { pred, masked, hold } = demo.sim.step(demo._simT, people);
      demo._emit(demo.sim.floor.snapshot(), {
        careT: demo._simT, videoT: null, people, kp: people[0], pred, masked,
        cand: hold.cand, hold: hold.cand ? demo._simT - hold.since : null, confirmed: hold.confirmed,
      });
    }, intervalMs);
    return () => { stop = true; clearInterval(timer); };
  };
  return demo;
}

export function wrapLandmarker(demo, landmarker) {
  if (!landmarker || landmarker.__somaWrapped) return landmarker;
  return {
    __somaWrapped: true,
    detectForVideo(video, ts) {
      const res = landmarker.detectForVideo(video, ts);
      const choice = rotationChoice(res.landmarks, demo.rotation);
      demo._rotationText = choice.text;
      return {
        landmarks: (res.landmarks || []).map((person) => person.map((p) => {
          const r = rotatePoint([p.x, p.y, p.z, p.visibility ?? 1], choice.deg);
          return { x: r[0], y: r[1], z: r[2], visibility: r[3] };
        })),
      };
    },
  };
}
