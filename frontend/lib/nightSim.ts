/** Fictional six-bed night. Same rules as ml/somacare_ml/somacare_ml/night_sim.py.
 * Counts are from this generator. They are not a home measurement. */

export const NIGHT_MIN = 480;
export const LEAD_MIN = 15;
export const TOLERANCE_MIN = 30;
export const SELF_PER_HOUR = 0.25;
export const FALSE_PER_HOUR = 0.1;
export const PAPERWORK_MIN = 0.5;
const POSITIONS = ["back", "left", "right", "sitting"] as const;

export type Position = (typeof POSITIONS)[number];

const OPENING: Array<[string, string, string, number, Position, number, number]> = [
  ["Elena Alvarez", "12", "High risk, foam mattress", 120, "left", 33, 39],
  ["James Okonkwo", "14", "Moderate risk, foam mattress", 120, "right", 65, 83],
  ["Mei Lin", "16", "Very high risk, standard mattress", 90, "back", 47, 66],
  ["Rosa Delgado", "18", "Moderate risk, foam, extended interval approved", 180, "right", 78, 79],
  ["Harold Bennett", "20", "Moderate risk, foam mattress", 120, "back", 20, 29],
  ["Leticia Ramos", "22", "Moderate risk, foam mattress", 150, "back", 60, 64],
];

export type Scenario = {
  name: string;
  camera: boolean;
  trust: boolean;
  mistakes: boolean;
  stretched: boolean;
  response_mean: number;
  response_sd: number;
};

export type ResidentSnap = {
  name: string;
  room: string;
  note: string;
  limit: number;
  reading: string;
  confidence: number;
  camera_min: number;
  true_min: number;
  since_human: number;
  consent: boolean;
  blanket: boolean;
  over: boolean;
};

export type AlertSnap = { minute: number; text: string; name: string; resolved: boolean };

export type Snap = {
  minute: number;
  maria: string;
  residents: ResidentSnap[];
  queue: Array<{ name: string; camera_min: number; since_human: number; in_min: number }>;
  alerts: AlertSnap[];
  visits: number;
  records: number;
  alerts_sent: number;
  safety_net: number;
  paperwork_min: number;
  past_episodes: number;
  longest_past: number;
};

export type Cell = {
  visits: number;
  nights_past: number;
  nights: number;
  records: number;
  longest_past: number;
};

export type ExperimentRow = { name: string; ordinary: Cell; stretched: Cell };

type Resident = {
  name: string;
  room: string;
  note: string;
  limit: number;
  position: Position;
  true_min: number;
  belief_min: number;
  since_human: number;
  consent: boolean;
  blanket: boolean;
  alerted: boolean;
};

type Rng = {
  random: () => number;
  normal: (mean: number, sd: number) => number;
  integers: (lo: number, hi: number) => number;
};

function makeRng(seed: number): Rng {
  let s = seed >>> 0 || 1;
  const next = () => {
    s = (Math.imul(1664525, s) + 1013904223) >>> 0;
    return s / 4294967296;
  };
  return {
    random: next,
    normal(mean, sd) {
      const u = Math.max(next(), 1e-9);
      const v = next();
      const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
      return Math.max(1, mean + sd * z);
    },
    integers(lo, hi) {
      return lo + Math.floor(next() * (hi - lo));
    },
  };
}

export function responseFor(stretched: boolean): [number, number] {
  return stretched ? [14, 5] : [8, 3];
}

export function makeScenario(flags: {
  camera: boolean;
  trust: boolean;
  mistakes: boolean;
  stretched: boolean;
  name?: string;
}): Scenario {
  const [response_mean, response_sd] = responseFor(flags.stretched);
  return {
    name: flags.name ?? "This night",
    camera: flags.camera,
    trust: flags.trust,
    mistakes: flags.mistakes,
    stretched: flags.stretched,
    response_mean,
    response_sd,
  };
}

function label(position: string): string {
  if (position === "left") return "left side";
  if (position === "right") return "right side";
  return position;
}

function sees(p: Resident, scn: Scenario): boolean {
  return scn.camera && p.consent && !p.blanket;
}

function clock(p: Resident, scn: Scenario): number {
  if (scn.trust && sees(p, scn)) return p.belief_min;
  return p.since_human;
}

function urgency(p: Resident, scn: Scenario): number {
  if (scn.camera && sees(p, scn)) return p.belief_min / p.limit;
  return p.since_human / p.limit;
}

function turn(rng: Rng, p: Resident) {
  const choices = POSITIONS.filter((x) => x !== p.position);
  p.position = choices[rng.integers(0, choices.length)];
}

