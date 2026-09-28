"""Caregiver scheduler: rank residents, then assign tasks greedily to on-shift caregivers,
estimating when each caregiver can actually arrive. Flags turns that will be late."""
from .engine import POSTURES

TASK_MIN = {"turn": 6, "change_turn": 9}
TRAVEL_MIN = 2

def rank(entries):
    """entries: list of dict(rid, plan, tier, wet). Most urgent first."""
    def key(e):
        m = e["plan"]["mins_to_due"]
        return (0 if e["wet"] else 1 if m is not None else 2, m if m is not None else 1e9, -e["tier"])
    timed = [e for e in entries if e["plan"]["mins_to_due"] is not None or e["wet"]]
    return sorted(timed, key=key) + [e for e in entries if e not in timed]

def schedule(entries, caregivers, now, horizon=120):
    free_at = {c: now for c in caregivers}
    tasks = []
    for e in rank(entries):
        p = e["plan"]
        if not e["wet"] and (p["mins_to_due"] is None or p["mins_to_due"] > horizon):
            continue
        kind = "change_turn" if e["wet"] else "turn"
        cg = min(free_at, key=free_at.get) if free_at else None
        start = max(free_at.get(cg, now), now) + TRAVEL_MIN
        due = p["due"] if p["due"] is not None else now
        # do not wake someone far ahead of schedule: start no earlier than 15 min before due
        if not e["wet"]: start = max(start, due - 15)
        late = max(0, start - due) if p["due"] is not None else 0
        if cg: free_at[cg] = start + TASK_MIN[kind]
        to = POSTURES[p["next"]]["short"] if p["next"] else "a position the nurse chooses"
        what = ("Change the brief, then turn to " if kind == "change_turn" else "Turn to ") + to
        tasks.append(dict(rid=e["rid"], caregiver=cg, kind=kind, start=start, due=due,
                          late_by=round(late), instruction=what))
    return tasks
