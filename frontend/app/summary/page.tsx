"use client";

import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { ChartLine, Shift, api } from "../../lib/api";
import { renderLine, useT } from "../../lib/i18n";
import { clearSession, loadSession } from "../../lib/session";
import { useRouter } from "next/navigation";

export default function SummaryPage() {
  const t = useT();
  const router = useRouter();
  const [shift, setShift] = useState<Shift | null>(null);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api.shift(session.token).then(setShift);
  }, []);
  const open = (shift?.items || []).filter((item) => !item.settled).length;
  return (
    <Shell>
      <p className="kicker">{t("nav.summary")}</p>
      <h1>{t("summary.thanks")}</h1>
      <p>{t("summary.savedTime", { minutes: shift?.time_saved?.minutes || 0 })}</p>
      <p>{t("summary.open", { count: open })}</p>
      <p>{t("summary.verified", { count: shift?.verified_checks || 0 })}</p>
      {(shift?.chart_lines || []).length > 0 && (
        <>
          <p className="section-label">{t("chart.title")}</p>
          <ul className="how">
            {(shift?.chart_lines as ChartLine[]).map((line) => (
              <li key={line.ts + line.code}>{renderLine(t, line.code, line.params || {})}</li>
            ))}
          </ul>
        </>
      )}
      <label className="stack" style={{ marginTop: 12 }}>
        <span>{t("summary.note")}</span>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={t("summary.placeholder")} />
      </label>
      <button
        className="big"
        style={{ marginTop: 12 }}
        onClick={async () => {
          const session = loadSession();
          if (!session) return;
          await api.note(session.token, note);
          setSaved(true);
        }}
      >
        {t("summary.save")}
      </button>
      {saved && <p>{t("summary.saved")}</p>}
      <button
        className="big quiet"
        style={{ marginTop: 12 }}
        onClick={() => {
          clearSession();
          router.push("/");
        }}
      >
        {t("login.title")}
      </button>
    </Shell>
  );
}
