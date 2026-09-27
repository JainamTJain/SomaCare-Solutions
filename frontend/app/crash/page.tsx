"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { FirstRun } from "../../components/FirstRun";
import { Shell } from "../../components/Shell";
import { HowTo, Shift, api } from "../../lib/api";
import { renderLine, speak, useLang, useT } from "../../lib/i18n";
import { loadSession } from "../../lib/session";

export default function CrashPage() {
  const t = useT();
  const { lang } = useLang();
  const router = useRouter();
  const [shift, setShift] = useState<Shift | null>(null);
  const [index, setIndex] = useState(0);
  const [who, setWho] = useState<string | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    setWho(session.staff.id);
    api.shift(session.token).then(setShift);
  }, []);

  const items = shift?.items || [];
  const item = items[index];
  if (!shift) {
    return (
      <Shell>
        {who && <FirstRun role="cna" staffId={who} />}
        <p className="muted">…</p>
      </Shell>
    );
  }
  if (!item) {
    return (
      <Shell>
        {who && <FirstRun role="cna" staffId={who} />}
        <h1>{t("crash.done")}</h1>
        <button className="big" style={{ marginTop: 16 }} onClick={() => router.push("/shift")}>
          {t("crash.back")}
        </button>
      </Shell>
    );
  }
  const lines = (item.how_to || []).slice(0, 6) as HowTo[];
  const spoken = lines.map((line) => renderLine(t, line.code, line.params)).join(". ");
  return (
    <Shell>
      {who && <FirstRun role="cna" staffId={who} />}
      <p className="kicker">{t("crash.progress", { now: index + 1, total: items.length })}</p>
      <h1>{item.resident.preferred_name}</h1>
      <p className="muted">{item.resident.room}</p>
      <ul className="how">
        {lines.map((line) => (
          <li key={line.code + JSON.stringify(line.params)}>{renderLine(t, line.code, line.params)}</li>
        ))}
      </ul>
      <div className="stack" style={{ marginTop: 16 }}>
        <button className="big quiet" onClick={() => speak(`${item.resident.preferred_name}. ${spoken}`, lang)}>
          {t("card.hear")}
        </button>
        <button
          className="big"
          onClick={() => {
            const seen = JSON.parse(localStorage.getItem("tw_seen") || "[]") as string[];
            localStorage.setItem("tw_seen", JSON.stringify([...seen, item.resident.id]));
            setIndex(index + 1);
          }}
        >
          {t("card.gotIt")}
        </button>
      </div>
    </Shell>
  );
}
