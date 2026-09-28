import { useEffect, useLayoutEffect, useRef, useState } from "react";

const BRADEN = [
  ["sensory", "Sensory", 4],
  ["moisture", "Moisture", 4],
  ["activity", "Activity", 4],
  ["mobility", "Mobility", 4],
  ["nutrition", "Nutrition", 4],
  ["friction", "Friction", 3],
];

export default function FloorPanel({ snapshot, interactive, onChange, timeScale = 60 }) {
  const [picked, setPicked] = useState(null);
  const [receivedAt, setReceivedAt] = useState(() => performance.now());
  const [tick, setTick] = useState(0);
  const hist = useRef({});
  const listRef = useRef(null);
  const prevBox = useRef(new Map());
  const matrixRef = useRef(null);
  const prevChip = useRef(new Map());

  useEffect(() => {
    if (!snapshot) return;
    setReceivedAt(performance.now());
    for (const r of snapshot.residents) {
      const h = hist.current[r.id] || [];
      h.push(r.plan.mins_to_due);
      hist.current[r.id] = h.slice(-60);
    }
  }, [snapshot]);

  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  useLayoutEffect(() => {
    const root = listRef.current;
    if (!root) return;
    const next = new Map();
    for (const el of root.querySelectorAll("[data-rid]")) {
      const box = el.getBoundingClientRect();
      const id = el.dataset.rid;
      next.set(id, box);
      const prev = prevBox.current.get(id);
      if (prev && prev.top - box.top > 2) {
        el.animate(
          [{ transform: `translateY(${prev.top - box.top}px)` }, { transform: "translateY(0)" }],
          { duration: 300, easing: "ease" }
        );
        el.classList.add("moved-up");
        setTimeout(() => el.classList.remove("moved-up"), 320);
      } else if (prev && Math.abs(prev.top - box.top) > 2) {
        el.animate(
          [{ transform: `translateY(${prev.top - box.top}px)` }, { transform: "translateY(0)" }],
          { duration: 300, easing: "ease" }
        );
      }
    }
    prevBox.current = next;
  }, [snapshot]);

  useLayoutEffect(() => {
    const root = matrixRef.current;
    if (!root) return;
    const next = new Map();
    for (const el of root.querySelectorAll("[data-room]")) {
      const box = el.getBoundingClientRect();
      const prev = prevChip.current.get(el.dataset.room);
      next.set(el.dataset.room, box);
      if (prev && (Math.abs(prev.left - box.left) > 2 || Math.abs(prev.top - box.top) > 2)) {
        el.animate(
          [{ transform: `translate(${prev.left - box.left}px, ${prev.top - box.top}px)` }, { transform: "translate(0, 0)" }],
          { duration: 300, easing: "ease" }
        );
      }
    }
    prevChip.current = next;
  }, [snapshot]);

  if (!snapshot) return <section className="card">Waiting for the floor…</section>;
  const residents = snapshot.residents || [];
  const selected = residents.find((r) => r.id === picked) || null;
  const late = (snapshot.tasks || []).some((t) => t.late_by > 15);
  const elapsedMin = ((performance.now() - receivedAt) / 1000) * (timeScale / 60);
  void tick;

  const groups = new Map();
  for (const t of snapshot.tasks || []) {
    const name = t.caregiver || "Unassigned";
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(t);
  }

  return (
    <section className="floor card">
      <h2>Who is next</h2>
      <ol className="queue" ref={listRef}>
        {residents.map((r, i) => {
          const remain = r.plan.mins_to_due == null ? null : r.plan.mins_to_due - elapsedMin;
          const overdue = remain != null && remain < 0;
          return (
            <li key={r.id} data-rid={r.id} className={picked === r.id ? "open" : ""}>
              <button type="button" className="queue-row" onClick={() => setPicked(r.id)}>
                <span className="pos">{i + 1}</span>
                <span>
                  <strong>{r.room}</strong> {r.name}
                  {r.room === "Room 1" && <em className="tag">Camera bed</em>}
                  {r.wet && <em className="tag wet">Wet</em>}
                  {r.plan.interval === 0 && <em className="tag now">Move off now</em>}
                </span>
                <span>{r.posture_label}</span>
                <span>{r.minutes_in_posture} min in position</span>
                <span className="tag tier">{r.tier_name}</span>
                <span className={overdue ? "due overdue" : "due"}>
                  {r.plan.due_clock || "No timed turn"}
                  {remain != null && (overdue ? ` · overdue ${Math.abs(Math.round(remain))} min` : ` · ${Math.max(0, Math.round(remain))} min`)}
                </span>
                <span>Turn to {r.plan.next_label || "a position the nurse chooses"}</span>
                <Spark values={hist.current[r.id] || []} />
              </button>
              {selected?.id === r.id && (
                <div className="why">
                  <h3>Why this time</h3>
                  <ul>
                    {r.plan.steps.map((s, n) => (
                      <li key={n}><span>{s.text}</span><span>{s.factor || ""}</span></li>
                    ))}
                  </ul>
                  <p>Turn every {r.plan.interval == null ? "—" : r.plan.interval} min, due {r.plan.due_clock || "—"}, next {r.plan.next_label || "—"}</p>
                  {r.plan.blocked?.length > 0 && <p>{r.plan.blocked.join(" ")}</p>}
                  {r.plan.nurse?.length > 0 && <p>{r.plan.nurse.join(" ")}</p>}
                  {interactive ? (
                    <WhatIf resident={r} onChange={onChange} />
                  ) : (
                    <p className="caption">The presenter controls the floor.</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <h2>Risk matrix</h2>
      <div className="matrix" ref={matrixRef}>
        <div className="matrix-corner" />
        {(snapshot.matrix?.cols || []).map((col) => <div key={col} className="matrix-col">{col}</div>)}
        {(snapshot.matrix?.rows || []).map((row, i) => (
          <div className="matrix-line" key={row}>
            <div className="matrix-row">{row}</div>
            {(snapshot.matrix.cols || []).map((col, j) => (
              <div className="cell" key={col}>
                {(snapshot.matrix.cells?.[i]?.[j] || []).map((room) => (
                  <span className="chip" data-room={room} key={room}>{room.replace("Room ", "")}</span>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>

      {late && <p className="banner">Two turns are due together. Consider calling another caregiver.</p>}
      <h2>Caregiver schedule</h2>
      {[...groups.entries()].map(([name, tasks]) => (
        <div key={name} className="shift">
          <h3>{name}</h3>
          {tasks.map((t, n) => (
            <p key={n}>
              {t.start_clock} · {t.room} · {t.instruction}
              {t.late_by > 0 && <em className="late"> late by {t.late_by} min</em>}
            </p>
          ))}
        </div>
      ))}

      <h2>What just changed</h2>
      <ul className="events">
        {(snapshot.events || []).slice(0, 8).map((e) => (
          <li key={`${e.t}-${e.text}`} className={`kind-${e.kind || "info"}`}>
            <span>{e.clock}</span> {e.room ? `${e.room}: ` : ""}{e.text}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Spark({ values }) {
  if (!values.length) return <svg className="spark" viewBox="0 0 60 16" />;
  const nums = values.map((v) => (v == null ? 0 : v));
  const min = Math.min(...nums), max = Math.max(...nums);
  const span = max - min || 1;
  const d = nums.map((v, i) => {
    const x = (i / Math.max(1, nums.length - 1)) * 60;
    const y = 15 - ((v - min) / span) * 14;
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return <svg className="spark" viewBox="0 0 60 16"><path d={d} /></svg>;
}

function WhatIf({ resident, onChange }) {
  return (
    <form className="whatif" onSubmit={(e) => e.preventDefault()}>
      <h3>What if</h3>
      <div className="fields">
        {BRADEN.map(([key, label, max]) => (
          <label key={key}>{label}
            <select
              value={resident.braden_parts?.[key] ?? 1}
              onChange={(e) => onChange("inputs", resident.id, { braden: { [key]: Number(e.target.value) } })}
            >
              {Array.from({ length: max }, (_, n) => n + 1).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        ))}
        <label>Frailty
          <select value={resident.cfs} onChange={(e) => onChange("inputs", resident.id, { cfs: Number(e.target.value) })}>
            {Array.from({ length: 9 }, (_, n) => n + 1).map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label>Mattress
          <select value={resident.mattress} onChange={(e) => onChange("inputs", resident.id, { mattress: e.target.value })}>
            <option value="hdfoam">High-density foam</option>
            <option value="standard">Standard</option>
          </select>
        </label>
        <label>Nurse limit
          <select
            value={resident.nurse_max ?? ""}
            onChange={(e) => onChange("inputs", resident.id, { nurse_max: e.target.value === "" ? null : Number(e.target.value) })}
          >
            <option value="">None</option>
            <option value="120">120</option>
            <option value="180">180</option>
            <option value="240">240</option>
          </select>
        </label>
      </div>
      <div className="row">
        <button type="button" onClick={() => onChange("wet", resident.id, true)}>Wet</button>
        <button type="button" onClick={() => onChange("wet", resident.id, false)}>Changed</button>
      </div>
    </form>
  );
}
