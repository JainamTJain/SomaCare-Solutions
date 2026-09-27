"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { FirstRun } from "../../components/FirstRun";
import { PositionMark } from "../../components/PositionMark";
import { api } from "../../lib/api";
import { clearSession, loadSession } from "../../lib/session";

type Area = { area: string; load_min: number; limit_min: number; ratio: number };
type ResidentRow = {
  resident_id: string;
  name: string;
  room: string;
  position: string;
  confidence_pct: number;
  uncertainty_pct: number;
  model_version: string;
  camera_online: boolean;
  camera_spectrum: string;
  worst_area: string | null;
  worst_ratio: number | null;
  extra_risk_steps: number;
  risk_multiplier: number | null;
  braden_total: number;
  areas: Area[];
  continence: {
    wet_probability: number | null;
    threshold: number | null;
    above_threshold: boolean;
    learning: boolean;
    reason_code: string | null;
  };
  visual_check: {
    would_verify: boolean;
    confidence_pct: number;
    uncertainty_pct: number;
    gate_pct: number;
    blocked_by: string[];
  };
  open_alert: { rule: string; status: string; inputs: Record<string, unknown> } | null;
  monitoring?: { mode?: string; label?: string | null };
};

type CameraRow = {
  device_id: string;
  room: string | null;
  resident: string | null;
  label: string;
  online: boolean;
  infrared: boolean;
  spectrum: string;
  fps: number | null;
  latency_ms: number | null;
  last_seen: string | null;
  uncertainty_pct: number | null;
  mic: string | null;
  cloud: string | null;
  simulated?: boolean;
  live?: boolean;
  monitoring?: string;
};

type InstallStep = { id: string; label: string; done: boolean };

type Board = {
  generated_at: string;
  position_model: string;
  position_model_note: string;
  verify_gate: number;
  gate1?: { status: string; note?: string; per_side_under_blanket?: string };
  sensing?: {
    default: string;
    computer: string;
    frames_leave_home: boolean;
    microphone: string;
    cloud: string;
  };
  cameras?: CameraRow[];
  install?: { note?: string | null; steps: InstallStep[] };
  residents: ResidentRow[];
};

function labeled(block: unknown) {
  const row = (block || {}) as { empty?: boolean; withheld?: string | null; rows?: unknown[] };
  if (row.withheld) return "withheld until consent";
  if (row.empty) return "none on file";
  return `${row.rows?.length ?? 0} on file`;
}

function FullPicture({ picture }: { picture: Record<string, unknown> }) {
  const risk = picture.risk as { extra_steps?: number; weight?: number; factors?: string[]; sedating_medication?: boolean } | undefined;
  const features = picture.continence_features as { diuretic?: number | null; withheld?: string | null } | undefined;
  const timeline = picture.timeline as { sources?: Record<string, { empty?: boolean; withheld?: string | null }> } | undefined;
  const meds = (picture.medications as { rows?: { medication_name: string; is_diuretic: boolean; is_sedating: boolean; in_diuretic_window?: boolean; in_sedating_window?: boolean }[] } | undefined)?.rows || [];
  return (
    <section className="saved">
      <h2>{String(picture.name || "Resident")}</h2>
      <p>
        Risk steps {risk?.extra_steps ?? "—"} · weight {risk?.weight ?? "—"}
        {risk?.sedating_medication ? " · sedating dose in the window" : ""}
      </p>
      <p className="muted">Factors: {(risk?.factors || []).join(", ") || "none"}</p>
      <p>Diagnoses: {labeled(picture.risk_factors)}</p>
      <p>Braden: {labeled(picture.braden)}</p>
      <p>Medications: {labeled(picture.medications)}</p>
      {meds.map((row) => (
        <p key={row.medication_name} className="muted">
          {row.medication_name}
          {row.is_diuretic ? " · diuretic" : ""}
          {row.in_diuretic_window ? " · inside 6 hours" : ""}
          {row.is_sedating ? " · sedating" : ""}
          {row.in_sedating_window ? " · inside the sedating window" : ""}
        </p>
      ))}
      <p>
        Continence diuretic feature: {features?.withheld ? "withheld until consent" : features?.diuretic ?? "—"}
      </p>
      <p className="muted">
        Timeline{" "}
        {timeline?.sources
          ? Object.entries(timeline.sources)
              .map(([name, source]) => `${name} ${source.withheld ? "withheld" : source.empty ? "empty" : "filled"}`)
              .join(" · ")
          : "—"}
      </p>
    </section>
  );
}

