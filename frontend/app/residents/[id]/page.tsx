"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PositionMark } from "../../../components/PositionMark";
import { Shell } from "../../../components/Shell";
import { ChartLine, HowTo, api } from "../../../lib/api";
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
      <p className="live">
        <i />
        <span>
          {card.camera_spectrum === "infrared" ? t("camera.infrared") : t("camera.offline")}
          {" · "}
          {t(`position.${card.position as string}`, { defaultValue: String(card.position) })}
        </span>
      </p>
      <PositionMark position={String(card.position)} />
      <p className="muted">
        {t("card.inPosition", { count: card.minutes_in_position as number })}
        {" · "}
        {t("camera.rule")}
      </p>
      {!card.camera_online && <p className="banner">{t("shift.cameraOff")}</p>}
      <Vitals card={card} />
      <Diet card={card} />
      <Chart lines={(card.chart_lines as ChartLine[]) || []} />
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

function Vitals({ card }: { card: Record<string, unknown> }) {
  const t = useT();
  const vitals = card.vitals as {
    systolic?: number;
    diastolic?: number;
    pulse?: number;
    temp_c?: number;
    spo2?: number;
    weight_kg?: number;
  } | null;
  if (!vitals) return null;
  return (
    <section className="saved">
      <p className="kicker">{t("vitals.title")}</p>
      <p>{t("vitals.bp", { sys: vitals.systolic, dia: vitals.diastolic })}</p>
      <p className="muted">
        {t("vitals.pulse", { count: vitals.pulse })}
        {" · "}
        {t("vitals.temp", { count: vitals.temp_c })}
        {" · "}
        {t("vitals.spo2", { count: vitals.spo2 })}
        {" · "}
        {t("vitals.weight", { count: vitals.weight_kg })}
      </p>
      <p className="muted" style={{ marginBottom: 0 }}>
        {t("vitals.fromChart")}
      </p>
    </section>
  );
}

function Diet({ card }: { card: Record<string, unknown> }) {
  const t = useT();
  const diet = card.diet as { applies?: boolean; code?: string; is_order?: boolean; turn_blocks?: Record<string, number> } | null;
  if (!diet) return null;
  const turns = diet.turn_blocks || {};
  const turnCount = Object.values(turns).reduce((sum, value) => sum + value, 0);
  return (
    <section className="saved">
      <p className="kicker">{t("diet.title")}</p>
      <p>{t(diet.code || "diet.quiet")}</p>
      {diet.applies && (
        <p className="muted">
          {t("diet.turns")} · {turnCount}
        </p>
      )}
      <p className="muted" style={{ marginBottom: 0 }}>
        {t("diet.notOrder")}
      </p>
    </section>
  );
}

function Chart({ lines }: { lines: ChartLine[] }) {
  const t = useT();
  if (!lines.length) return null;
  return (
    <section>
      <p className="section-label">{t("chart.title")}</p>
      <ul className="how">
        {lines.map((line) => (
          <li key={line.ts + line.code}>{renderLine(t, line.code, line.params || {})}</li>
        ))}
      </ul>
    </section>
  );
}
