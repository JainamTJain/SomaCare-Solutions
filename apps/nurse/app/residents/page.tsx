"use client";

import { useEffect, useState } from "react";
import { Nav } from "../../components/Nav";
import { call, session } from "../../lib/api";

function Picture({ picture }: { picture: Record<string, unknown> }) {
  const risk = picture.risk as { extra_steps?: number; weight?: number; sedating_medication?: boolean; factors?: string[] };
  const meds = picture.medications as { empty?: boolean; rows?: { medication_name: string; is_diuretic: boolean; is_sedating: boolean }[] };
  const braden = picture.braden as { empty?: boolean; rows?: { total?: number }[] };
  const factors = picture.risk_factors as { empty?: boolean; rows?: { factor: string }[] };
  const timeline = picture.timeline as { sources?: Record<string, { empty?: boolean; withheld?: string | null }> };
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <h2>{String(picture.name)}</h2>
      <p>
        Risk steps {risk?.extra_steps}. Weight {risk?.weight}.
        {risk?.sedating_medication ? " A sedating dose is inside the window." : ""}
      </p>
      <p>Diagnoses: {factors?.empty ? "none on file" : (factors?.rows || []).map((row) => row.factor).join(", ")}</p>
      <p>Braden: {braden?.empty ? "none on file" : braden?.rows?.[0]?.total}</p>
      <p>Medications: {meds?.empty ? "none on file" : (meds?.rows || []).map((row) => row.medication_name).join(", ")}</p>
      <p className="muted">
        {timeline?.sources
          ? Object.entries(timeline.sources)
              .map(([name, source]) => `${name}: ${source.withheld ? "withheld" : source.empty ? "empty" : "on file"}`)
              .join(" · ")
          : ""}
      </p>
    </section>
  );
}

export default function ResidentsPage() {
  const [rows, setRows] = useState<{ id: string; preferred_name: string; room: string }[]>([]);
  const [picture, setPicture] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/nurse/residents", auth.token).then((body) => setRows(body.residents));
  }, []);
  return (
    <main>
      <Nav />
      <h1>History</h1>
      <div className="grid">
        {rows.map((row) => (
          <button
            key={row.id}
            className="quiet"
            onClick={async () => {
              const auth = session();
              setPicture(await call(`/residents/${row.id}/full-picture`, auth.token));
            }}
          >
            {row.preferred_name}
            <div className="muted">{row.room}</div>
          </button>
        ))}
      </div>
      {picture && <Picture picture={picture} />}
    </main>
  );
}
