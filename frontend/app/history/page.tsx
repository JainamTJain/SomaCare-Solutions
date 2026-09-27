"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { Shift, api } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { loadSession } from "../../lib/session";

export default function HistoryIndex() {
  const t = useT();
  const [shift, setShift] = useState<Shift | null>(null);
  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api.shift(session.token).then(setShift);
  }, []);
  return (
    <Shell>
      <p className="kicker">{t("history.title")}</p>
      <h1>{t("nav.history")}</h1>
      <div className="stack" style={{ marginTop: 16 }}>
        {(shift?.items || []).map((item) => (
          <Link key={item.resident.id} className="person" href={`/history/${item.resident.id}`}>
            <strong>{item.resident.preferred_name}</strong>
            <div className="muted">{item.resident.room}</div>
          </Link>
        ))}
      </div>
    </Shell>
  );
}
