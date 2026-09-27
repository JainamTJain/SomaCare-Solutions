"use client";

import i18n from "i18next";
import { createContext, useContext, useEffect, useState } from "react";
import { initReactI18next, useTranslation } from "react-i18next";
import en from "../locales/en.json";
import es from "../locales/es.json";
import tl from "../locales/tl.json";

const LANGS = ["en", "es", "tl"] as const;
export type Lang = (typeof LANGS)[number];

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      es: { translation: es },
      tl: { translation: tl },
    },
    lng: "en",
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });
}

const LangContext = createContext<{ lang: Lang; setLang: (lang: Lang) => void }>({
  lang: "en",
  setLang: () => undefined,
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    const saved = localStorage.getItem("tw_lang") as Lang | null;
    const size = localStorage.getItem("tw_size") || "regular";
    document.documentElement.dataset.size = size;
    if (saved && LANGS.includes(saved)) {
      setLangState(saved);
      i18n.changeLanguage(saved);
    }
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, []);
  const setLang = (next: Lang) => {
    setLangState(next);
    localStorage.setItem("tw_lang", next);
    i18n.changeLanguage(next);
  };
  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { t } = useTranslation();
  return t;
}

export function speak(text: string, lang: Lang) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  if (localStorage.getItem("tw_speak") === "off") return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = lang === "es" ? "es-MX" : lang === "tl" ? "fil-PH" : "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

export function renderLine(
  t: (key: string, opts?: Record<string, unknown>) => string,
  code: string,
  params: Record<string, string> = {}
) {
  const next: Record<string, string> = { ...params };
  if (next.side) next.side = t(`side.${next.side}`);
  if (next.area) next.area = t(`area.${next.area}`);
  if (next.position) next.position = t(`position.${next.position}`, { defaultValue: next.position });
  if (next.to) next.to = t(`position.${next.to}`, { defaultValue: next.to });
  return t(code, next);
}
