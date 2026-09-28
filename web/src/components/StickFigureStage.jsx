import { useEffect, useRef, useState } from "react";
import { POSTURES } from "../somacare/engine.js";

const BONES = [[0, 11], [0, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24], [23, 25], [25, 27], [24, 26], [26, 28]];

function visibility(point) {
  if (!point) return 0;
  return point.length > 3 ? point[3] : point[2] ?? 1;
}

function containBox(cw, ch, mw, mh) {
  if (!mw || !mh) return { x: cw * 0.12, y: ch * 0.1, w: cw * 0.76, h: ch * 0.78 };
  const scale = Math.min(cw / mw, ch / mh);
  const w = mw * scale, h = mh * scale;
  return { x: (cw - w) / 2, y: (ch - h) / 2, w, h };
}

function readingLabel(frame) {
  const best = frame?.pred?.best;
  if (!best || !POSTURES[best]) return frame?.pred?.reason ? "Unsure" : "Waiting for a reading";
  const name = POSTURES[best].label.split(",")[0];
  return `${name} · ${Math.round((frame.pred.conf || 0) * 100)}%`;
}

export default function StickFigureStage({ people, kp, videoEl, showVideo, frame }) {
  const boxRef = useRef(null);
  const canvasRef = useRef(null);
  const slotRef = useRef(null);
  const drawRef = useRef({});
  const [show, setShow] = useState(showVideo !== false);
  drawRef.current = { people: people || (kp ? [kp] : []), videoEl, show, frame };

  useEffect(() => { setShow(showVideo !== false); }, [showVideo]);

  useEffect(() => {
    const slot = slotRef.current;
    if (!videoEl || !slot) return;
    videoEl.classList.add("stage-video");
    slot.prepend(videoEl);
    return () => videoEl.classList.remove("stage-video");
  }, [videoEl]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const box = boxRef.current;
    if (!canvas || !box) return;
    let raf = 0;
    const paint = () => {
      const { people: bodies, videoEl: video, show: pixels, frame: fr } = drawRef.current;
      const rect = box.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, rect.width), h = Math.max(1, rect.height);
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const mediaW = video?.videoWidth || 0;
      const mediaH = video?.videoHeight || 0;
      const bed = containBox(w, h, pixels && mediaW ? mediaW : 0, pixels && mediaH ? mediaH : 0);
      ctx.strokeStyle = "#6b5344";
      ctx.lineWidth = 2;
      roundRect(ctx, bed.x + bed.w * 0.08, bed.y + bed.h * 0.18, bed.w * 0.84, bed.h * 0.7, 18);
      ctx.stroke();
      ctx.beginPath();
      ctx.ellipse(bed.x + bed.w * 0.5, bed.y + bed.h * 0.28, bed.w * 0.16, bed.h * 0.08, 0, 0, Math.PI * 2);
      ctx.stroke();
      (bodies || []).forEach((person, index) => drawPerson(ctx, person, bed, index === 0));
      raf = requestAnimationFrame(paint);
      void fr;
    };
    raf = requestAnimationFrame(paint);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    if (videoEl) videoEl.classList.toggle("is-hidden", !show);
  }, [videoEl, show]);

  return (
    <div className="stage-wrap">
      <div className="stage" ref={boxRef}>
        <div ref={slotRef} className="stage-slot" />
        <canvas ref={canvasRef} />
        <span className="corner-chip">{readingLabel(frame)}</span>
      </div>
      <div className="stage-tools">
        <button type="button" className={show ? "on" : ""} onClick={() => setShow(true)}>Show video</button>
        <button type="button" className={!show ? "on" : ""} onClick={() => setShow(false)}>Stick figure only</button>
      </div>
      {!show && <p className="caption">This is everything SomaCare keeps from each frame.</p>}
    </div>
  );
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawPerson(ctx, person, bed, resident) {
  if (!person) return;
  const pt = (i) => {
    const p = person[i];
    if (!p || visibility(p) < 0.5) return null;
    return [bed.x + p[0] * bed.w, bed.y + p[1] * bed.h];
  };
  ctx.lineWidth = resident ? 4 : 2;
  ctx.strokeStyle = resident ? "#f0c56e" : "#9a9084";
  ctx.lineCap = "round";
  for (const [a, b] of BONES) {
    const A = pt(a), B = pt(b);
    if (!A || !B) continue;
    ctx.beginPath();
    ctx.moveTo(A[0], A[1]);
    ctx.lineTo(B[0], B[1]);
    ctx.stroke();
  }
  ctx.fillStyle = resident ? "#f0c56e" : "#9a9084";
  for (let i = 0; i < person.length; i++) {
    const p = pt(i);
    if (!p) continue;
    ctx.beginPath();
    ctx.arc(p[0], p[1], resident ? 3.5 : 2.5, 0, Math.PI * 2);
    ctx.fill();
  }
  const head = pt(0);
  if (head) {
    ctx.beginPath();
    ctx.arc(head[0], head[1], resident ? 11 : 8, 0, Math.PI * 2);
    ctx.stroke();
    if (!resident) {
      ctx.fillStyle = "#d9d0c4";
      ctx.font = "12px Inter, sans-serif";
      ctx.fillText("Caregiver", head[0] + 14, head[1]);
    }
  }
}
