"use client";

import { ChartLine } from "../lib/api";
import { renderLine, useT } from "../lib/i18n";
import { PositionMark } from "./PositionMark";

export function ResidentContext({ card }: { card: Record<string, unknown> | null }) {
  const t = useT();
  if (!card) return null;
  const lines = (card.chart_lines as ChartLine[]) || [];
  const monitoring = card.monitoring as { mode?: string; label?: string } | undefined;
  if (monitoring?.mode === "schedule") {
    return <p className="banner">{monitoring.label || t("monitoring.schedule")}</p>;
  }
  return (
    <>
      <p className="live">
        <i />
        <span>
          {card.camera_spectrum === "infrared" ? t("camera.infrared") : t("camera.offline")}
          {" · "}
          {t(`position.${card.position as string}`, { defaultValue: String(card.position) })}
        </span>
      </p>
      <PositionMark position={String(card.position || "unknown")} />
      <p className="muted">{t("camera.rule")}</p>
      <Vitals card={card} />
      <Diet card={card} />
      {lines.length > 0 && (
        <section>
          <p className="section-label">{t("chart.title")}</p>
          <ul className="how">
            {lines.map((line) => (
              <li key={line.ts + line.code}>{renderLine(t, line.code, line.params || {})}</li>
            ))}
          </ul>
        </section>
      )}
    </>
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
  const diet = card.diet as { applies?: boolean; code?: string; turn_blocks?: Record<string, number> } | null;
  if (!diet) return null;
  const turnCount = Object.values(diet.turn_blocks || {}).reduce((sum, value) => sum + value, 0);
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
