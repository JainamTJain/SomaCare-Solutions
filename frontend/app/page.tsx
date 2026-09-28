"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useLang, useT } from "../lib/i18n";
import { saveSession } from "../lib/session";

type Person = { id: string; display_name: string; role: string; ui_language: string };

export default function LoginPage() {
  const t = useT();
  const { setLang } = useLang();
  const router = useRouter();
  const [people, setPeople] = useState<Person[]>([]);
  const [picked, setPicked] = useState<Person | null>(null);
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.roster().then((body) => {
      const staff = (body.staff as Person[]).filter((person) =>
        ["cna", "charge_nurse", "engineer", "director"].includes(person.role)
      );
      setPeople(staff);
    });
  }, []);

  async function submit(nextPin: string) {
    if (!picked || nextPin.length < 4) return;
    try {
      const session = await api.login(picked.id, nextPin);
      saveSession(session);
      setLang((session.staff.ui_language || "en") as "en" | "es" | "tl");
      if (session.staff.role === "engineer") router.push("/engineer");
      else if (session.staff.role === "director") router.push("/director");
      else router.push("/crash");
    } catch {
      setError(t("login.bad"));
      setPin("");
    }
  }

  function press(digit: string) {
    if (!picked) return;
    const next = (pin + digit).slice(0, 4);
    setPin(next);
    if (next.length === 4) submit(next);
  }

  return (
    <main className="phone">
      <p className="kicker">{t("login.kicker")}</p>
      <h1>{t("login.title")}</h1>
      <div className="stack" style={{ marginTop: 18 }}>
        {people.map((person) => (
          <button
            key={person.id}
            className="person"
            onClick={() => {
              setPicked(person);
              setPin("");
              setError("");
            }}
          >
            <strong>{person.display_name}</strong>
            <div className="muted">
              {person.role === "cna" || person.role === "charge_nurse"
                ? person.ui_language.toUpperCase()
                : person.role}
            </div>
          </button>
        ))}
      </div>
      <p className="muted" style={{ marginTop: 22 }}>
        <Link href="/simulate">See a fictional night</Link>
      </p>
      {picked && (
        <section className="stack" style={{ marginTop: 18 }}>
          <p className="dots">{pin.replace(/./g, "●") || t("login.pin")}</p>
          {error && <p className="banner">{error}</p>}
          <div className="pad">
            {"123456789".split("").map((digit) => (
              <button key={digit} onClick={() => press(digit)}>
                {digit}
              </button>
            ))}
            <button onClick={() => setPin("")}>C</button>
            <button onClick={() => press("0")}>0</button>
            <button onClick={() => setPin(pin.slice(0, -1))}>⌫</button>
          </div>
        </section>
      )}
    </main>
  );
}
