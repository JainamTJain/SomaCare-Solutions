"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call, session } from "../lib/api";

export function Nav() {
  const [showSetup, setShowSetup] = useState(true);
  useEffect(() => {
    const auth = session();
    if (!auth) return;
    call("/setup/status", auth.token)
      .then((body) => setShowSetup(!body.complete))
      .catch(() => setShowSetup(true));
  }, []);
  return (
    <nav>
      <Link href="/plans">Plans</Link>
      <Link href="/preferences">Preferences</Link>
      <Link href="/residents">History</Link>
      <Link href="/overrides">Overrides</Link>
      <Link href="/consent">Consent</Link>
      {showSetup && <Link href="/setup">Setup</Link>}
    </nav>
  );
}
