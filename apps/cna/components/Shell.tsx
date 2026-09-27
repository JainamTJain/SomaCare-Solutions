"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useT } from "../lib/i18n";
import { loadSession } from "../lib/session";

const LINKS = [
  ["/shift", "nav.shift"],
  ["/crash", "nav.crash"],
  ["/continence", "nav.continence"],
  ["/help", "nav.help"],
  ["/summary", "nav.summary"],
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const t = useT();
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!loadSession()) router.replace("/");
    else setReady(true);
  }, [router]);
  if (!ready) return <main className="phone" />;
  return (
    <>
      <main className="phone">{children}</main>
      <nav className="nav">
        {LINKS.map(([href, key]) => (
          <Link key={href} href={href} className={path.startsWith(href) ? "on" : ""}>
            {t(key)}
          </Link>
        ))}
      </nav>
    </>
  );
}