function fresh(rng: Rng, opening: boolean): Resident[] {
  return OPENING.map(([name, room, note, limit, pos, belief, since]) => {
    let true_min: number;
    let belief_min: number;
    let since_human: number;
    let position: Position;
    if (opening) {
      true_min = belief;
      belief_min = belief;
      since_human = since;
      position = pos;
    } else {
      since_human = rng.integers(0, limit);
      true_min = since_human;
      belief_min = true_min;
      position = POSITIONS[rng.integers(0, POSITIONS.length)];
    }
    return {
      name, room, note, limit, position, true_min, belief_min, since_human,
      consent: true, blanket: false, alerted: false,
    };
  });
}

export class Night {
  scn: Scenario;
  rng: Rng;
  people: Resident[];
  minute = 0;
  visits = 0;
  records = 0;
  alerts = 0;
  safety_net = 0;
  past_limit_episodes = 0;
  longest_past = 0;
  had_fail = false;
  done = false;
  private inFail: boolean[];
  private feed: AlertSnap[] = [];
  private caregiver: { name: string; index: number; arrives: number } | null = null;

  constructor(scn: Scenario, seed = 0, opening = false) {
    this.scn = scn;
    this.rng = makeRng(seed);
    this.people = fresh(this.rng, opening);
    this.inFail = this.people.map(() => false);
  }

  snapshot(): Snap {
    const queue = [...this.people].sort((a, b) => (a.limit - clock(a, this.scn)) - (b.limit - clock(b, this.scn))).slice(0, 4);
    const maria = this.caregiver ? `On the way to ${this.caregiver.name}.` : "Free. Nobody is waiting on her.";
    return {
      minute: this.minute,
      maria,
      residents: this.people.map((p) => {
        let reading = label(p.position);
        let confidence = 0.92;
        if (!p.consent) {
          reading = "no consent";
          confidence = 0;
        } else if (p.blanket || !this.scn.camera) {
          reading = "not sure";
          confidence = 0;
        }
        return {
          name: p.name, room: p.room, note: p.note, limit: p.limit,
          reading, confidence,
          camera_min: Math.round(p.belief_min),
          true_min: Math.round(p.true_min),
          since_human: Math.round(p.since_human),
          consent: p.consent, blanket: p.blanket,
          over: p.true_min > p.limit + TOLERANCE_MIN,
        };
      }),
      queue: queue.map((p) => ({
        name: p.name,
        camera_min: Math.round(p.belief_min),
        since_human: Math.round(p.since_human),
        in_min: Math.max(0, Math.round(p.limit - clock(p, this.scn))),
      })),
      alerts: this.feed.map((item) => ({ ...item })),
      visits: this.visits,
      records: this.records,
      alerts_sent: this.alerts,
      safety_net: this.safety_net,
      paperwork_min: Math.round(this.records * PAPERWORK_MIN * 10) / 10,
      past_episodes: this.past_limit_episodes,
      longest_past: Math.round(Math.max(this.longest_past, 0) * 10) / 10,
    };
  }

  step(): Snap {
    if (this.done) return this.snapshot();
    const { scn, rng } = this;
    if (this.caregiver && this.minute >= this.caregiver.arrives) {
      this.visit(this.caregiver.index);
      this.caregiver = null;
    }
    this.people.forEach((p, i) => {
      p.true_min += 1;
      p.belief_min += 1;
      p.since_human += 1;
      if (rng.random() < SELF_PER_HOUR / 60) {
        p.true_min = 0;
        turn(rng, p);
        if (sees(p, scn)) {
          p.belief_min = 0;
          this.records += 1;
          if (scn.trust) {
            p.since_human = 0;
            p.alerted = false;
          }
        }
      }
      if (scn.mistakes && sees(p, scn) && rng.random() < FALSE_PER_HOUR / 60) {
        p.belief_min = 0;
        this.records += 1;
        if (scn.trust) {
          p.since_human = 0;
          p.alerted = false;
        }
      }
      const dueClock = clock(p, scn);
      if (!p.alerted && dueClock >= p.limit - LEAD_MIN) {
        p.alerted = true;
        this.alerts += 1;
        const safety = !(scn.trust && sees(p, scn));
        if (safety) this.safety_net += 1;
        this.pushAlert(p, safety);
      }
      const past = p.true_min - p.limit;
      if (past > this.longest_past) this.longest_past = past;
      const over = p.true_min > p.limit + TOLERANCE_MIN;
      if (over && !this.inFail[i]) {
        this.past_limit_episodes += 1;
        this.had_fail = true;
        this.inFail[i] = true;
      }
      if (!over) this.inFail[i] = false;
    });
    if (!this.caregiver) {
      const due = this.people
        .map((p, i) => ({ i, p }))
        .filter(({ p }) => clock(p, scn) >= p.limit - LEAD_MIN)
        .sort((a, b) => urgency(b.p, scn) - urgency(a.p, scn));
      if (due.length) {
        const idx = due[0].i;
        this.caregiver = {
          name: this.people[idx].name,
          index: idx,
          arrives: this.minute + rng.normal(scn.response_mean, scn.response_sd),
        };
      }
    }
    this.minute += 1;
    if (this.minute >= NIGHT_MIN) this.done = true;
    return this.snapshot();
  }