export default function EngineerPage() {
  const router = useRouter();
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [picture, setPicture] = useState<Record<string, unknown> | null>(null);
  const [who, setWho] = useState<string | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      router.replace("/");
      return;
    }
    setWho(session.staff.id);
    if (session.staff.role !== "engineer" && session.staff.role !== "admin") {
      setError("This view is for the engineer login.");
      return;
    }
    let stop = false;
    const pull = () =>
      api
        .engineer(session.token)
        .then((body) => {
          if (!stop) setBoard(body as Board);
        })
        .catch((err: Error) => {
          if (!stop) setError(err.message);
        });
    pull();
    const timer = window.setInterval(pull, 2000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [router]);

  return (
    <main className="desk">
      <p className="kicker">Sorety</p>
      {who && <FirstRun role="engineer" staffId={who} />}
      <div className="spread">
        <h1>Engineer</h1>
        <button
          className="choice"
          onClick={() => {
            clearSession();
            router.push("/");
          }}
        >
          Sign out
        </button>
      </div>
      <p className="banner">
        Gate 1 has not been run. A blanket blocks near-infrared the same way it blocks visible light. A covered
        side-of-body label does not reset the pressure timer.
      </p>
      <p className="muted">{board?.position_model_note}</p>
      <p className="muted">
        Live. Refreshes every 2 seconds. Model {board?.position_model}. Visual-check gate{" "}
        {board ? Math.round(board.verify_gate * 100) : "—"}%. One shared computer. Frames stay in the house.
      </p>
      {error && <p className="banner">{error}</p>}
      <h2>Baby monitors</h2>
      <div style={{ overflowX: "auto" }}>
        <table className="raw">
          <thead>
            <tr>
              <th>Room</th>
              <th>Camera</th>
              <th>Infrared</th>
              <th>fps</th>
              <th>Latency</th>
              <th>Uncertainty</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {(board?.cameras || []).map((camera) => (
              <tr key={camera.device_id}>
                <td>
                  {camera.room}
                  <div>{camera.resident}</div>
                </td>
                <td>
                  {camera.label}
                  <div className="muted">
                    {camera.online ? "online" : "offline"}
                  {camera.simulated || camera.live === false ? " · simulated" : ""}
                  {camera.monitoring === "schedule" ? " · monitored by schedule, not camera" : ""} · mic {camera.mic || "off"} · cloud{" "}
                  {camera.cloud || "off"}
                  </div>
                </td>
                <td>{camera.infrared ? "yes" : camera.spectrum}</td>
                <td>{camera.fps ?? "—"}</td>
                <td>{camera.latency_ms == null ? "—" : `${camera.latency_ms} ms`}</td>
                <td>{camera.uncertainty_pct == null ? "—" : `${camera.uncertainty_pct}%`}</td>
                <td>{camera.last_seen ? new Date(camera.last_seen).toLocaleTimeString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Install</h2>
      <p className="muted">{board?.install?.note}</p>
      <ul>
        {(board?.install?.steps || []).map((step) => (
          <li key={step.id}>
            {step.done ? "Done" : "Open"} — {step.label}
          </li>
        ))}
      </ul>
      <h2>Residents</h2>
      <div style={{ overflowX: "auto" }}>
        <table className="raw">
          <thead>
            <tr>
              <th>Room</th>
              <th>Position</th>
              <th>Confidence</th>
              <th>Uncertainty</th>
              <th>Score</th>
              <th>Incontinence</th>
              <th>Visual check</th>
            </tr>
          </thead>
          <tbody>
            {(board?.residents || []).map((row) => {
              const scheduled = row.monitoring?.mode === "schedule";
              return (
              <tr key={row.resident_id} onClick={() => {
                const next = open === row.resident_id ? null : row.resident_id;
                setOpen(next);
                setPicture(null);
                if (!next) return;
                const session = loadSession();
                if (!session) return;
                api.fullPicture(session.token, next).then((body) => setPicture(body as Record<string, unknown>));
              }}>
                <td>
                  {row.room}
                  <div>{row.name}</div>
                </td>
                <td>
                  {scheduled ? (
                    <div>{row.monitoring?.label}</div>
                  ) : (
                    <>
                      <PositionMark position={row.position} compact />
                      <div>
                        {row.position} · {row.camera_spectrum}
                        {row.camera_online ? "" : " · offline"}
                      </div>
                      <div className="muted">{row.model_version}</div>
                    </>
                  )}
                </td>
                <td>{scheduled || row.confidence_pct == null ? "—" : `${row.confidence_pct}%`}</td>
                <td>{scheduled || row.uncertainty_pct == null ? "—" : `${row.uncertainty_pct}%`}</td>
                <td>
                  {scheduled ? (
                    "—"
                  ) : (
                    <>
                      {row.worst_area || "—"} {row.worst_ratio ?? "—"}
                      <div className={row.worst_ratio !== null && row.worst_ratio >= 0.8 ? "meter hot" : "meter"}>
                        <span style={{ width: `${Math.min((row.worst_ratio || 0) * 100, 100)}%` }} />
                      </div>
                      <div className="muted">
                        steps {row.extra_risk_steps} · ×{row.risk_multiplier} · Braden {row.braden_total}
                      </div>
                    </>
                  )}
                </td>
                <td>
                  {row.continence.wet_probability === null ? "—" : row.continence.wet_probability}
                  <div className="muted">threshold {row.continence.threshold ?? "—"}</div>
                  <div className="muted">{row.continence.above_threshold ? "above threshold" : "under threshold"}</div>
                  {row.continence.learning && <div className="muted">learning</div>}
                </td>
                <td>
                  {scheduled ? (
                    <>
                      withheld
                      <div className="muted">{row.visual_check.blocked_by.join(", ")}</div>
                    </>
                  ) : (
                    <>
                      {row.visual_check.would_verify ? "pass" : "fail"}
                      <div className="muted">
                        {row.visual_check.confidence_pct}% confident · {row.visual_check.uncertainty_pct}% uncertain · gate{" "}
                        {row.visual_check.gate_pct}%
                      </div>
                      {row.visual_check.blocked_by.length > 0 && (
                        <div className="muted">{row.visual_check.blocked_by.join(", ")}</div>
                      )}
                    </>
                  )}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {open && picture && <FullPicture picture={picture} />}
    </main>
  );
}
