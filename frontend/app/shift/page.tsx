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
      <Saved shift={shift} />
      <p className="section-label due">{due[0] ? t("shift.next") : t("shift.needsYou")}</p>
      <div className="stack">
        {due.length === 0 && <p>{t("shift.empty")}</p>}
        {due[0] && <VisitCard item={due[0]} next />}
        {due.length > 1 && <p className="section-label due">{t("shift.needsYou")}</p>}
        {due.slice(1).map((item) => (
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

function Saved({ shift }: { shift: Shift | null }) {
  const t = useT();
  const saved = shift?.time_saved;
  const minutes = saved?.minutes || 0;
  const next = (shift?.items || []).find((item) => !item.settled);
  const label =
    saved && saved.hours > 0
      ? t("shift.savedHours", { hours: saved.hours, minutes: saved.remainder_min })
      : t("shift.saved", { minutes });
  return (
    <section className="saved">
      <strong>{label}</strong>
      <p className="muted" style={{ marginBottom: 0 }}>
        {t("shift.savedHint")} {t("calendar.same")}
      </p>
      <div className="stack" style={{ marginTop: 12 }}>
        {next?.due_at && (
          <a className="big" style={{ textAlign: "center" }} href={googleVisit(next)} target="_blank" rel="noreferrer">
            {t("calendar.add")}
          </a>
        )}
        <button className="big quiet" onClick={() => downloadShift()}>
          {t("calendar.download")}
        </button>
      </div>
    </section>
  );
}

function googleVisit(item: Visit) {
  const start = new Date(item.due_at);
  const end = new Date(start.getTime() + 15 * 60000);
  const stamp = (moment: Date) => moment.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const text = `${item.resident.preferred_name} ${item.resident.room}`;
  const details = item.tasks.join(", ");
  const query = new URLSearchParams({
    action: "TEMPLATE",
    text,
    dates: `${stamp(start)}/${stamp(end)}`,
    details,
  });
  return `https://calendar.google.com/calendar/render?${query.toString()}`;
}

async function downloadShift() {
  const session = loadSession();
  if (!session) return;
  const text = await api.calendar(session.token);
  const blob = new Blob([text], { type: "text/calendar" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "sorety-shift.ics";
  link.click();
  URL.revokeObjectURL(url);
}

function VisitCard({ item, next = false }: { item: Visit; next?: boolean }) {
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
    <Link className={next ? "visit next" : "visit"} href={href}>
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
