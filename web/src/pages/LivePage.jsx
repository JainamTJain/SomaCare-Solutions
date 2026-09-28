import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { createClient } from "@supabase/supabase-js";
import { importPublic, supabaseTransport, Viewer } from "../somacare/broadcast.js";
import StickFigureStage from "../components/StickFigureStage.jsx";
import ReadingPanel from "../components/ReadingPanel.jsx";
import FloorPanel from "../components/FloorPanel.jsx";
import { CareFooter } from "../components/SiteChrome.jsx";

export default function LivePage() {
  const viewerRef = useRef(null);
  const [state, setState] = useState({ snapshot: null, frame: null, live: false, viewers: 0 });
  const [people, setPeople] = useState([]);
  const [error, setError] = useState("");
  const videoId = import.meta.env.VITE_LIVE_VIDEO_ID;

  useEffect(() => {
    const url = import.meta.env.VITE_SUPABASE_URL;
    const anon = import.meta.env.VITE_SUPABASE_ANON_KEY;
    const pub = import.meta.env.VITE_LIVE_PUBLIC_KEY;
    if (!url || !anon || !pub) {
      setError("offline");
      return;
    }
    let viewer;
    let tx;
    let stop = false;
    importPublic(pub).then((key) => {
      if (stop) return;
      const supabase = createClient(url, anon);
      tx = supabaseTransport(supabase, import.meta.env.VITE_LIVE_CHANNEL, "viewer");
      viewer = new Viewer(tx, key);
      viewerRef.current = viewer;
      viewer.onUpdate(setState);
    }).catch(() => setError("offline"));
    let raf = 0;
    const loop = () => {
      if (viewerRef.current) setPeople(viewerRef.current.interpolatedPeople(500));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      stop = true;
      cancelAnimationFrame(raf);
      viewer?.close();
      tx?.close();
    };
  }, []);

  const waiting = !error && !state.snapshot;

  return (
    <div className="experience">
      <div className="page-head">
        <h1 className="page-title">Watch live</h1>
        {state.live && (
          <p className="row"><span className="live-pill">Live</span> {state.viewers} watching</p>
        )}
      </div>
      {error && (
        <p className="banner">The live demo is offline right now. <Link to="/try">Try it live</Link></p>
      )}
      {!error && !state.live && state.snapshot == null && waiting && (
        <p className="waiting"><span className="spinner" /> Waiting for the live feed...</p>
      )}
      {!error && state.snapshot == null && !waiting ? null : null}
      {!error && !state.live && state.snapshot && (
        <p className="banner">The live demo is offline right now. <Link to="/try">Try it on this device</Link></p>
      )}
      <div className="workspace">
        <div className="camera-col">
          <div className={videoId ? "watch-split" : ""}>
            <StickFigureStage people={people} frame={state.frame} showVideo={false} />
            {videoId && (
              <div>
                <iframe
                  title="Staged demo camera"
                  src={`https://www.youtube.com/embed/${videoId}?autoplay=1&mute=1`}
                  allow="autoplay; encrypted-media"
                />
                <p className="caption">Staged demo camera, a few seconds behind. In a real home the video never leaves the room.</p>
              </div>
            )}
          </div>
          <p className="caption">You're watching a real camera as it happens. Only these body points leave the room; the video never does.</p>
          <ReadingPanel frame={state.frame} snapshot={state.snapshot} />
        </div>
        <FloorPanel snapshot={state.snapshot} interactive={false} />
      </div>
      <CareFooter />
    </div>
  );
}
