"use client";

export type Session = {
  token: string;
  staff: { id: string; display_name: string; role: string; ui_language: string };
};

export function saveSession(session: Session) {
  sessionStorage.setItem("tw_session", JSON.stringify(session));
  if (!localStorage.getItem("tw_lang")) {
    localStorage.setItem("tw_lang", session.staff.ui_language || "en");
  }
}

export function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("tw_session");
  return raw ? (JSON.parse(raw) as Session) : null;
}

export function clearSession() {
  sessionStorage.removeItem("tw_session");
}
