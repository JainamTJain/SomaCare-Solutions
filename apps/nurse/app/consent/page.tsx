"use client";

import { useEffect, useState } from "react";
import { Nav } from "../../components/Nav";
import { API_BASE_URL } from "../../config";
import { call, session } from "../../lib/api";

type Scope = { id: string | null; scope: string; status: string; explanation_shown?: string };
type Row = { resident_id: string; name: string; scopes: Record<string, Scope> };

const ORDER = ["position_monitoring", "skin_capture", "continence_tracking"];

export default function ConsentPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [signer, setSigner] = useState("Family member");
  const [message, setMessage] = useState("");
  const auth = session();

  function load() {
    if (!auth) return;
    call("/consent", auth.token).then((body) => setRows(body.residents));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function start(residentId: string, scope: string) {
    if (!auth) return;
    const created = await call("/consent/request", auth.token, {
      method: "POST",
      body: JSON.stringify({ resident_id: residentId, scope }),
    });
    await call(`/consent/${created.id}/send`, auth.token, { method: "POST" });
    setMessage("Form is ready to print. Outbound email is off.");
    load();
  }

  async function printForm(recordId: string) {
    if (!auth) return;
    const response = await fetch(`${API_BASE_URL}/consent/${recordId}/form`, {
      headers: { Authorization: `Bearer ${auth.token}` },
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  }

  async function sign(recordId: string) {
    if (!auth) return;
    await call(`/consent/${recordId}/sign`, auth.token, {
      method: "POST",
      body: JSON.stringify({ signer_name: signer, relationship: "power of attorney" }),
    });
    setMessage("Signed in person. This is not an e-sign vendor.");
    load();
  }

  return (
    <main>
      <Nav />
      <h1>Consent</h1>
      <p className="muted">
        Each scope has its own form. The words are fixed. Email and text are off, so the form is printed and signed in
        person. Demo rows marked demo-seed are not a real power of attorney. Skin capture stays off until someone signs
        that scope, and a skin finding is still not shown to staff.
      </p>
      <label>
        Signer name
        <input value={signer} onChange={(event) => setSigner(event.target.value)} />
      </label>
      {message && <p>{message}</p>}
      {rows.map((row) => (
        <section key={row.resident_id}>
          <h2>{row.name}</h2>
          {ORDER.map((scope) => {
            const item = row.scopes[scope];
            return (
              <p key={scope}>
                {scope}: {item?.status || "none"}{" "}
                {item?.status === "none" && (
                  <button onClick={() => start(row.resident_id, scope)}>Start request</button>
                )}
                {item?.id && item.status !== "none" && item.status !== "signed" && (
                  <>
                    <button onClick={() => printForm(item.id as string)}>Print</button>
                    <button onClick={() => sign(item.id as string)}>Sign in person</button>
                  </>
                )}
              </p>
            );
          })}
        </section>
      ))}
    </main>
  );
}
