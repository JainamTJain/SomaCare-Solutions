"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  EXPERIMENT_PRESETS,
  LEAD_MIN,
  NIGHT_MIN,
  Night,
  SELF_PER_HOUR,
  FALSE_PER_HOUR,
  TOLERANCE_MIN,
  clockLabel,
  experiments,
  makeScenario,
  type ExperimentRow,
  type Snap,
} from "../../lib/nightSim";

const SPEEDS = { Slow: 420, Normal: 120, Fast: 32 } as const;

type Flags = { camera: boolean; trust: boolean; mistakes: boolean; stretched: boolean; truth: boolean };

const START: Flags = { camera: true, trust: false, mistakes: false, stretched: false, truth: false };

function scenarioName(flags: Flags): string {
  if (!flags.camera) return "Paper";
  if (flags.trust && flags.mistakes) return "Trusted, and sometimes wrong";
  if (flags.trust) return "SomaCare, trust the camera";
  if (flags.mistakes) return "Human checks stay, camera sometimes wrong";
  return "SomaCare, human checks stay";
}

function build(nightNo: number, flags: Flags): Night {
  return new Night(
    makeScenario({ ...flags, name: scenarioName(flags) }),
    nightNo,
    nightNo === 1
  );
}

type OwnRun = {
  night: number;
  settings: string;
  visits: number;
  safety: number;
  past: number;
  longest: number;
  records: number;
};

