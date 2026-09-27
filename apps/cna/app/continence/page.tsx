"use client";

import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { Shift, api } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { loadSession } from "../../lib/session";

type Window = { due_at: string; source: string; detail: Record<string, unknown> | null };
type View = { windows: Window[]; learning: boolean; last_change_at: string | null; threshold: number };

export default function ContinencePage() {
  const t = useT();
  const [rows, setRows] = useState<{ name: string; room: string; view: View }[]>([]);
  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api.shift(session.token).then(async (shift: Shift) => {
      const next = [];
      for (const item of shift.items) {
        const view = (await api.continence(session.token, item.resident.id)) as View;
        next.push({ name: item.resident.preferred_name, room: item.resident.room, view });
      }
      setRows(next);
    });
  }, []);
  return (
    <Shell>
      <p className="kicker">{t("continence.title")}</p>
      <h1>{t("nav.continence")}</h1>
      <div className="stack" style={{ marginTop: 16 }}>
        {rows.map((row) => (
          <article key={row.name} className="card">
            <div className="spread">
              <span className="name">{row.name}</span>
              {row.view.learning && <span className="chip">{t("continence.learning")}</span>}
            </div>
            <div className="muted">{row.room}</div>
            {row.view.last_change_at && (
              <p>{t("continence.last", { time: new Date(row.view.last_change_at).toLocaleTimeString() })}</p>
            )}
            {row.view.windows.length === 0 && <p>{t("continence.none")}</p>}
            {row.view.windows.map((window) => {
              const detail = window.detail || {};
              const code = String(detail.reason_code || "continence.reason.nurse_check");
              const params = (detail.reason_params as Record<string, string>) || {};
              return (
                <p key={window.due_at}>
                  {new Date(window.due_at).toLocaleTimeString()} · {t(code, params)}
                </p>
              );
            })}
          </article>
        ))}
      </div>
    </Shell>
  );
}
