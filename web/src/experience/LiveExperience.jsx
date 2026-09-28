import { useEffect, useRef, useState } from "react";
import { LiveDemo, loadLandmarker } from "../somacare/liveDemo.js";
import { prepareDemo, wrapLandmarker } from "../demoControls.js";
import StickFigureStage from "../components/StickFigureStage.jsx";
import ReadingPanel from "../components/ReadingPanel.jsx";
import FloorPanel from "../components/FloorPanel.jsx";
import PhotoCheck from "../components/PhotoCheck.jsx";
import { CareFooter } from "../components/SiteChrome.jsx";

export default function LiveExperience({ extra, presenterRef, demoHolder }) {
  const videoRef = useRef(null);
  const demoRef = useRef(null);
  const stopRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [state, setState] = useState({ snapshot: null, frame: null });
  const [source, setSource] = useState("simulated");
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(60);
  const [note, setNote] = useState("");
  const [modelNote, setModelNote] = useState("");
  const [hasClip, setHasClip] = useState(false);
  const [videoEl, setVideoEl] = useState(null);

  useEffect(() => {
    let cancel = false;
    const video = ensureVideo(videoRef);
    setVideoEl(video);
    Promise.all([
      fetch("/demo/residents.json").then((r) => r.json()),
      fetch("/demo/demo_script.json").then((r) => r.json()),
      fetch("/demo/bed1-demo.mp4").then((r) => r.ok && (r.headers.get("content-type") || "").startsWith("video/")).catch(() => false),
    ]).then(([residents, script, clip]) => {
      if (cancel) return;
      const demo = prepareDemo(new LiveDemo({ residents, script, timeScale: 60 }));
      demo.onUpdate(({ snapshot, frame }) => setState({ snapshot, frame }));
      demoRef.current = demo;
      if (demoHolder) demoHolder.current = demo;
      setHasClip(clip);
      setReady(true);
      const first = clip ? "clip" : "simulated";
      setSource(first);
      startSource(first, demo, video, clip);
    }).catch(() => setNote("The resident list could not be loaded."));
    return () => {
      cancel = true;
      stopRef.current?.();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
    // start once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function clearMedia(video) {
    stopRef.current?.();
    stopRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (!video) return;
    video.pause();
    video.srcObject = null;
    video.removeAttribute("src");
    video.load();
  }

  async function startSource(kind, demo = demoRef.current, video = videoRef.current) {
    if (!demo || !video) return;
    clearMedia(video);
    setPlaying(true);
    setNote("");
    if (kind === "simulated") {
      demo.setMode("simulated");
      stopRef.current = demo.runSimulated(250);
      return;
    }
    demo.setMode("video");
    try {
      if (!demo.landmarker || demo.landmarker.__somaWrapped !== true && !demo._rawLandmarker) {
        setModelNote("Loading the pose model, about 10 MB, first time only");
        const raw = await loadLandmarker();
        demo._rawLandmarker = raw;
        demo.landmarker = wrapLandmarker(demo, raw);
        setModelNote("");
      } else if (!demo.landmarker.__somaWrapped) {
        demo.landmarker = wrapLandmarker(demo, demo.landmarker);
      }
    } catch {
      setModelNote("");
      setNote("Live tracking isn't supported on this device.");
      setSource("simulated");
      demo.setMode("simulated");
      stopRef.current = demo.runSimulated(250);
      return;
    }
    try {
      if (kind === "camera") {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        streamRef.current = stream;
        video.srcObject = stream;
      } else if (kind === "clip") {
        video.src = "/demo/bed1-demo.mp4";
        video.loop = true;
      }
      video.muted = true;
      video.playsInline = true;
      await video.play();
      stopRef.current = demo.attach(video);
    } catch {
      setNote(kind === "camera"
        ? "Camera access was blocked. Allow it in your browser, or try a video."
        : "That video could not be played.");
      setPlaying(false);
    }
  }

  function choose(kind) {
    setSource(kind);
    startSource(kind);
  }

  function onFile(file) {
    if (!file || !file.type.startsWith("video/")) return;
    const video = videoRef.current;
    const demo = demoRef.current;
    clearMedia(video);
    setSource("file");
    demo.setMode("video");
    video.src = URL.createObjectURL(file);
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.play().then(() => {
      stopRef.current = demo.attach(video);
      setPlaying(true);
    }).catch(() => setNote("That video could not be played."));
  }

  function togglePlay() {
    const demo = demoRef.current;
    const video = videoRef.current;
    if (source === "simulated") {
      if (playing) { stopRef.current?.(); stopRef.current = null; setPlaying(false); }
      else { stopRef.current = demo.runSimulated(250); setPlaying(true); }
      return;
    }
    if (video.paused) { video.play(); setPlaying(true); }
    else { video.pause(); setPlaying(false); }
  }

  function apply(kind, id, payload) {
    const demo = demoRef.current;
    if (!demo) return;
    const floor = demo.sim.floor;
    if (kind === "inputs") floor.updateInputs(id, payload);
    if (kind === "wet") floor.setWet(id, payload, "caregiver");
    if (kind === "suggest") floor.skinSuggestion(id, payload.site, payload.sug, true);
    if (kind === "confirm") floor.skinConfirm(id, payload.site, payload.finding, "Nurse");
    const snapshot = floor.snapshot();
    setState((s) => ({ ...s, snapshot }));
    const presenter = presenterRef?.current;
    if (presenter) {
      presenter.pending = { snapshot, frame: demo.lastUpdate?.frame ?? null };
      presenter.maybeSend(true);
    }
  }

  const demo = demoRef.current;
  const frame = state.frame;
  const showNoPerson = source !== "simulated" && frame?.noPersonFor > 8;

  return (
    <div className="experience">
      <div className="workspace">
        <div className="camera-col">
          <div className="segmented">
            <button type="button" className={source === "camera" ? "on" : ""} onClick={() => choose("camera")}>Live camera</button>
            <button type="button" className={source === "clip" ? "on" : ""} onClick={() => choose("clip")} disabled={!hasClip && source !== "clip"}>Demo clip</button>
            <button type="button" className={source === "file" ? "on" : ""} onClick={() => setSource("file")}>Your video</button>
            <button type="button" className={source === "simulated" ? "on" : ""} onClick={() => choose("simulated")}>Simulated resident</button>
          </div>
          {modelNote && <p className="caption">{modelNote}</p>}
          {source === "camera" && <p className="caption">Point your camera at someone lying down, or lie down in front of your laptop.</p>}
          {source === "file" && (
            <label className="drop"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]); }}
            >
              Drop a video of someone lying in bed
              <input type="file" accept="video/*" hidden onChange={(e) => onFile(e.target.files?.[0])} />
            </label>
          )}
          {source === "simulated" && <p className="caption">Simulated resident: generated stick figure, same engine.</p>}
          <StickFigureStage people={frame?.people} kp={frame?.kp} videoEl={videoEl} showVideo={source !== "simulated"} frame={frame} />
          <p className="caption">Your camera and videos stay on your device. Tracking runs in your browser and nothing is uploaded.</p>
          {note && <p className="banner">{note}</p>}
          <ReadingPanel frame={frame} snapshot={state.snapshot} />
          <div className="controls card">
            <div className="row">
              <button type="button" onClick={togglePlay} disabled={!ready}>
                {source === "simulated" ? (playing ? "Stop" : "Start") : (playing ? "Pause" : "Play")}
              </button>
              <button type="button" onClick={() => demoRef.current?.reset()} disabled={!ready}>Reset night</button>
              <strong className="clock">{state.snapshot?.clock || "22:00"}</strong>
            </div>
            <label className="speed">Care speed
              <input type="range" min="30" max="240" value={speed} onChange={(e) => {
                const n = Number(e.target.value);
                setSpeed(n);
                demoRef.current?.setTimeScale(n);
              }} />
              <span>1 second = {formatScale(speed)} care {formatScale(speed) === "1" ? "minute" : "minutes"}</span>
            </label>
            {source !== "simulated" && (
              <div className="cal">
                <label>Rotate
                  <select value={String(demo?.rotation ?? "auto")} onChange={(e) => demoRef.current?.setRotation(e.target.value)}>
                    <option value="auto">Auto</option>
                    <option value="0">0</option>
                    <option value="90">90</option>
                    <option value="180">180</option>
                    <option value="270">270</option>
                  </select>
                </label>
                <p>Calibrate this camera</p>
                <div className="row">
                  <button type="button" onClick={() => demo?.calibrate("supine")}>On back now</button>
                  <button type="button" onClick={() => demo?.calibrate("left30")}>On left side now</button>
                  <button type="button" onClick={() => demo?.calibrate("right30")}>On right side now</button>
                </div>
                <p className="caption">
                  {demo?.calib ? "Calibrated" : "Press each while the person clearly holds that position."}
                  {demo && !demo.calib && ` ${Object.entries(demo.calibrationStatus()).map(([k, n]) => `${k} ${n}`).join(", ")}`}
                </p>
              </div>
            )}
            {showNoPerson && (
              <p className="banner">
                Can't find a person. Try Rotate, move the camera higher, or switch to the simulated resident.
                <button type="button" onClick={() => choose("simulated")}>Simulated resident</button>
              </p>
            )}
            {source === "simulated" && (
              <div className="row">
                <button type="button" onClick={() => demo?.turnSimulated("supine")}>Turn her to back</button>
                <button type="button" onClick={() => demo?.turnSimulated("left30")}>Turn her to left</button>
                <button type="button" onClick={() => demo?.turnSimulated("right30")}>Turn her to right</button>
                <button type="button" onClick={() => demo?.shiftSimulated("right30")}>Brief shuffle</button>
                <button type="button" onClick={() => apply("wet", 1, true)}>Report wet</button>
              </div>
            )}
          </div>
        </div>
        <FloorPanel
          snapshot={state.snapshot}
          interactive
          timeScale={speed}
          onChange={(kind, id, payload) => apply(kind, id, payload)}
        />
      </div>
      {extra}
      <PhotoCheck
        snapshot={state.snapshot}
        interactive
        onSuggest={(id, site, sug) => apply("suggest", id, { site, sug })}
        onConfirm={(id, site, finding) => apply("confirm", id, { site, finding })}
      />
      <CareFooter />
    </div>
  );
}

function ensureVideo(ref) {
  if (!ref.current) {
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    ref.current = video;
  }
  return ref.current;
}

function formatScale(n) {
  const v = n / 60;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}
