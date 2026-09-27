"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { Shift, api } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { loadSession } from "../../lib/session";

function HelpInner() {
  const t = useT();
  const params = useSearchParams();
  const preset = params.get("resident");
  const [shift, setShift] = useState<Shift | null>(null);
  const [result, setResult] = useState<{ teammate: string; eta_min: number; resident: string } | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    api.shift(session.token).then(setShift);
  }, []);

  async function ask(residentId: string) {
    const session = loadSession();
    if (!session) return;
    const body = await api.help(session.token, residentId);
    setResult(body);
  }

  const people = (shift?.items || []).filter((item) => !preset || item.resident.id === preset);
  return (
    <Shell>
      <p className="kicker">{t("nav.help")}</p>
      <h1>{t("help.title")}</h1>
      {result ? (
        <article className="card" style={{ marginTop: 16 }}>
          <h2>{t("help.coming", { name: result.teammate })}</h2>
          <p>{t("help.eta", { count: result.eta_min })}</p>
          <p className="muted">{result.resident}</p>
        </article>
      ) : (
        <div className="stack" style={{ marginTop: 16 }}>
          <p className="muted">{t("help.pick")}</p>
          {people.map((item) => (
            <button key={item.resident.id} className="big" onClick={() => ask(item.resident.id)}>
              {item.resident.preferred_name}
            </button>
          ))}
        </div>
      )}
    </Shell>
  );
}

export default function HelpPage() {
  return (
    <Suspense>
      <HelpInner />
    </Suspense>
  );
}
