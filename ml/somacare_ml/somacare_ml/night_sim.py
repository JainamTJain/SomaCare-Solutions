"""One fictional night in a six-bed home.

This shows how SomaCare behaves under stated assumptions. It is not a measurement from a real home,
and it does not change anyone's care plan. The live product does not skip visits because of this file.

A human check is scheduled when time since the last human check reaches the care-plan limit.
The alert fires `lead` minutes earlier. With a camera, and while trust is off, the camera only
changes who is seen first among people already due, and it writes the record. Trust is a separate
switch: a confirmed turn then counts as the check. A false confirmation resets the camera clock
and, if trust is on, the check clock. It never resets the true time in position.

A blanket or withdrawn consent means the camera makes no claim for that resident. They stay on
the human schedule. This demo does not apply the hard visit cap; `safety_sim.py` is where that
cap is measured. Names and numbers are fictional.
"""
from dataclasses import dataclass
import numpy as np

NIGHT_MIN = 480
LEAD_MIN = 15
TOLERANCE_MIN = 30
SELF_PER_HOUR = 0.25
FALSE_PER_HOUR = 0.10
POSITIONS = ("back", "left", "right", "sitting")
PAPERWORK_MIN = 0.5

# Opening frame of the interactive night. Experiments draw a fresh start each night.
OPENING = (
    ("Elena Alvarez", "12", "High risk, foam mattress", 120, "left", 33, 39),
    ("James Okonkwo", "14", "Moderate risk, foam mattress", 120, "right", 65, 83),
    ("Mei Lin", "16", "Very high risk, standard mattress", 90, "back", 47, 66),
    ("Rosa Delgado", "18", "Moderate risk, foam, extended interval approved", 180, "right", 78, 79),
    ("Harold Bennett", "20", "Moderate risk, foam mattress", 120, "back", 20, 29),
    ("Leticia Ramos", "22", "Moderate risk, foam mattress", 150, "back", 60, 64),
)


def _gauss(rng, mean, sd):
    return float(max(1.0, rng.normal(mean, sd)))


@dataclass
class Resident:
    name: str
    room: str
    note: str
    limit: int
    position: str
    true_min: float
    belief_min: float
    since_human: float
    consent: bool = True
    blanket: bool = False
    alerted: bool = False


@dataclass
class Scenario:
    name: str
    camera: bool = True
    trust: bool = False
    mistakes: bool = False
    stretched: bool = False
    # Travel time, in minutes, once she leaves. She leaves when the alert fires.
    response_mean: float = 8.0
    response_sd: float = 3.0


def paper():
    return Scenario("Paper", camera=False, trust=False, mistakes=False)


def _response(stretched):
    # Ordinary: she usually arrives before the limit. Stretched: the trip is long enough that
    # a second person waiting can pass the tolerance, which is where visit order matters.
    if stretched:
        return 14.0, 5.0
    return 8.0, 3.0


def human_checks_stay(mistakes=False, stretched=False):
    mean, sd = _response(stretched)
    return Scenario("SomaCare, human checks stay", camera=True, trust=False, mistakes=mistakes, stretched=stretched,
                    response_mean=mean, response_sd=sd)


def trust_camera(mistakes=False, stretched=False):
    mean, sd = _response(stretched)
    return Scenario("SomaCare, trust the camera", camera=True, trust=True, mistakes=mistakes, stretched=stretched,
                    response_mean=mean, response_sd=sd)


def _fresh(rng, opening=False):
    people = []
    for name, room, note, limit, pos, belief, since in OPENING:
        if opening:
            # The scripted first frame: the camera and the last human check already differ.
            true_min, belief_min, since_human, position = float(belief), float(belief), float(since), pos
        else:
            # Until someone moves on their own, time in position matches time since the last check.
            since_human = float(rng.integers(0, limit))
            true_min = since_human
            belief_min = true_min
            position = POSITIONS[int(rng.integers(0, len(POSITIONS)))]
        people.append(Resident(name, room, note, limit, position, true_min, belief_min, since_human))
    return people


