"""The floor: residents, care clock, sensor state, events. One lock, one version counter
(the SSE stream sends a new snapshot whenever the version changes, and once a second anyway)."""
import copy, json, threading, time
from collections import deque
from pathlib import Path
from . import engine
from .scheduler import schedule
from .posture import HoldConfirmer

NIGHT_START_MIN = 22 * 60

def clock_str(m):
    m = int(round(NIGHT_START_MIN + m)) % 1440; return f"{m // 60:02d}:{m % 60:02d}"

class CareClock:
    """Care minutes since 22:00. time_scale = care seconds per wall second (1 = real time;
    use e.g. 96 for an 8 h timelapse that plays in 5 min)."""
    def __init__(self, time_scale=1.0, start_min=0.0):
        self.scale, self.start, self.t0 = time_scale, start_min, time.monotonic()
    def now(self): return self.start + (time.monotonic() - self.t0) * self.scale / 60.0

class Floor:
    def __init__(self, residents, caregivers=("Maria", "Joy"), clock=None):
        self.lock = threading.RLock(); self.clock = clock or CareClock()
        self.R = {r["id"]: r for r in copy.deepcopy(residents)}
        for r in self.R.values(): r.setdefault("skin_provisional", {})
        self.S = {}; now = self.clock.now()
        for rid, r in self.R.items():
            p = r["start_posture"]
            self.S[rid] = dict(posture=p, last_turn=r["last_turn"], wet=False, wet_since_clock=None,
                               site_free_since={s: (None if s in engine.POSTURES[p]["sites"] else r["last_turn"]) for s in engine.SITES},
                               hold=HoldConfirmer(p), live=None, done_pending=None)
        self.caregivers = list(caregivers); self.events = deque(maxlen=200); self.version = 0
        self.last_photo = {}

    @classmethod
    def from_file(cls, path, **kw): return cls(json.loads(Path(path).read_text()), **kw)

    def _log(self, rid, text, kind="info"):
        self.events.appendleft(dict(t=round(self.clock.now(), 1), clock=clock_str(self.clock.now()),
                                    room=self.R[rid]["room"] if rid else "", text=text, kind=kind)); self.version += 1

    def _apply_turn(self, rid, frm, to, at, how):
        s = self.S[rid]
        for site in engine.POSTURES[frm]["sites"]: s["site_free_since"][site] = at
        for site in engine.POSTURES[to]["sites"]: s["site_free_since"][site] = None
        s["posture"], s["last_turn"] = to, at; s["hold"].confirmed = to
        self._log(rid, f"Turn to {engine.POSTURES[to]['short']} {how}. Clock reset.", "turn")
        if s["done_pending"]: s["done_pending"] = None

    # ---- inputs ----
    def sensor_update(self, rid, pred, masked, keypoints=None):
        with self.lock:
            t = self.clock.now(); s = self.S[rid]
            s["live"] = dict(best=pred["best"], conf=round(pred["conf"], 2),
                             probs={k: round(v, 2) for k, v in pred["probs"].items()},
                             reason=pred.get("reason") or ("second person at bedside" if masked else None),
                             twist=round(pred["feat"]["twist"]) if pred.get("feat") else None,
                             keypoints=keypoints, t=round(t, 1))
            ev = s["hold"].update(t, pred, masked)
            if ev and ev["type"] == "turn": self._apply_turn(rid, ev["frm"], ev["to"], ev["at"], "confirmed by the camera after a 3 min hold")
            elif ev and ev["type"] == "shift":
                self._log(rid, f"Brief shift toward {engine.POSTURES[ev['toward']]['short']} ({ev['minutes']} min). Not counted as a turn.", "shift")
            self.version += 1

    def manual_posture(self, rid, posture, who="caregiver"):
        with self.lock:
            s = self.S[rid]
            if posture != s["posture"]: self._apply_turn(rid, s["posture"], posture, self.clock.now(), f"recorded by {who}")

    def set_wet(self, rid, wet, source="caregiver"):
        with self.lock:
            s = self.S[rid]; s["wet"] = wet
            s["wet_since_clock"] = clock_str(self.clock.now()) if wet else None
            self._log(rid, ("Wet: " if wet else "Changed and dry: ") + f"reported by {source}.", "wet")

    def update_inputs(self, rid, patch):
        with self.lock:
            r = self.R[rid]
            for k in ("braden", "cfs", "mattress", "nurse_max"):
                if k in patch: r[k] = {**r[k], **patch[k]} if k == "braden" else patch[k]
            self._log(rid, "Resident inputs updated: " + ", ".join(patch), "input")

    def skin_suggestion(self, rid, site, suggestion, auto_apply):
        with self.lock:
            self.last_photo[rid] = dict(site=site, **suggestion, clock=clock_str(self.clock.now()))
            f = suggestion.get("finding")
            if auto_apply and f and f != "intact":
                self.R[rid]["skin_provisional"][site] = f
                self._log(rid, f"Bath photo, {engine.SITES[site].lower()}: model suggests {engine.FINDING_TEXT[f]}. Plan tightened until a nurse confirms.", "skin")
            else:
                self._log(rid, f"Bath photo, {engine.SITES[site].lower()}: {suggestion.get('message','saved for nurse review')}.", "skin")

    def skin_confirm(self, rid, site, finding, nurse="nurse"):
        with self.lock:
            self.R[rid]["skin"][site] = finding; self.R[rid]["skin_provisional"].pop(site, None)
            self._log(rid, f"{nurse} confirmed {engine.SITES[site].lower()}: {engine.FINDING_TEXT[finding]}.", "skin")

    def task_done(self, rid, caregiver):
        with self.lock:
            self.S[rid]["done_pending"] = dict(by=caregiver, at=self.clock.now())
            if self.S[rid]["wet"]: self.set_wet(rid, False, caregiver)
            self._log(rid, f"{caregiver} marked the round done. Waiting for the camera to confirm the turn.", "care")

    # ---- output ----
    def snapshot(self):
        with self.lock:
            now = self.clock.now(); rows = []
            for rid, r in self.R.items():
                s = self.S[rid]
                if s["done_pending"] and now - s["done_pending"]["at"] > 8 and r.get("source") == "video":
                    self._log(rid, f"Round marked done by {s['done_pending']['by']} but no turn seen by the camera. Please check.", "alert")
                    s["done_pending"] = None
                p = engine.plan(r, s, now); tr = engine.tier(r, s)
                rows.append(dict(id=rid, room=r["room"], name=r["name"], age=r["age"], source=r.get("source"),
                                 braden=engine.braden(r), braden_parts=r["braden"], cfs=r["cfs"], mattress=r["mattress"],
                                 nurse_max=r.get("nurse_max"), skin=r["skin"], skin_provisional=r["skin_provisional"],
                                 posture=s["posture"], posture_label=engine.POSTURES[s["posture"]]["label"],
                                 minutes_in_posture=round(now - s["last_turn"]), wet=s["wet"], live=s["live"],
                                 tier=tr, tier_name=engine.TIERS[tr], due_col=engine.due_col(p),
                                 plan={**p, "due_clock": clock_str(p["due"]) if p["due"] is not None else None,
                                       "next_label": engine.POSTURES[p["next"]]["label"] if p["next"] else None},
                                 last_photo=self.last_photo.get(rid)))
            entries = [dict(rid=x["id"], plan=x["plan"], tier=x["tier"], wet=x["wet"]) for x in rows]
            tasks = schedule(entries, self.caregivers, now)
            for tk in tasks:
                tk["start_clock"], tk["due_clock"] = clock_str(tk["start"]), clock_str(tk["due"])
                tk["room"] = self.R[tk["rid"]]["room"]; tk["name"] = self.R[tk["rid"]]["name"]
            order = [tk["rid"] for tk in tasks] + [x["id"] for x in rows if x["id"] not in {tk["rid"] for tk in tasks}]
            rows.sort(key=lambda x: order.index(x["id"]))
            matrix = [[[x["room"] for x in rows if x["tier"] == ti and x["due_col"] == ci] for ci in range(5)] for ti in range(4, -1, -1)]
            return dict(now=round(now, 2), clock=clock_str(now), version=self.version, residents=rows, tasks=tasks,
                        matrix=dict(rows=engine.TIERS[::-1], cols=engine.DUE_COLS, cells=matrix),
                        events=list(self.events)[:40])
