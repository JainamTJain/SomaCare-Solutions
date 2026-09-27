"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { call } from "../lib/api";

export default function NurseLogin() {
  const router = useRouter();
  const [people, setPeople] = useState<{ id: string; display_name: string; role: string }[]>([]);
  const [id, setId] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    call("/auth/roster", null).then((body) => {
      setPeople(body.staff.filter((person: { role: string }) => person.role === "nurse" || person.role === "charge_nurse"));
    });
  }, []);
  return (
    <main>
      <p className="muted">Harbor House</p>
      <h1>Approve the plan. The schedule follows.</h1>
      <div className="grid" style={{ marginTop: 16 }}>
        {people.map((person) => (
          <button key={person.id} className="quiet" onClick={() => setId(person.id)}>
            {person.display_name}
            <div className="muted">{person.role}</div>
          </button>
        ))}
      </div>
      <label>
        PIN
        <input value={pin} onChange={(event) => setPin(event.target.value)} inputMode="numeric" />
      </label>
      {error && <p>{error}</p>}
      <button
        onClick={async () => {
          try {
            const body = await call("/auth/login", null, {
              method: "POST",
              body: JSON.stringify({ staff_id: id, pin }),
            });
            sessionStorage.setItem("tw_nurse", JSON.stringify(body));
            router.push("/plans");
          } catch {
            setError("That PIN does not match.");
          }
        }}
      >
        Sign in
      </button>
    </main>
  );
}