def _sees(p, scn):
    return scn.camera and p.consent and not p.blanket


def _clock(p, scn):
    """The clock a check is scheduled on. Trust uses the camera only while it can see."""
    if scn.trust and _sees(p, scn):
        return p.belief_min
    return p.since_human


def _urgency(p, scn):
    if scn.camera and _sees(p, scn):
        return p.belief_min / p.limit
    return p.since_human / p.limit


def _turn(rng, p):
    choices = [x for x in POSITIONS if x != p.position]
    p.position = choices[int(rng.integers(0, len(choices)))]


class Night:
    def __init__(self, scn: Scenario, seed=0, opening=False):
        self.scn = scn
        self.rng = np.random.default_rng(seed)
        self.people = _fresh(self.rng, opening=opening)
        self.minute = 0
        self.visits = 0
        self.records = 0
        self.alerts = 0
        self.safety_net = 0
        self.past_limit_episodes = 0
        self.longest_past = 0.0
        self._in_fail = [False] * len(self.people)
        self.had_fail = False
        self.feed = []
        self.caregiver = None  # dict(name, arrives)
        self.done = False

    def snapshot(self):
        queue = sorted(self.people, key=lambda p: p.limit - _clock(p, self.scn))[:4]
        if self.caregiver is None:
            maria = "Free. Nobody is waiting on her."
        else:
            maria = "On the way to %s." % self.caregiver["name"]
        rows = []
        for p in self.people:
            sees = _sees(p, self.scn)
            if not p.consent:
                reading, conf = "no consent", 0.0
            elif p.blanket or not self.scn.camera:
                reading, conf = "not sure", 0.0
            else:
                reading, conf = _label(p.position), 0.92
            true_over = p.true_min > p.limit + TOLERANCE_MIN
            rows.append(dict(
                name=p.name, room=p.room, note=p.note, limit=p.limit,
                reading=reading, confidence=conf, sees=sees,
                camera_min=round(p.belief_min), true_min=round(p.true_min),
                since_human=round(p.since_human), consent=p.consent, blanket=p.blanket,
                over=true_over,
            ))
        return dict(
            minute=self.minute, maria=maria, residents=rows,
            queue=[dict(name=p.name, camera_min=round(p.belief_min), since_human=round(p.since_human),
                        in_min=max(0, round(p.limit - _clock(p, self.scn)))) for p in queue],
            alerts=list(self.feed),
            visits=self.visits, records=self.records, alerts_sent=self.alerts,
            safety_net=self.safety_net,
            paperwork_min=round(self.records * PAPERWORK_MIN, 1),
            past_episodes=self.past_limit_episodes,
            longest_past=round(self.longest_past, 1),
        )

    def step(self):
        if self.done:
            return self.snapshot()
        scn, rng = self.scn, self.rng
        # Arrivals happen on the minute they were promised, before clocks advance,
        # so a visit scheduled for this minute still lands on it.
        if self.caregiver is not None and self.minute >= self.caregiver["arrives"]:
            self._visit(self.caregiver["index"])
            self.caregiver = None
        for i, p in enumerate(self.people):
            p.true_min += 1
            p.belief_min += 1
            p.since_human += 1
            if rng.random() < SELF_PER_HOUR / 60.0:
                p.true_min = 0.0
                _turn(rng, p)
                if _sees(p, scn):
                    p.belief_min = 0.0
                    self.records += 1
                    if scn.trust:
                        p.since_human = 0.0
                        p.alerted = False
            if scn.mistakes and _sees(p, scn) and rng.random() < FALSE_PER_HOUR / 60.0:
                p.belief_min = 0.0
                self.records += 1
                if scn.trust:
                    p.since_human = 0.0
                    p.alerted = False
            clock = _clock(p, scn)
            if not p.alerted and clock >= p.limit - LEAD_MIN:
                p.alerted = True
                self.alerts += 1
                safety = not (scn.trust and _sees(p, scn))
                if safety:
                    self.safety_net += 1
                self._push_alert(p, safety)
            past = p.true_min - p.limit
            if past > self.longest_past:
                self.longest_past = past
            over = p.true_min > p.limit + TOLERANCE_MIN
            if over and not self._in_fail[i]:
                self.past_limit_episodes += 1
                self.had_fail = True
                self._in_fail[i] = True
            if not over:
                self._in_fail[i] = False
        if self.caregiver is None:
            # She leaves when the alert fires, lead minutes before the limit.
            due = [i for i, p in enumerate(self.people) if _clock(p, scn) >= p.limit - LEAD_MIN]
            if due:
                due.sort(key=lambda i: _urgency(self.people[i], scn), reverse=True)
                idx = due[0]
                delay = _gauss(rng, scn.response_mean, scn.response_sd)
                self.caregiver = dict(name=self.people[idx].name, index=idx, arrives=self.minute + delay)
        self.minute += 1
        if self.minute >= NIGHT_MIN:
            self.done = True
        return self.snapshot()

    def _visit(self, index):
        p = self.people[index]
        p.true_min = 0.0
        p.belief_min = 0.0
        p.since_human = 0.0
        p.alerted = False
        _turn(self.rng, p)
        self.visits += 1
        self.records += 1
        self._resolve(p.name)

    def _push_alert(self, p, safety):
        if safety and self.scn.camera and _sees(p, self.scn):
            text = ("Human check due for %s. The camera says %d min in this position, "
                    "but a person still looks in until trust is earned." % (p.name, round(p.belief_min)))
        elif safety:
            text = "Human check due for %s. Scheduled from the last check." % p.name
        else:
            text = "Check due for %s. A confirmed position is being trusted to count." % p.name
        self.feed.insert(0, dict(minute=self.minute, text=text, name=p.name, resolved=False))
        self.feed = self.feed[:8]

    def _resolve(self, name):
        for item in self.feed:
            if item["name"] == name and not item["resolved"]:
                item["resolved"] = True
                break

    def run(self):
        while not self.done:
            self.step()
        return self.summary()

    def summary(self):
        return dict(scenario=self.scn.name, visits=self.visits, records=self.records,
                    alerts=self.alerts, safety_net=self.safety_net,
                    past_episodes=self.past_limit_episodes, had_fail=self.had_fail,
                    longest_past=round(max(self.longest_past, 0.0), 1))


