"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call, session } from "../../lib/api";

export default function ResidentsPage() {
  const [rows, setRows] = useState<{ id: string; preferred_name: string; room: string }[]>([]);
  const [history, setHistory] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/nurse/residents", auth.token).then((body) => setRows(body.residents));
  }, []);
  return (
    <main>
      <nav>
        <Link href="/plans">Plans</Link>
        <Link href="/preferences">Preferences</Link>
        <Link href="/residents">History</Link>
        <Link href="/overrides">Overrides</Link>
      </nav>
      <h1>History</h1>
      <div className="grid">
        {rows.map((row) => (
          <button
            key={row.id}
            className="quiet"
            onClick={async () => {
              const auth = session();
              setHistory(await call(`/residents/${row.id}/history?days=7`, auth.token));
            }}
          >
            {row.preferred_name}
            <div className="muted">{row.room}</div>
          </button>
        ))}
      </div>
      {history && (
        <pre className="card" style={{ marginTop: 16, whiteSpace: "pre-wrap" }}>
          {JSON.stringify(history, null, 2)}
        </pre>
      )}
    </main>
  );
}
