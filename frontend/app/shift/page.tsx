"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { Shift, Visit, api, cacheShift, cachedShift } from "../../lib/api";
import { renderLine, useT } from "../../lib/i18n";
import { loadSession } from "../../lib/session";

function minutesUntil(iso: string) {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60000);
}

export default function ShiftPage() {
  const t = useT();
  const [shift, setShift] = useState<Shift | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api
      .shift(session.token)
      .then(async (body) => {
        setShift(body);
        await cacheShift(body);
      })
      .catch(async () => {
        const saved = await cachedShift();
        if (saved) {
          setShift(saved);
          setOffline(true);
        }
      });
  }, []);

  const due = (shift?.items || []).filter((item) => !item.settled);
  const resting = (shift?.items || []).filter((item) => item.settled);

  return (
    <Shell>
      <p className="kicker">{t("app.name")}</p>
      <div className="spread">
        <h1>{t("nav.shift")}</h1>
        <Link href="/settings" className="muted">
          {t("nav.settings")}
        </Link>
      </div>
      {offline && <p className="banner">{t("shift.offline")}</p>}
      <p className="muted">{t("shift.verified", { count: shift?.verified_checks || 0 })}</p>
      <p className="section-label due">{t("shift.needsYou")}</p>
      <div className="stack">
        {due.length === 0 && <p>{t("shift.empty")}</p>}
        {due.map((item) => (
          <VisitCard key={item.visit_id} item={item} />
        ))}
      </div>
      {resting.length > 0 && (
        <>
          <p className="section-label">{t("shift.resting")}</p>
          <div className="stack">
            {resting.map((item) => (
              <VisitCard key={item.visit_id} item={item} />
            ))}
          </div>
        </>
      )}
    </Shell>
  );
}

function VisitCard({ item }: { item: Visit }) {
  const t = useT();
  const mins = minutesUntil(item.due_at);
  const late = mins < 0;
  const area = String(item.why.worst_area || "");
  const why = area
    ? late
      ? t("why.overdue", { area: t(`area.${area}`) })
      : t("why.turn", { area: t(`area.${area}`), count: Math.max(mins, 0) })
    : "";
  const href = item.alert_id ? `/alerts/${item.alert_id}` : `/residents/${item.resident.id}`;
  return (
    <Link className="visit" href={href}>
      <div className="spread">
        <span className="name">{item.resident.preferred_name}</span>
        <span className={late ? "time late" : "time"}>
          {late ? t("shift.overdue") : t("shift.min", { count: Math.max(mins, 0) })}
        </span>
      </div>
      <div className="muted">{item.resident.room}</div>
      <div className="chips" style={{ marginTop: 8 }}>
        {item.tasks.map((task) => (
          <span key={task} className={item.settled ? "chip ok" : "chip mark"}>
            {t(`task.${task}`, { defaultValue: task })}
          </span>
        ))}
        {item.tasks.length > 1 && <span className="chip">{t("shift.merged")}</span>}
        {item.two_person && <span className="chip">{t("shift.two")}</span>}
      </div>
      {why && <p style={{ marginBottom: 0 }}>{why}</p>}
      {!item.camera_online && <p className="banner">{t("shift.cameraOff")}</p>}
      {item.how_to.length > 0 && (
        <ul className="how">
          {item.how_to.slice(0, 3).map((line) => (
            <li key={line.code + JSON.stringify(line.params)}>{renderLine(t, line.code, line.params)}</li>
          ))}
        </ul>
      )}
    </Link>
  );
}
