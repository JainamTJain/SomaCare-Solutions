import { useEffect, useRef, useState } from "react";
import { SITES } from "../somacare/engine.js";

const STEPS = ["Standardise", "Model reads the photo", "Suggestion", "Plan updates"];
const FINDING_BUTTONS = [
  ["intact", "Intact"],
  ["blanch", "Redness fades when pressed"],
  ["stage1", "Redness stays when pressed (Stage 1)"],
  ["stage2", "Open or blistered (Stage 2+)"],
];

export default function PhotoCheck({ snapshot, interactive, onSuggest, onConfirm }) {
  const [manifest, setManifest] = useState(null);
  const [residentId, setResidentId] = useState(1);
  const [site, setSite] = useState("sacrum");
  const [run, setRun] = useState(null);
  const [own, setOwn] = useState(false);

  useEffect(() => {
    fetch("/demo/photos/manifest.json").then((r) => (r.ok ? r.json() : null)).then(setManifest).catch(() => setManifest(null));
  }, []);

  useEffect(() => {
    if (!run || run.step >= STEPS.length) return;
    const t = setTimeout(() => setRun((cur) => (cur ? { ...cur, step: cur.step + 1 } : cur)), 600);
    return () => clearTimeout(t);
  }, [run]);

  const sent = useRef(false);
  useEffect(() => {
    if (run?.step === STEPS.length && run.photo && !sent.current) {
      sent.current = true;
      onSuggest?.(residentId, site, { status: run.photo.status, finding: run.photo.finding, message: run.photo.message });
    }
  }, [run, onSuggest, residentId, site]);

  function start(photo) {
    setOwn(false);
    sent.current = false;
    setRun({ photo, step: 0 });
  }

  function dropOwn(e) {
    const file = e.dataTransfer?.files?.[0];
    if (file && file.type.startsWith("image/")) {
      e.preventDefault();
      setOwn(true);
      setRun(null);
    }
  }

  const photos = manifest?.photos || [];
  const residents = snapshot?.residents || [];
  const done = run && run.step >= STEPS.length;

  return (
    <section className="card photos" onDragOver={(e) => e.preventDefault()} onDrop={dropOwn}>
      <h2>Photo check</h2>
      <p className="caption">Scored with a published model (see credits). A suggestion can only tighten the plan until a nurse confirms.</p>
      {own && <p className="banner">New photos are scored on the care-home computer, not in the browser. Try one of these to see the model's real answer.</p>}
      {!photos.length && <p>No scored photos are published yet.</p>}
      <div className="thumbs">
        {photos.map((photo) => (
          <button
            type="button"
            key={photo.file}
            className="thumb"
            draggable
            onDragStart={(e) => e.dataTransfer.setData("text/photo", photo.file)}
            onClick={() => start(photo)}
          >
            <img src={`/demo/photos/${photo.file}`} alt="" />
            <small>{[photo.credit, photo.licence].filter(Boolean).join(" · ")}</small>
          </button>
        ))}
      </div>
      <div className="photo-setup">
        <label>Resident
          <select value={residentId} onChange={(e) => setResidentId(Number(e.target.value))}>
            {residents.map((r) => <option key={r.id} value={r.id}>{r.room} · {r.name}</option>)}
          </select>
        </label>
        <BodyMap site={site} onSite={setSite} onDropPhoto={(name) => {
          const photo = photos.find((p) => p.file === name);
          if (photo) start(photo);
        }} />
      </div>
      {run && (
        <ol className="steps">
          {STEPS.map((label, i) => <li key={label} className={i < run.step ? "done" : i === run.step ? "now" : ""}>{label}</li>)}
        </ol>
      )}
      {done && (
        <div className="suggestion">
          <p>{run.photo.message}</p>
          {run.photo.probs && Object.entries(run.photo.probs).map(([name, p]) => (
            <div className="bar-row" key={name}>
              <span>{name.replaceAll("_", " ")}</span>
              <div className="bar"><span style={{ width: `${Math.round(p * 100)}%` }} /></div>
              <span className="pct">{Math.round(p * 100)}%</span>
            </div>
          ))}
          {interactive && (
            <div className="row nurse">
              {FINDING_BUTTONS.map(([value, label]) => (
                <button type="button" key={value} onClick={() => onConfirm?.(residentId, site, value)}>{label}</button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function BodyMap({ site, onSite, onDropPhoto }) {
  const zones = [
    ["sacrum", 70, 118, 60, 70],
    ["lhip", 18, 150, 48, 48],
    ["rhip", 134, 150, 48, 48],
    ["heels", 62, 250, 76, 36],
  ];
  return (
    <svg className="body" viewBox="0 0 200 320" role="img" aria-label="Body sites">
      <ellipse cx="100" cy="46" rx="26" ry="30" />
      <rect x="78" y="82" width="44" height="150" rx="16" />
      {zones.map(([id, x, y, w, h]) => (
        <rect
          key={id}
          className={site === id ? "zone on" : "zone"}
          x={x} y={y} width={w} height={h} rx="12"
          onClick={() => onSite(id)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); e.stopPropagation(); onSite(id); onDropPhoto(e.dataTransfer.getData("text/photo")); }}
        >
          <title>{SITES[id]}</title>
        </rect>
      ))}
      <text x="100" y="310" textAnchor="middle">{SITES[site]}</text>
    </svg>
  );
}
