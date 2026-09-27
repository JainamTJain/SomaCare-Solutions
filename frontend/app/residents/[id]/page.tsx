"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ResidentContext } from "../../../components/ResidentContext";
import { Shell } from "../../../components/Shell";
import { HowTo, api } from "../../../lib/api";
import { renderLine, speak, useLang, useT } from "../../../lib/i18n";
import { loadSession } from "../../../lib/session";

export default function ResidentPage() {
  const t = useT();
  const { lang } = useLang();
  const params = useParams<{ id: string }>();
  const [card, setCard] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    const pull = () => api.card(session.token, params.id).then(setCard);
    pull();
    const timer = window.setInterval(pull, 2000);
    return () => window.clearInterval(timer);
  }, [params.id]);

  if (!card) {
    return (
      <Shell>
        <p className="muted">…</p>
      </Shell>
    );
  }
  const resident = card.resident as { preferred_name: string; room: string };
  const lines = (card.how_to as HowTo[]) || [];
  const text = lines.map((line) => renderLine(t, line.code, line.params)).join(". ");

  return (
    <Shell>
      <p className="kicker">{resident.room}</p>
      <h1>{resident.preferred_name}</h1>
      {(card.monitoring as { mode?: string } | undefined)?.mode !== "schedule" && (
        <p className="muted">{t("card.inPosition", { count: card.minutes_in_position as number })}</p>
      )}
      {card.camera_online === false && <p className="banner">{t("shift.cameraOff")}</p>}
      <ResidentContext card={card} />
      <ul className="how">
        {lines.map((line) => (
          <li key={line.code + JSON.stringify(line.params)}>{renderLine(t, line.code, line.params)}</li>
        ))}
      </ul>
      <div className="stack" style={{ marginTop: 16 }}>
        <button className="big quiet" onClick={() => speak(`${resident.preferred_name}. ${text}`, lang)}>
          {t("card.hear")}
        </button>
        <Link className="big" href="/shift" style={{ textAlign: "center" }}>
          {t("card.next")}
        </Link>
      </div>
    </Shell>
  );
}
