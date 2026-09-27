"use client";

import { useEffect, useState } from "react";
import { Nav } from "../../components/Nav";
import { call, session } from "../../lib/api";

export default function OverridesPage() {
  const [rows, setRows] = useState<{ id: string; reason: string; target_type: string; ts: string }[]>([]);
  const [reason, setReason] = useState("");
  const [target, setTarget] = useState("");
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/nurse/overrides", auth.token).then((body) => setRows(body.overrides));
  }, []);
  return (
    <main>
      <Nav />
      <h1>Overrides</h1>
      <p className="muted">A lower floor than 60 minutes needs your name on it.</p>
      <article className="card">
        <label>
          Target id
          <input value={target} onChange={(event) => setTarget(event.target.value)} />
        </label>
        <label>
          Reason
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
        <button
          onClick={async () => {
            const auth = session();
            await call("/overrides", auth.token, {
              method: "POST",
              body: JSON.stringify({ target_type: "plan", target_id: target, reason }),
            });
            const body = await call("/nurse/overrides", auth.token);
            setRows(body.overrides);
          }}
        >
          Record override
        </button>
      </article>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>
            {row.target_type}: {row.reason}
          </li>
        ))}
      </ul>
    </main>
  );
}
