"use client";

import { useEffect, useState } from "react";
import { Nav } from "../../components/Nav";
import { call, session } from "../../lib/api";

type Step = { id: string; done: boolean; have?: number; cameras_online?: number; signed?: number; needed?: number; label?: string };

export default function SetupPage() {
  const [steps, setSteps] = useState<Step[]>([]);
  const [complete, setComplete] = useState(false);
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/setup/status", auth.token).then((body) => {
      setSteps(body.steps);
      setComplete(body.complete);
    });
  }, []);
  return (
    <main>
      <Nav />
      <h1>Setup</h1>
      <p className="muted">
        Counts come from the hall, not a script. Consent stays open until every resident has signed every scope. Skin
        is still unsigned in the demo.
      </p>
      <ul>
        {steps.map((step) => (
          <li key={step.id}>
            {step.done ? "Done" : "Open"} — {step.id}
            {step.have != null ? ` (${step.have})` : ""}
            {step.cameras_online != null ? `, cameras online ${step.cameras_online}` : ""}
            {step.signed != null ? `, consent ${step.signed} of ${step.needed}` : ""}
            {step.label ? ` ${step.label}` : ""}
          </li>
        ))}
      </ul>
      {complete ? <p>Setup is complete.</p> : <p>Setup stays in the nav until every step is done.</p>}
    </main>
  );
}
