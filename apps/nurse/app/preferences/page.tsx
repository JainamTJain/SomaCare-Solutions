"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call, session } from "../../lib/api";

type Pref = {
  id: string;
  resident_name: string;
  code: string;
  params: Record<string, string> | null;
  source_excerpt: string | null;
  source_type: string | null;
};

export default function PreferencesPage() {
  const [rows, setRows] = useState<Pref[]>([]);
  const [text, setText] = useState("Resident prefers to be positioned on her right side. Say her name before touching her.");
  const [residentId, setResidentId] = useState("");
  const [residents, setResidents] = useState<{ id: string; preferred_name: string }[]>([]);
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/nurse/preferences/pending", auth.token).then((body) => setRows(body.preferences));
    call("/nurse/residents", auth.token).then((body) => setResidents(body.residents));
  }, []);
  return (
    <main>
      <nav>
        <Link href="/plans">Plans</Link>
        <Link href="/preferences">Preferences</Link>
        <Link href="/residents">History</Link>
        <Link href="/overrides">Overrides</Link>
      </nav>
      <h1>Preference cards</h1>
      <p className="muted">
        Drafts come from keyword rules. Nothing here reaches a CNA until you approve it. Machine translation stays off.
      </p>
      <article className="card">
        <label>
          Resident
          <select value={residentId} onChange={(event) => setResidentId(event.target.value)}>
            <option value="">Choose</option>
            {residents.map((resident) => (
              <option key={resident.id} value={resident.id}>
                {resident.preferred_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Note
          <textarea value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <button
          onClick={async () => {
            const auth = session();
            await call("/nurse/preferences/extract", auth.token, {
              method: "POST",
              body: JSON.stringify({ resident_id: residentId, text }),
            });
            const body = await call("/nurse/preferences/pending", auth.token);
            setRows(body.preferences);
          }}
        >
          Extract drafts
        </button>
      </article>
      <div className="grid" style={{ marginTop: 14 }}>
        {rows.map((row) => (
          <article key={row.id} className="card">
            <h2>{row.resident_name}</h2>
            <p>{row.code}</p>
            <p className="muted">“{row.source_excerpt}”</p>
            <p className="muted">{row.source_type}</p>
            <button
              onClick={async () => {
                const auth = session();
                await call(`/nurse/preferences/${row.id}/approve`, auth.token, { method: "POST" });
                setRows(rows.filter((item) => item.id !== row.id));
              }}
            >
              Approve
            </button>
          </article>
        ))}
      </div>
    </main>
  );
}
