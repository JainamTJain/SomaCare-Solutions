// Drop a video -> MediaPipe Pose runs in the visitor's browser -> keypoints drive the engine live.
// The video never leaves the device. Only this file touches MediaPipe; engine.js stays pure.
import { Simulation, PostureClassifier } from "./engine.js";

const MP_VERSION = "0.10.14";
const WASM = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`;
const MODEL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task";

export async function loadLandmarker() {
  const { FilesetResolver, PoseLandmarker } = await import(/* @vite-ignore */ `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/+esm`);
  const vision = await FilesetResolver.forVisionTasks(WASM);
  const opts = (delegate) => ({ baseOptions: { modelAssetPath: MODEL, delegate }, runningMode: "VIDEO",
    numPoses: 2, minPoseDetectionConfidence: 0.3, minTrackingConfidence: 0.3 });
  try { return await PoseLandmarker.createFromOptions(vision, opts("GPU")); }
  catch { return await PoseLandmarker.createFromOptions(vision, opts("CPU")); }
}

export class LiveDemo {
  // residents: residents.json; script: demo_script.json; landmarker: from loadLandmarker() (or a fake in tests)
  constructor({ residents, script = [], landmarker, timeScale = 60, sampleHz = 4, videoBed = 1 }) {
    Object.assign(this, { residents, script, landmarker, timeScale, sampleHz, videoBed });
    this.listeners = []; this.calibLabel = null; this.calibNeed = 0; this.calibSamples = {}; this.calib = null;
    this.reset();
  }
  onUpdate(cb) { this.listeners.push(cb); return () => { this.listeners = this.listeners.filter((x) => x !== cb); }; }
  reset() {
    this.sim = new Simulation(this.residents, { videoBed: this.videoBed, script: structuredClone(this.script), calib: this.calib });
    this.careT = 0; this.lastVT = null; this.lastUpdate = null;
    this._emit(this.sim.floor.snapshot(), null);
  }
  setTimeScale(s) { this.timeScale = s; }            // care seconds per video second; applies from now on
  // Calibration: while the video clearly shows the posture, call calibrate("supine"|"left30"|"right30").
  calibrate(label, frames = 12) { this.calibLabel = label; this.calibNeed = frames; }
  calibrationStatus() { return Object.fromEntries(["supine", "left30", "right30"].map((c) => [c, (this.calibSamples[c] || []).length])); }

  // Called for every decoded video frame. Returns the update it emitted, or null.
  tick(video) {
    const vt = video.currentTime, dur = video.duration || Infinity;
    if (this.lastVT !== null && vt - this.lastVT < 1 / this.sampleHz && vt >= this.lastVT) return null;
    let dt = this.lastVT === null ? 0 : vt - this.lastVT;
    if (dt < 0) {
      if (video.loop && this.lastVT - vt > dur * 0.5) dt = (dur - this.lastVT) + vt;   // loop wrap: the night continues
      else { this.reset(); dt = 0; }                                                  // user scrubbed back: start over
    }
    this.lastVT = vt; this.careT += dt * this.timeScale / 60;
    const res = this.landmarker.detectForVideo(video, performance.now());
    const people = (res.landmarks || []).map((pts) => pts.map((p) => [p.x, p.y, p.z, p.visibility ?? 1]));
    if (this.calibLabel && people.length === 1) {
      const f = new PostureClassifier().predict(people[0]).feat;
      if (f.vis >= 0.5) (this.calibSamples[this.calibLabel] ||= []).push(f);
      if (--this.calibNeed <= 0) this.calibLabel = null;
      if (["supine", "left30", "right30"].every((c) => (this.calibSamples[c] || []).length >= 5)) {
        this.calib = new PostureClassifier().fitCalibration(this.calibSamples); this.sim.clf.calib = this.calib;
      }
    }
    const { pred, masked, hold } = this.sim.step(this.careT, people);
    const frame = { careT: this.careT, videoT: vt, people, kp: people[0] || null, pred, masked,
                    cand: hold.cand, hold: hold.cand ? this.careT - hold.since : null, confirmed: hold.confirmed };
    return this._emit(this.sim.floor.snapshot(), frame);
  }
  _emit(snapshot, frame) { const u = { snapshot, frame }; this.lastUpdate = u; for (const cb of this.listeners) cb(u); return u; }

  // Wire to a <video> element. Uses requestVideoFrameCallback where available.
  attach(video) {
    this.video = video; let stop = false;
    const loop = () => { if (stop) return; if (!video.paused && !video.ended) this.tick(video);
      if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(loop); else requestAnimationFrame(loop); };
    loop(); return () => { stop = true; };
  }
}
