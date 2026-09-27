"use client";

import { useState } from "react";
import { Shell } from "../../components/Shell";
import { useLang, useT } from "../../lib/i18n";

export default function SettingsPage() {
  const t = useT();
  const { lang, setLang } = useLang();
  const [size, setSize] = useState("regular");
  const [speak, setSpeak] = useState(true);
  return (
    <Shell>
      <p className="kicker">{t("nav.settings")}</p>
      <h1>{t("settings.language")}</h1>
      <div className="row" style={{ marginTop: 12 }}>
        {(
          [
            ["en", "English"],
            ["es", "Español"],
            ["tl", "Tagalog"],
          ] as const
        ).map(([code, label]) => (
          <button key={code} className={lang === code ? "choice on" : "choice"} onClick={() => setLang(code)}>
            {label}
          </button>
        ))}
      </div>
      <h2 style={{ marginTop: 22 }}>{t("settings.text")}</h2>
      <div className="row" style={{ marginTop: 12 }}>
        <button
          className="choice"
          onClick={() => {
            setSize("regular");
            document.documentElement.dataset.size = "regular";
            localStorage.setItem("tw_size", "regular");
          }}
        >
          {t("settings.small")}
        </button>
        <button
          className="choice"
          onClick={() => {
            setSize("large");
            document.documentElement.dataset.size = "large";
            localStorage.setItem("tw_size", "large");
          }}
        >
          {t("settings.large")}
        </button>
      </div>
      <p className="muted">{size}</p>
      <h2 style={{ marginTop: 22 }}>{t("settings.readAloud")}</h2>
      <button
        className="choice"
        onClick={() => {
          const next = !speak;
          setSpeak(next);
          localStorage.setItem("tw_speak", next ? "on" : "off");
        }}
      >
        {speak ? "On" : "Off"}
      </button>
    </Shell>
  );
}
