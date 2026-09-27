"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "../../../components/Shell";
import { HowTo, Shift, api } from "../../../lib/api";
import { renderLine, useT } from "../../../lib/i18n";
import { loadSession } from "../../../lib/session";

export default function AlertPage() {
  const t = useT();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [shift, setShift] = useState<Shift | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api.shift(session.token).then(setShift);
  }, []);

  const item = shift?.items.find((row) => row.alert_id === params.id);
  async function act(kind: "accept" | "pass" | "confirm") {
    const session = loadSession();
    if (!session) return;
    const result = await api[kind](session.token, params.id);
    if (kind === "pass") setNote(t("alert.passed", { name: result.display_name }));
    else if (kind === "accept") setNote(t("alert.accepted"));
    else router.push("/shift");
  }

  if (!item) {
    return (
      <Shell>
        <p className="muted">…</p>
      </Shell>
    );
  }
  const lines = item.how_to as HowTo[];
  return (
    <Shell>
      <p className="kicker">{item.resident.room}</p>
      <h1>{item.resident.preferred_name}</h1>
      <div className="chips" style={{ margin: "12px 0" }}>
        {item.tasks.map((task) => (
          <span key={task} className="chip mark">
            {t(`task.${task}`, { defaultValue: task })}
          </span>
        ))}
        {item.two_person && <span className="chip">{t("shift.two")}</span>}
      </div>
      <ul className="how">
        {lines.map((line) => (
          <li key={line.code}>{renderLine(t, line.code, line.params)}</li>
        ))}
      </ul>
      <p className="muted">{t("alert.confirmHint")}</p>
      {note && <p>{note}</p>}
      <div className="stack" style={{ marginTop: 12 }}>
        <button className="big" onClick={() => act("accept")}>
          {t("alert.accept")}
        </button>
        <button className="big quiet" onClick={() => act("confirm")}>
          {t("alert.confirm")}
        </button>
        <button className="big quiet" onClick={() => act("pass")}>
          {t("alert.pass")}
        </button>
        {item.two_person && (
          <Link className="big quiet" href={`/help?resident=${item.resident.id}`} style={{ textAlign: "center" }}>
            {t("help.button")}
          </Link>
        )}
      </div>
    </Shell>
  );
}