def _label(position):
    return {"left": "left side", "right": "right side", "back": "back", "sitting": "sitting"}.get(position, position)


def run_cell(scn_factory, nights=40, seed=0, stretched=False):
    visits, records, fails, longest = [], [], 0, []
    for n in range(nights):
        scn = scn_factory(stretched)
        out = Night(scn, seed=seed + 1000 * int(stretched) + n, opening=False).run()
        visits.append(out["visits"])
        records.append(out["records"])
        fails += int(out["had_fail"])
        longest.append(out["longest_past"])
    return dict(visits=round(float(np.mean(visits)), 1),
                nights_past=fails, nights=nights,
                records=int(round(float(np.mean(records)))),
                longest_past=round(float(np.mean(longest)), 1))


def experiments(nights=40, seed=0):
    """Five cells, ordinary and stretched. Counts come from this simulator."""
    specs = [
        ("Paper", lambda stretched: Scenario(
            "Paper", camera=False, trust=False, mistakes=False, stretched=stretched,
            response_mean=_response(stretched)[0], response_sd=_response(stretched)[1])),
        ("SomaCare, human checks stay", lambda stretched: human_checks_stay(False, stretched)),
        ("SomaCare, trust the camera", lambda stretched: trust_camera(False, stretched)),
        ("Trusted, and sometimes wrong", lambda stretched: trust_camera(True, stretched)),
        ("Human checks stay, camera sometimes wrong", lambda stretched: human_checks_stay(True, stretched)),
    ]
    rows = []
    for name, factory in specs:
        ordinary = run_cell(factory, nights, seed, False)
        stretched = run_cell(factory, nights, seed, True)
        rows.append(dict(name=name, ordinary=ordinary, stretched=stretched))
    return rows
