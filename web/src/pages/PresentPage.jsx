import { useEffect, useRef, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import LiveExperience from "../experience/LiveExperience.jsx";
import { importPrivate, Presenter, supabaseTransport } from "../somacare/broadcast.js";

export default function PresentPage() {
  const presenterRef = useRef(null);
  const txRef = useRef(null);
  const demoHolder = useRef(null);
  const [keyText, setKeyText] = useState("");
  const [error, setError] = useState("");
  const [live, setLive] = useState(false);
  const [viewers, setViewers] = useState(0);

  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex";
    document.head.appendChild(meta);
    return () => {
      meta.remove();
      presenterRef.current?.stop();
      txRef.current?.close();
    };
  }, []);

  async function goLive() {
    setError("");
    const demo = demoHolder.current;
    if (!demo) { setError("The floor is still loading."); return; }
    let priv;
    try { priv = await importPrivate(keyText); }
    catch { setError("That key isn't valid."); return; }
    const url = import.meta.env.VITE_SUPABASE_URL;
    const anon = import.meta.env.VITE_SUPABASE_ANON_KEY;
    if (!url || !anon) { setError("Live broadcast is not configured on this site."); return; }
    const supabase = createClient(url, anon);
    const tx = supabaseTransport(supabase, import.meta.env.VITE_LIVE_CHANNEL, "presenter");
    tx.onViewers(setViewers);
    presenterRef.current = new Presenter(demo, tx, priv, { hz: 2 });
    txRef.current = tx;
    setLive(true);
  }

  function end() {
    presenterRef.current?.stop();
    txRef.current?.close();
    presenterRef.current = null;
    txRef.current = null;
    setLive(false);
  }

  return (
    <>
      <h1 className="page-title">Present</h1>
      <LiveExperience
        presenterRef={presenterRef}
        demoHolder={demoHolder}
        extra={(
          <section className="card golive">
            <h2>Go live</h2>
            {live ? (
              <div className="row">
                <span className="live-pill">Live</span>
                <span>{viewers} watching</span>
                <button type="button" onClick={end}>End broadcast</button>
              </div>
            ) : (
              <div className="stack">
                <label>Paste presenter key
                  <input type="password" value={keyText} autoComplete="off" onChange={(e) => setKeyText(e.target.value)} />
                </label>
                {error && <p className="banner">{error}</p>}
                <button type="button" onClick={goLive}>Go live</button>
              </div>
            )}
            <p className="caption">Viewers see only the stick figure and the floor. Your video never leaves this device.</p>
          </section>
        )}
      />
    </>
  );
}
