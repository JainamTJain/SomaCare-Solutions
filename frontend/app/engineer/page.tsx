"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
};

type Board = {
  generated_at: string;
  position_model: string;
  position_model_note: string;
  verify_gate: number;
  residents: ResidentRow[];
};

export default function EngineerPage() {
  const router = useRouter();
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      router.replace("/");
      return;
    }
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
      <p className="muted">{board?.position_model_note}</p>
      <p className="muted">
        Live. Refreshes every 2 seconds. Model {board?.position_model}. Visual-check gate{" "}
        {board ? Math.round(board.verify_gate * 100) : "—"}%.
      </p>
      {error && <p className="banner">{error}</p>}
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
            {(board?.residents || []).map((row) => (
              <tr key={row.resident_id} onClick={() => setOpen(open === row.resident_id ? null : row.resident_id)}>
                <td>
                  {row.room}
                  <div>{row.name}</div>
                </td>
                <td>
                  <PositionMark position={row.position} compact />
                  <div>
                    {row.position} · {row.camera_spectrum}
                    {row.camera_online ? "" : " · offline"}
                  </div>
                  <div className="muted">{row.model_version}</div>
                </td>
                <td>{row.confidence_pct}%</td>
                <td>{row.uncertainty_pct}%</td>
                <td>
                  {row.worst_area || "—"} {row.worst_ratio ?? "—"}
                  <div className={row.worst_ratio !== null && row.worst_ratio >= 0.8 ? "meter hot" : "meter"}>
                    <span style={{ width: `${Math.min((row.worst_ratio || 0) * 100, 100)}%` }} />
                  </div>
                  <div className="muted">
                    steps {row.extra_risk_steps} · ×{row.risk_multiplier} · Braden {row.braden_total}
                  </div>
                </td>
                <td>
                  {row.continence.wet_probability === null ? "—" : row.continence.wet_probability}
                  <div className="muted">threshold {row.continence.threshold ?? "—"}</div>
                  <div className="muted">{row.continence.above_threshold ? "above threshold" : "under threshold"}</div>
                  {row.continence.learning && <div className="muted">learning</div>}
                </td>
                <td>
                  {row.visual_check.would_verify ? "pass" : "fail"}
                  <div className="muted">
                    {row.visual_check.confidence_pct}% confident · {row.visual_check.uncertainty_pct}% uncertain · gate{" "}
                    {row.visual_check.gate_pct}%
                  </div>
                  {row.visual_check.blocked_by.length > 0 && (
                    <div className="muted">{row.visual_check.blocked_by.join(", ")}</div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && board && (
        <pre className="mono">{JSON.stringify(board.residents.find((row) => row.resident_id === open), null, 2)}</pre>
      )}
    </main>
  );
}
