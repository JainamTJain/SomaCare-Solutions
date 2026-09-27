"""Priority, merging and verified checks.

Priority starts as risk_weight times the worst pressure ratio, then rises with
the number of open tasks already on that caregiver's shift. Two tasks for the
same resident inside the merge window become one visit at the earlier due time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SchedTask:
    id: str
    resident_id: str
    kind: str
    due_at: datetime
    window_min: int = 30
    priority: float = 0.0
    room_order: int = 0
    source: str = "record"
    merged_into: str | None = None


@dataclass
class Visit:
    id: str
    resident_id: str
    kinds: list[str] = field(default_factory=list)
    due_at: datetime | None = None
    priority: float = 0.0
    room_order: int = 0
    task_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def risk_weight(extra_steps: int, braden_total: int) -> float:
    return 1 + 0.5 * extra_steps + (1.0 if braden_total <= 9 else 0.0)


def with_caregiver_load(base_priority: float, open_tasks_for_cna: int, per_open_task: float) -> float:
    """Raise a visit when this caregiver already has more open tasks waiting.

    The same resident, with the same pressure ratio, scores higher as the
    count grows. A heavier queue can therefore pass a lighter one.
    """
    waiting = max(int(open_tasks_for_cna), 0)
    return float(base_priority) * (1.0 + float(per_open_task) * waiting)


def merge_tasks(tasks: list[SchedTask], merge_window_min: float) -> list[Visit]:
    """Merge tasks for one resident when they fall inside the window of the
    earliest task in the cluster. The visit stays at that earlier time."""
    grouped: dict[str, list[SchedTask]] = {}
    for task in tasks:
        grouped.setdefault(task.resident_id, []).append(task)

    visits: list[Visit] = []
    for resident_id, group in grouped.items():
        group.sort(key=lambda t: (t.due_at, t.id))
        current: Visit | None = None
        for task in group:
            if current is None:
                current = _new_visit(task)
                visits.append(current)
                continue
            gap_min = (task.due_at - current.due_at).total_seconds() / 60.0
            if gap_min <= merge_window_min:
                task.merged_into = current.id
                if task.kind not in current.kinds:
                    current.kinds.append(task.kind)
                current.task_ids.append(task.id)
                current.sources.append(task.source)
                current.priority = max(current.priority, task.priority)
            else:
                current = _new_visit(task)
                visits.append(current)
    visits.sort(key=lambda v: (-v.priority, v.room_order, v.due_at, v.resident_id))
    return visits


def _new_visit(task: SchedTask) -> Visit:
    return Visit(
        id=task.id,
        resident_id=task.resident_id,
        kinds=[task.kind],
        due_at=task.due_at,
        priority=task.priority,
        room_order=task.room_order,
        task_ids=[task.id],
        sources=[task.source],
    )


def can_verify_check(
    *,
    camera_online: bool,
    in_bed: bool,
    settled: bool,
    confidence: float,
    open_alert: bool,
    min_confidence: float = 0.8,
) -> bool:
    """A scheduled check becomes verified without a visit only when the camera
    can actually see a settled resident. Offline cameras never verify."""
    if not camera_online:
        return False
    return bool(in_bed and settled and confidence >= min_confidence and not open_alert)