export default function SimulatePage() {
  const [flags, setFlags] = useState<Flags>(START);
  const [nightNo, setNightNo] = useState(1);
  const [speed, setSpeed] = useState<keyof typeof SPEEDS>("Normal");
  const [playing, setPlaying] = useState(false);
  const [snap, setSnap] = useState<Snap>(() => build(1, START).snapshot());
  const [table, setTable] = useState<ExperimentRow[] | null>(null);
  const [running, setRunning] = useState(false);
  const [recordFor, setRecordFor] = useState<string | null>(null);
  const [own, setOwn] = useState<OwnRun[]>([]);
  const nightRef = useRef<Night>(build(1, START));
  const logged = useRef(false);

  function adopt(next: Night) {
    nightRef.current = next;
    logged.current = false;
    setSnap(next.snapshot());
    setPlaying(false);
  }

  function restart(nextFlags = flags, nextNight = nightNo) {
    adopt(build(nextNight, nextFlags));
  }

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const night = nightRef.current;
      const frame = night.step();
      setSnap(frame);
      if (night.done) {
        setPlaying(false);
        if (!logged.current) {
          logged.current = true;
          const summary = night.snapshot();
          setOwn((rows) => [
            {
              night: nightNo,
              settings: scenarioName(flags) + (flags.stretched ? ", stretched" : ""),
              visits: summary.visits,
              safety: summary.safety_net,
              past: summary.past_episodes,
              longest: summary.longest_past,
              records: summary.records,
            },
            ...rows,
          ].slice(0, 8));
        }
      }
    }, SPEEDS[speed]);
    return () => window.clearInterval(id);
  }, [playing, speed, flags, nightNo]);

  function patch(partial: Partial<Flags>) {
    const next = { ...flags, ...partial };
    setFlags(next);
    nightRef.current.scn = makeScenario({ ...next, name: scenarioName(next) });
    setSnap(nightRef.current.snapshot());
  }

  function watchPreset(preset: (typeof EXPERIMENT_PRESETS)[number]) {
    const next = { ...flags, camera: preset.camera, trust: preset.trust, mistakes: preset.mistakes };
    setFlags(next);
    setNightNo(1);
    adopt(build(1, next));
  }

  function runAll() {
    setRunning(true);
    window.setTimeout(() => {
      setTable(experiments(40, 1));
      setRunning(false);
    }, 30);
  }

  const frame = snap;
  const scalePad = 45;

  return (
    <main className="desk">
      <p className="kicker">Simulation. Fictional residents, no real data</p>
      <p className="muted"><Link href="/">Back to sign in</Link></p>
      <h1>See it before you believe it</h1>
      <p>
        One night in a six-bed home. You decide what to switch on. Six residents, one caregiver, eight hours.
        Each resident has a turning limit set in their care plan. Watch who gets seen first, watch the record
        write itself, then break things on purpose: make the camera wrong, take a resident&apos;s consent away,
        cover someone with a blanket.
      </p>
      <p className="banner">
        This is a simulation with assumptions you can read at the bottom. It shows how SomaCare behaves.
        It is not evidence of how it performs in a real home, and the pilot exists to measure that.
      </p>

      <div className="spread" style={{ marginTop: 18 }}>
        <div>
          <h2 style={{ margin: 0 }}>{clockLabel(frame.minute)}</h2>
          <p className="muted">Night {nightNo}, minute {frame.minute} of {NIGHT_MIN}</p>
        </div>
        <div className="row">
          <button className="choice" onClick={() => setPlaying((on) => !on)}>{playing ? "Pause" : "Play"}</button>
          <button className="choice" onClick={() => restart()}>Restart night</button>
        </div>
      </div>
      <div className="row" style={{ margin: "8px 0 18px" }}>
        <label className="muted">Night{" "}
          <input
            type="number"
            min={1}
            max={40}
            value={nightNo}
            onChange={(event) => {
              const next = Math.max(1, Math.min(40, Number(event.target.value) || 1));
              setNightNo(next);
              adopt(build(next, flags));
            }}
            style={{ width: 64, background: "var(--bg-raise)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 8px" }}
          />
        </label>
        <span className="muted">Speed</span>
        {(Object.keys(SPEEDS) as Array<keyof typeof SPEEDS>).map((name) => (
          <button key={name} className={speed === name ? "choice on" : "choice"} onClick={() => setSpeed(name)}>{name}</button>
        ))}
      </div>

      <div className="stack">
        <Toggle on={flags.camera} title="Camera on" body="Off is the paper schedule. On, the camera can reorder visits and write the record." onClick={() => patch(flags.camera ? { camera: false, trust: false, mistakes: false } : { camera: true })} />
        <Toggle on={flags.trust} disabled={!flags.camera} title="Trust camera confirmations" body="A clinician allows a confirmed turn to count as a check. Needs measured evidence first." onClick={() => patch({ trust: !flags.trust })} />
        <Toggle on={flags.mistakes} disabled={!flags.camera} title="Camera makes mistakes" body="Now and then it reports a turn that never happened." onClick={() => patch({ mistakes: !flags.mistakes })} />
        <Toggle on={flags.stretched} title="Caregiver is stretched" body="Slower to arrive after an alert." onClick={() => patch({ stretched: !flags.stretched })} />
        <Toggle on={flags.truth} title="Show simulation truth" body="Reveal what really happened, which no system can see." onClick={() => patch({ truth: !flags.truth })} />
      </div>

      <div className="sim-grid" style={{ marginTop: 18 }}>
        {frame.residents.map((resident, index) => {
          const shown = flags.truth ? resident.true_min : (flags.camera && resident.consent && !resident.blanket ? resident.camera_min : resident.since_human);
          const scale = resident.limit + scalePad;
          const width = Math.min(100, (shown / scale) * 100);
          const amber = shown >= resident.limit - LEAD_MIN;
          const red = flags.truth && resident.over;
          return (
            <article key={resident.name} className={red ? "card sim-card hot" : "card sim-card"}>
              <div className="spread">
                <strong>{resident.name}</strong>
                <span className="muted">Room {resident.room}</span>
              </div>
              <p className="muted" style={{ margin: "4px 0 8px" }}>{resident.note}</p>
              <div className="muted">Camera reads</div>
              <div>{resident.reading}{resident.confidence ? `, ${Math.round(resident.confidence * 100)}%` : ""}</div>
              <div className={red ? "posbar red" : amber ? "posbar amber" : "posbar"}>
                <i style={{ width: `${width}%` }} />
                <span className="tick" style={{ left: `${(resident.limit / scale) * 100}%` }} />
              </div>
              <p className="muted">
                {flags.truth ? `True time in position ${resident.true_min} min. Camera ${resident.camera_min} min.` : `Time in position (camera) ${resident.camera_min} min`}
                <br />Last human check {resident.since_human} min ago
                <br />Limit (care plan) {resident.limit} min
                <br />{shown > resident.limit ? "Past the limit" : "Inside limit"}
              </p>
              <div className="row">
                <button className="choice" onClick={() => {
                  nightRef.current.people[index].consent = !resident.consent;
                  setSnap(nightRef.current.snapshot());
                }}>{resident.consent ? "Consent on" : "Consent off"}</button>
                <button className="choice" onClick={() => {
                  nightRef.current.people[index].blanket = !resident.blanket;
                  setSnap(nightRef.current.snapshot());
                }}>{resident.blanket ? "Blanket on" : "Blanket off"}</button>
                <button className="choice" onClick={() => setRecordFor(recordFor === resident.name ? null : resident.name)}>Open care record</button>
              </div>
              {recordFor === resident.name && (
                <div className="mono" style={{ marginTop: 10 }}>
                  {frame.alerts.filter((item) => item.name === resident.name).map((item) => (
                    <div key={item.text + item.minute}>{clockLabel(item.minute)} {item.text}</div>
                  ))}
                  {frame.alerts.every((item) => item.name !== resident.name) && <div>No alerts for {resident.name} yet.</div>}
                  <div>This is not a chart. Records counted tonight: {frame.records}.</div>
                </div>
              )}
            </article>
          );
        })}
      </div>
      <p className="muted">
        How to read a card. The bar is time in one position from the camera&apos;s point of view, and the black line is the care-plan limit.
        It turns amber {LEAD_MIN} minutes before the limit, which is also when a human check falls due.
        A red card means the resident really went more than {TOLERANCE_MIN} minutes past the limit, which only the simulation can know, and only while simulation truth is on.
      </p>

      <h2>Maria&apos;s list</h2>
      <p>{frame.maria}</p>
      <div className="stack">
        {frame.queue.map((item, index) => (
          <div key={item.name} className="spread card">
            <div>
              <strong>{index + 1}. {item.name}</strong>
              <div className="muted">Camera: {item.camera_min} min in this position. Last human check {item.since_human} min ago.</div>
            </div>
            <div>{item.in_min === 0 ? "due" : `in ${item.in_min} min`}</div>
          </div>
        ))}
      </div>

      <h2>Alerts</h2>
      <div className="stack">
        {frame.alerts.length === 0 && <p className="muted">None yet.</p>}
        {frame.alerts.map((item) => (
          <div key={item.text + item.minute} className="spread">
            <div>
              <div className="muted">{clockLabel(item.minute)}</div>
              {item.text}
            </div>
            <span className="muted">{item.resolved ? "Resolved" : "Open"}</span>
          </div>
        ))}
      </div>

      <h2>This night so far</h2>
      <div className="metrics">
        <Stat n={frame.visits} label="Human visits" />
        <Stat n={frame.records} label="Records written automatically" />
        <Stat n={frame.alerts_sent} label={`Alerts sent (${frame.safety_net} safety-net)`} />
        <Stat n={`${frame.paperwork_min} min`} label="Paperwork avoided (estimate at 0.5 min per record)" />
        <Stat n={frame.past_episodes} label={`Times a resident went past limit + ${TOLERANCE_MIN} min`} />
        <Stat n={`${frame.longest_past} min`} label="Longest time past the limit" />
      </div>

      <h2>Run the experiments</h2>
      <p className="muted">
        One night proves little, so these run the same six residents through 40 different nights each and average the results.
        Click one to set the switches and watch a single night, or run all of them. The table is computed in this browser from the rules below. It is not a measurement, and it is not a copied result from another writeup.
      </p>
      <div className="sim-grid">
        {EXPERIMENT_PRESETS.map((preset) => (
          <button key={preset.name} className="card" style={{ textAlign: "left" }} onClick={() => watchPreset(preset)}>
            <strong>{preset.name}</strong>
            <div className="muted">{preset.blurb}</div>
          </button>
        ))}
      </div>
      <p><button className="choice on" onClick={runAll} disabled={running}>{running ? "Running…" : "Run all five over 40 nights"}</button></p>
      <div className="scroll-x">
        <table className="raw">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Ordinary visits</th>
              <th>Ordinary nights past limit + 30</th>
              <th>Ordinary records</th>
              <th>Stretched visits</th>
              <th>Stretched nights past limit + 30</th>
              <th>Stretched longest past limit (min)</th>
            </tr>
          </thead>
          <tbody>
            {!table && <tr><td colSpan={7}>Not run yet.</td></tr>}
            {table?.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td>{row.ordinary.visits}</td>
                <td>{row.ordinary.nights_past} of {row.ordinary.nights}</td>
                <td>{row.ordinary.records}</td>
                <td>{row.stretched.visits}</td>
                <td>{row.stretched.nights_past} of {row.stretched.nights}</td>
                <td>{row.stretched.longest_past}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table && <Takeaway rows={table} />}

      <h2>Your own runs</h2>
      <div className="scroll-x">
      <table className="raw">
        <thead>
          <tr>
            <th>Night</th><th>Settings</th><th>Human visits</th><th>Safety-net checks</th>
            <th>Past limit + 30 min</th><th>Longest past limit (min)</th><th>Records</th>
          </tr>
        </thead>
        <tbody>
          {own.length === 0 && <tr><td colSpan={7}>Play a night through to the end and it will land here.</td></tr>}
          {own.map((row, index) => (
            <tr key={index}>
              <td>{row.night}</td><td>{row.settings}</td><td>{row.visits}</td><td>{row.safety}</td>
              <td>{row.past}</td><td>{row.longest}</td><td>{row.records}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      <h2>What is assumed</h2>
      <ul>
        <li>Fictional residents, the limits printed on the cards, one caregiver, {NIGHT_MIN} minutes from 10:00 PM.</li>
        <li>Someone moves on their own about {SELF_PER_HOUR} times an hour. A mistaken camera, when that switch is on, confirms a turn that did not happen about {FALSE_PER_HOUR} times an hour.</li>
        <li>The alert fires {LEAD_MIN} minutes before the care-plan limit. She leaves then. An ordinary trip averages 8 minutes. A stretched trip averages 14 minutes.</li>
        <li>With the camera off, or with trust off, the check still happens on the human schedule. The camera, when it can see, changes who is first in line and writes a record.</li>
        <li>Trust makes a confirmed turn count as the check. A false confirmation never resets the true time in position. A blanket or no consent means the camera makes no claim, and that resident stays on the human schedule.</li>
        <li>Going {TOLERANCE_MIN} minutes past a limit counts as a failure. This page does not apply the hard visit cap. The safety simulation finds that a cap at the limit plus that tolerance stops false-confirm failures and gives back most of the visit savings.</li>
        <li>Paperwork avoided is an estimate of {0.5} minutes per record, not time measured on a unit.</li>
      </ul>
      <p className="muted">SomaCare. Care that notices. Every resident, name, and number on this page is fictional.</p>
    </main>
  );
}

function Toggle({ on, title, body, onClick, disabled }: { on: boolean; title: string; body: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button className={on ? "choice on" : "choice"} onClick={onClick} disabled={disabled} style={{ textAlign: "left" }}>
      <strong>{title}</strong>
      <div className="muted">{body}</div>
    </button>
  );
}

function Stat({ n, label }: { n: number | string; label: string }) {
  return (
    <div className="metric">
      <b>{n}</b>
      <span className="muted">{label}</span>
    </div>
  );
}

function Takeaway({ rows }: { rows: ExperimentRow[] }) {
  const paper = rows[0];
  const stay = rows[1];
  const trust = rows[2];
  const wrong = rows[3];
  const stayWrong = rows[4];
  return (
    <>
      <h2>What to take from this</h2>
      <p>
        Keeping people checking on schedule means this run does not reduce visits ({stay.ordinary.visits} a night against {paper.ordinary.visits} on paper).
        Its value at this stage is the order of visits and the record: {stay.ordinary.records} entries written each night, against {paper.ordinary.records} on paper.
      </p>
      <p>
        On a stretched night, seeing the resident most at risk first mattered: someone went more than 30 minutes past their limit on {paper.stretched.nights_past} of {paper.stretched.nights} paper nights and on {stay.stretched.nights_past} of {stay.stretched.nights} SomaCare nights.
        This comes from the assumptions above, so treat it as a reason to test, not a result.
      </p>
      <p>
        Trusting the camera is the time-saving case: {trust.ordinary.visits} visits a night instead of {paper.ordinary.visits}. It is only safe if the camera is right.
        When it is sometimes wrong and trusted anyway, someone went 30+ minutes past their limit on {wrong.ordinary.nights_past} of {wrong.ordinary.nights} ordinary nights.
        With people still checking, the same mistakes do it on {stayWrong.ordinary.nights_past} of {stayWrong.ordinary.nights}.
        Human checks stay until a clinician approves trust, and approval needs hundreds of hours of measured footage, not this demo.
      </p>
    </>
  );
}
