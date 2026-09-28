// Signed stick-figure broadcast. Care decisions stay in the engine; this only carries
// snapshots the engine already produced. The video is never part of the payload.

const ECDSA = { name: "ECDSA", namedCurve: "P-256" };
const SIGN = { name: "ECDSA", hash: "SHA-256" };

function bytesOf(text) {
  const clean = text.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  const bin = atob(clean);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function canon(value) {
  if (Array.isArray(value)) return `[${value.map(canon).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canon(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function importKey(text, usage) {
  const raw = String(text || "").trim();
  if (!raw) throw new Error("invalid");
  if (raw.startsWith("{")) {
    return crypto.subtle.importKey("jwk", JSON.parse(raw), ECDSA, false, [usage]);
  }
  const format = raw.includes("PUBLIC") ? "spki" : usage === "sign" ? "pkcs8" : "spki";
  return crypto.subtle.importKey(format, bytesOf(raw), ECDSA, false, [usage]);
}

export function importPrivate(text) {
  return importKey(text, "sign");
}

export function importPublic(text) {
  return importKey(text, "verify");
}

export function slimFrame(frame) {
  if (!frame) return null;
  const people = (frame.people || []).map((person) => person.map((p) => [
    Math.round(p[0] * 1000) / 1000,
    Math.round(p[1] * 1000) / 1000,
    Math.round(((p.length > 3 ? p[3] : p[2]) ?? 1) * 100) / 100,
  ]));
  return {
    pred: frame.pred, masked: frame.masked, cand: frame.cand, hold: frame.hold,
    confirmed: frame.confirmed, rotation: frame.rotation ?? null, noPersonFor: frame.noPersonFor ?? 0,
    people, kp: people[0] || null,
  };
}

export function supabaseTransport(supabase, channelName, role) {
  const key = `${role}-${Math.random().toString(36).slice(2)}`;
  const channel = supabase.channel(channelName || "somacare-live", { config: { presence: { key } } });
  const messageHandlers = [];
  const viewerHandlers = [];
  channel.on("broadcast", { event: "pose" }, ({ payload }) => {
    for (const cb of messageHandlers) cb(payload);
  });
  const countViewers = () => {
    const state = channel.presenceState() || {};
    const n = Object.values(state).flat().filter((p) => p.role === "viewer").length;
    for (const cb of viewerHandlers) cb(n);
    return n;
  };
  channel.on("presence", { event: "sync" }, countViewers);
  channel.subscribe(async (status) => {
    if (status === "SUBSCRIBED") await channel.track({ role });
  });
  return {
    role,
    send(payload) { return channel.send({ type: "broadcast", event: "pose", payload }); },
    onMessage(cb) { messageHandlers.push(cb); },
    onViewers(cb) { viewerHandlers.push(cb); },
    close() { return supabase.removeChannel(channel); },
  };
}

export class Presenter {
  constructor(demo, transport, privateKey, { hz = 2 } = {}) {
    this.demo = demo;
    this.tx = transport;
    this.key = privateKey;
    this.pending = null;
    this.stopped = false;
    this._off = demo.onUpdate((update) => { this.pending = update; });
    this._timer = setInterval(() => { this.maybeSend(false); }, 1000 / hz);
  }
  async maybeSend(force) {
    if (this.stopped || !this.pending) return;
    const now = performance.now();
    if (!force && this._sentAt && now - this._sentAt < 400) return;
    const body = { snapshot: this.pending.snapshot, frame: slimFrame(this.pending.frame), t: Date.now() };
    const data = new TextEncoder().encode(canon(body));
    const sigBuf = await crypto.subtle.sign(SIGN, this.key, data);
    const sig = btoa(String.fromCharCode(...new Uint8Array(sigBuf)));
    await this.tx.send({ body, sig });
    this._sentAt = now;
  }
  stop() {
    this.stopped = true;
    clearInterval(this._timer);
    this._off?.();
  }
}

export class Viewer {
  constructor(transport, publicKey) {
    this.tx = transport;
    this.publicKey = publicKey;
    this.snapshot = null;
    this.frame = null;
    this.live = false;
    this.viewers = 0;
    this.samples = [];
    this.handlers = [];
    this._seenAt = 0;
    transport.onMessage((msg) => { this._take(msg); });
    transport.onViewers((n) => { this.viewers = n; this._emit(); });
    this._watch = setInterval(() => {
      if (this.live && performance.now() - this._seenAt > 8000) { this.live = false; this._emit(); }
    }, 1000);
  }
  async _take(msg) {
    try {
      const data = new TextEncoder().encode(canon(msg.body));
      const sig = Uint8Array.from(atob(msg.sig), (c) => c.charCodeAt(0));
      const ok = await crypto.subtle.verify(SIGN, this.publicKey, sig, data);
      if (!ok) return;
      this.snapshot = msg.body.snapshot;
      this.frame = msg.body.frame;
      this.live = true;
      this._seenAt = performance.now();
      const people = msg.body.frame?.people || [];
      this.samples.push({ t: this._seenAt, people });
      if (this.samples.length > 8) this.samples.shift();
      this._emit();
    } catch { /* ignore a bad packet */ }
  }
  onUpdate(cb) { this.handlers.push(cb); return () => { this.handlers = this.handlers.filter((h) => h !== cb); }; }
  _emit() {
    const u = { snapshot: this.snapshot, frame: this.frame, live: this.live, viewers: this.viewers };
    for (const cb of this.handlers) cb(u);
  }
  interpolatedPeople(maxGap = 500) {
    const b = this.samples.at(-1);
    const a = this.samples.at(-2);
    if (!b) return this.frame?.people || [];
    const now = performance.now();
    if (!a || now - b.t > maxGap) return b.people;
    const u = Math.min(1, Math.max(0, (now - a.t) / Math.max(1, b.t - a.t)));
    const n = Math.min(a.people.length, b.people.length);
    const out = [];
    for (let i = 0; i < n; i++) {
      const A = a.people[i], B = b.people[i], m = Math.min(A.length, B.length);
      const person = [];
      for (let j = 0; j < m; j++) {
        person.push([
          A[j][0] + (B[j][0] - A[j][0]) * u,
          A[j][1] + (B[j][1] - A[j][1]) * u,
          A[j][2],
        ]);
      }
      out.push(person);
    }
    return out;
  }
  close() { clearInterval(this._watch); }
}
