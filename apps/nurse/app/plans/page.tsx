"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call, session } from "../../lib/api";

type Plan = {
  id: string;
  resident_name: string;
  version: number;
  lying_limit_min: number;
  sitting_limit_min: number;
  night_lying_limit_min: number | null;
  continence_threshold: number;
  reason: string | null;
  suggestion: { effect?: string; night_movements_per_hour?: number } | null;
};

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [reason, setReason] = useState("Approved after review.");
  const [message, setMessage] = useState("");
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/nurse/plans/pending", auth.token).then((body) => setPlans(body.plans));
  }, []);
  return (
    <main>
      <nav>
        <Link href="/plans">Plans</Link>
        <Link href="/preferences">Preferences</Link>
        <Link href="/residents">History</Link>
        <Link href="/overrides">Overrides</Link>
      </nav>
      <h1>Plans waiting for you</h1>
      <p className="muted">A suggestion can only tighten a limit. You set the number, and you write the reason.</p>
      {plans.length === 0 && <p>Nothing is waiting.</p>}
      <div className="grid">
        {plans.map((plan) => (
          <article key={plan.id} className="card">
            <h2>{plan.resident_name}</h2>
            <p>
              Version {plan.version}. Lying {plan.lying_limit_min} min. Sitting {plan.sitting_limit_min} min.
              Night {plan.night_lying_limit_min ?? "—"}. Change at {plan.continence_threshold}.
            </p>
            {plan.suggestion && (
              <p className="muted">
                Suggestion {plan.suggestion.effect}: night movement {plan.suggestion.night_movements_per_hour} per hour.
              </p>
            )}
            <p>{plan.reason}</p>
            <label>
              Reason
              <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <button
              onClick={async () => {
                const auth = session();
                await call(`/nurse/plans/${plan.id}/approve`, auth.token, {
                  method: "POST",
                  body: JSON.stringify({
                    reason,
                    night_lying_limit_min: plan.night_lying_limit_min,
                  }),
                });
                setMessage(`${plan.resident_name} is approved. The CNA schedule uses it now.`);
                setPlans(plans.filter((row) => row.id !== plan.id));
              }}
            >
              Approve
            </button>
          </article>
        ))}
      </div>
      {message && <p>{message}</p>}
    </main>
  );
}