  private visit(index: number) {
    const p = this.people[index];
    p.true_min = 0;
    p.belief_min = 0;
    p.since_human = 0;
    p.alerted = false;
    turn(this.rng, p);
    this.visits += 1;
    this.records += 1;
    for (const item of this.feed) {
      if (item.name === p.name && !item.resolved) {
        item.resolved = true;
        break;
      }
    }
  }

  private pushAlert(p: Resident, safety: boolean) {
    let text: string;
    if (safety && this.scn.camera && sees(p, this.scn)) {
      text = `Human check due for ${p.name}. The camera says ${Math.round(p.belief_min)} min in this position, but a person still looks in until trust is earned.`;
    } else if (safety) {
      text = `Human check due for ${p.name}. Scheduled from the last check.`;
    } else {
      text = `Check due for ${p.name}. A confirmed position is being trusted to count.`;
    }
    this.feed.unshift({ minute: this.minute, text, name: p.name, resolved: false });
    this.feed = this.feed.slice(0, 8);
  }

  run() {
    while (!this.done) this.step();
    return {
      visits: this.visits,
      records: this.records,
      had_fail: this.had_fail,
      longest_past: Math.round(Math.max(this.longest_past, 0) * 10) / 10,
    };
  }
}

function runCell(factory: (stretched: boolean) => Scenario, nights: number, seed: number, stretched: boolean): Cell {
  const visits: number[] = [];
  const records: number[] = [];
  const longest: number[] = [];
  let fails = 0;
  for (let n = 0; n < nights; n += 1) {
    const out = new Night(factory(stretched), seed + 1000 * (stretched ? 1 : 0) + n, false).run();
    visits.push(out.visits);
    records.push(out.records);
    longest.push(out.longest_past);
    if (out.had_fail) fails += 1;
  }
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  return {
    visits: Math.round(mean(visits) * 10) / 10,
    nights_past: fails,
    nights,
    records: Math.round(mean(records)),
    longest_past: Math.round(mean(longest) * 10) / 10,
  };
}

export function experiments(nights = 40, seed = 1): ExperimentRow[] {
  const specs: Array<[string, (stretched: boolean) => Scenario]> = [
    ["Paper", (stretched) => makeScenario({ camera: false, trust: false, mistakes: false, stretched, name: "Paper" })],
    ["SomaCare, human checks stay", (stretched) => makeScenario({ camera: true, trust: false, mistakes: false, stretched, name: "SomaCare, human checks stay" })],
    ["SomaCare, trust the camera", (stretched) => makeScenario({ camera: true, trust: true, mistakes: false, stretched, name: "SomaCare, trust the camera" })],
    ["Trusted, and sometimes wrong", (stretched) => makeScenario({ camera: true, trust: true, mistakes: true, stretched, name: "Trusted, and sometimes wrong" })],
    ["Human checks stay, camera sometimes wrong", (stretched) => makeScenario({ camera: true, trust: false, mistakes: true, stretched, name: "Human checks stay, camera sometimes wrong" })],
  ];
  return specs.map(([name, factory]) => ({
    name,
    ordinary: runCell(factory, nights, seed, false),
    stretched: runCell(factory, nights, seed, true),
  }));
}

export function clockLabel(minute: number): string {
  const m = (22 * 60 + minute) % (24 * 60);
  const h = Math.floor(m / 60);
  const min = m % 60;
  const suffix = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  return `${h12}:${String(min).padStart(2, "0")} ${suffix}`;
}

export const EXPERIMENT_PRESETS: Array<{
  name: string;
  blurb: string;
  camera: boolean;
  trust: boolean;
  mistakes: boolean;
}> = [
  { name: "Paper", blurb: "No camera. Scheduled checks only, ordered by time since the last turn.", camera: false, trust: false, mistakes: false },
  { name: "SomaCare, human checks stay", blurb: "Camera on. A person still checks on the same schedule. The camera changes the order, and writes the record.", camera: true, trust: false, mistakes: false },
  { name: "SomaCare, trust the camera", blurb: "A clinician has approved it. A confirmed turn counts as a check, so there are fewer visits.", camera: true, trust: true, mistakes: false },
  { name: "Trusted, and sometimes wrong", blurb: "What trusting the camera too early looks like. A false turn resets the clock and nobody looks in.", camera: true, trust: true, mistakes: true },
  { name: "Human checks stay, camera sometimes wrong", blurb: "The same mistakes, with people still checking on schedule.", camera: true, trust: false, mistakes: true },
];
