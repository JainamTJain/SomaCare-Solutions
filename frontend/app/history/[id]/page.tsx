"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "../../../components/Shell";
import { api } from "../../../lib/api";
import { useT } from "../../../lib/i18n";
import { loadSession } from "../../../lib/session";

type History = {
  events: { id: number; ts: string; kind: string; value: Record<string, unknown> | null; model_version: string | null }[];
  alerts: { id: string; created_at: string; rule: string; status: string; inputs: Record<string, unknown> | null }[];
};

export default function HistoryDetail() {
  const t = useT();
  const params = useParams<{ id: string }>();
  const [body, setBody] = useState<History | null>(null);
  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api.history(session.token, params.id).then(setBody);
  }, [params.id]);
  return (
    <Shell>
      <p className="kicker">{t("history.title")}</p>
      <h1>{t("nav.history")}</h1>
      {!body || (body.events.length === 0 && body.alerts.length === 0) ? (
        <p className="muted">{t("history.empty")}</p>
      ) : (
        <div className="timeline" style={{ marginTop: 16 }}>
          {body.alerts.map((alert) => (
            <article key={alert.id}>
              <strong>{alert.status}</strong>
              <div className="muted">{new Date(alert.created_at).toLocaleString()}</div>
              <div>
                {t("history.alertRule")}: {alert.rule}
              </div>
            </article>
          ))}
          {body.events.map((event) => (
            <article key={event.id}>
              <strong>{event.kind}</strong>
              <div className="muted">{new Date(event.ts).toLocaleString()}</div>
              <div>{event.value ? JSON.stringify(event.value) : ""}</div>
            </article>
          ))}
        </div>
      )}
    </Shell>
  );
}
