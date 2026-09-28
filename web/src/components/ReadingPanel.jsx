import { useEffect, useRef, useState } from "react";
import { POSTURES } from "../somacare/engine.js";

const BARS = [["supine", "On back"], ["left30", "Left side"], ["right30", "Right side"]];

export default function ReadingPanel({ frame, snapshot }) {
  const [banner, setBanner] = useState(false);
  const seen = useRef(new Set());
  useEffect(() => {
    const events = snapshot?.events || [];
    let fresh = false;
    for (const e of events) {
      const id = `${e.t}|${e.text}`;
      if (seen.current.has(id)) continue;
      seen.current.add(id);
      if (e.room === "Room 1" && String(e.text).startsWith("Turn to")) fresh = true;
    }
    if (!fresh) return;
    setBanner(true);
    const t = setTimeout(() => setBanner(false), 3000);
    return () => clearTimeout(t);
  }, [snapshot]);

  const probs = frame?.pred?.probs || {};
  let status = "Waiting for a reading";
  let tone = "";
  if (frame?.masked) { status = "Paused: caregiver at the bedside"; tone = "amber"; }
  else if (frame?.pred?.reason) { status = `Unsure: ${frame.pred.reason}`; tone = "amber"; }
  else if (frame?.cand) {
    const label = POSTURES[frame.cand]?.label || frame.cand;
    status = `Checking a turn to ${label}. It must hold 3 minutes to count.`;
    tone = "check";
  } else if (frame?.confirmed && POSTURES[frame.confirmed]) {
    status = `Steady: ${POSTURES[frame.confirmed].label}`;
  }
  const hold = Math.max(0, Math.min(1, (frame?.hold || 0) / 3));

  return (
    <section className="card reading">
      {banner && <p className="confirm-banner">Turn confirmed by the camera. Clock reset.</p>}
      {BARS.map(([key, label]) => (
        <div className="bar-row" key={key}>
          <span>{label}</span>
          <div className="bar"><span style={{ width: `${Math.round((probs[key] || 0) * 100)}%` }} /></div>
          <span className="pct">{Math.round((probs[key] || 0) * 100)}%</span>
        </div>
      ))}
      <p className={`status ${tone}`}>
        {tone === "check" && <HoldRing amount={hold} />}
        {status}
      </p>
      {frame?.rotation && <p className="caption">{frame.rotation}</p>}
    </section>
  );
}

function HoldRing({ amount }) {
  const r = 9, c = 2 * Math.PI * r;
  return (
    <svg className="ring" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r={r} />
      <circle cx="12" cy="12" r={r} strokeDasharray={`${c * amount} ${c}`} />
    </svg>
  );
}
