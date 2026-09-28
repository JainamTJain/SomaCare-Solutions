"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { FirstRun } from "../../components/FirstRun";
import { api } from "../../lib/api";
import { clearSession, loadSession } from "../../lib/session";

type Saved = { minutes: number; verified_checks: number; merged_visits: number };
type Board = {
  generated_at: string;
  facility: string;
  unit: string;
  residents: number;
  time_saved: {
    total_minutes: number;
    total_hours: number;
    turning: Saved;
    incontinence: Saved;
    visual_checks: Saved;
    per_verified_check_min: number;
    per_merged_visit_min: number;
  };
  pressure_injury: {
    ulcers_prevented: null;
    ulcers_prevented_note: string;
    new_injuries_recorded_this_shift: number;
    residents_inside_nurse_limit: number;
    residents_at_or_over_limit: number;
  };
  cameras: {
    hardware?: string;
    infrared_online: number;
    residents: number;
    mean_uncertainty_pct: number | null;
  };
  position_claim?: { under_blanket: string; gate1: string; note: string };
  incontinence: { above_nurse_threshold: number; names: string[] };
  visual_checks_passing: number;
  closest_to_limit: { name: string; room: string; worst_area: string | null; worst_ratio: number | null }[];
};

function clock(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return `${hours} h ${rest} min`;
}

export default function DirectorPage() {
  const router = useRouter();
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState("");
  const [who, setWho] = useState<string | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      router.replace("/");
      return;
    }
    setWho(session.staff.id);
    if (session.staff.role !== "director" && session.staff.role !== "admin") {
      setError("This view is for the director login.");
      return;
    }
    let stop = false;
    const pull = () =>
      api
        .director(session.token)
        .then((body) => {
          if (!stop) setBoard(body as Board);
        })
        .catch((err: Error) => {
          if (!stop) setError(err.message);
        });
    pull();
    const timer = window.setInterval(pull, 5000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [router]);

  const saved = board?.time_saved;
  return (
    <main className="desk">
      {who && <FirstRun role="director" staffId={who} />}
      <p className="kicker">SomaCare</p>
      <div className="spread">
        <h1>Director</h1>
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
      <p className="muted">
        {board ? `${board.facility} · ${board.unit} · ${board.residents} residents` : "Harbor House"}
      </p>
      {error && <p className="banner">{error}</p>}
      <div className="metrics">
        <article className="metric">
          <span className="muted">Caregiver time saved today</span>
          <b>{saved ? clock(saved.total_minutes) : "—"}</b>
          <p className="muted">Turning, incontinence, and checks the camera closed. One number, already on the CNA shift.</p>
        </article>
        <article className="metric">
          <span className="muted">Saved on turning</span>
          <b>{saved ? clock(saved.turning.minutes) : "—"}</b>
          <p className="muted">
            {saved?.turning.verified_checks ?? 0} verified turns · {saved?.turning.merged_visits ?? 0} turns folded into another visit
          </p>
        </article>
        <article className="metric">
          <span className="muted">Saved on incontinence</span>
          <b>{saved ? clock(saved.incontinence.minutes) : "—"}</b>
          <p className="muted">
            {saved?.incontinence.verified_checks ?? 0} verified changes · {saved?.incontinence.merged_visits ?? 0} changes folded into another visit
          </p>
        </article>
        <article className="metric">
          <span className="muted">Saved on visual checks</span>
          <b>{saved ? clock(saved.visual_checks.minutes) : "—"}</b>
          <p className="muted">
            {saved?.visual_checks.verified_checks ?? 0} checks confirmed without a walk · {board?.visual_checks_passing ?? 0} cameras that would pass one now
          </p>
        </article>
        <article className="metric">
          <span className="muted">Pressure ulcers prevented</span>
          <b>Not estimated</b>
          <p>{board?.pressure_injury.ulcers_prevented_note}</p>
          <p className="muted">
            New injuries recorded this shift: {board?.pressure_injury.new_injuries_recorded_this_shift ?? "—"}. Inside the nurse&apos;s limit:{" "}
            {board?.pressure_injury.residents_inside_nurse_limit ?? "—"} of {board?.residents ?? "—"}. At or over the limit:{" "}
            {board?.pressure_injury.residents_at_or_over_limit ?? "—"}.
          </p>
        </article>
        <article className="metric">
          <span className="muted">Incontinence above the nurse line</span>
          <b>{board?.incontinence.above_nurse_threshold ?? "—"}</b>
          <p className="muted">{(board?.incontinence.names || []).join(", ") || "No one is over the nurse’s threshold right now."}</p>
        </article>
        <article className="metric">
          <span className="muted">Infrared baby monitors online</span>
          <b>
            {board?.cameras.infrared_online ?? "—"}/{board?.cameras.residents ?? "—"}
          </b>
          <p className="muted">Mean position uncertainty {board?.cameras.mean_uncertainty_pct ?? "—"}%.</p>
          <p className="muted">{board?.position_claim?.note}</p>
        </article>
      </div>
      <p className="section-label">Closest to the nurse&apos;s limit</p>
      <ul className="how">
        {(board?.closest_to_limit || []).map((row) => (
          <li key={row.name}>
            {row.name}, room {row.room}: {row.worst_area} at {row.worst_ratio}
          </li>
        ))}
      </ul>
      {saved && (
        <p className="muted">
          Each camera-verified check is {saved.per_verified_check_min} minutes not walked. Each task merged into a visit already on the
          round is {saved.per_merged_visit_min} minutes.
        </p>
      )}
    </main>
  );
}
