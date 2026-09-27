"use client";

import { useEffect, useState } from "react";
import { useT } from "../lib/i18n";

export function FirstRun({ role, staffId }: { role: string; staffId: string }) {
  const t = useT();
  const storageKey = `sorety-tutorial-${staffId}`;
  const [step, setStep] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!window.localStorage.getItem(storageKey)) setOpen(true);
  }, [storageKey]);

  if (!open) return null;
  const index = ["one", "two", "three"][step];

  function finish() {
    window.localStorage.setItem(storageKey, "1");
    setOpen(false);
  }

  return (
    <section className="banner">
      <p className="kicker">{t("tutorial.kicker")}</p>
      <h2>{t(`tutorial.${role}.${index}.title`)}</h2>
      <p>{t(`tutorial.${role}.${index}.body`)}</p>
      {step < 2 ? (
        <button onClick={() => setStep(step + 1)}>{t("tutorial.next")}</button>
      ) : (
        <button onClick={finish}>{t("tutorial.done")}</button>
      )}
      <button onClick={finish}>{t("tutorial.skip")}</button>
    </section>
  );
}
