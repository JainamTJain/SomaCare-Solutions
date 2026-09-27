"""Alert delivery, escalation and resolution.

Every alert stores the rule, inputs, plan version and model version. Those
fields live on AlertState and are persisted by the API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class AlertState:
    id: str
    task_id: str
    staff_id: str
    created_at: datetime
    rule: str
    inputs: dict[str, Any]
    plan_version: int
    model_version: str
    status: str = "sent"
    accepted_at: datetime | None = None
    resolved_at: datetime | None = None
    charge_notified: bool = False
    resend_count: int = 0
    resident_id: str = ""
    actions: list[str] = field(default_factory=list)


def advance_alert(
    alert: AlertState,
    now: datetime,
    cfg,
    *,
    saw_confirming_event: bool,
) -> list[str]:
    """Step one alert forward.

    Not accepted within `alert_accept_min`: resend and notify the charge nurse.
    Not resolved within `alert_resolve_min`: escalate as overdue.
    A turn or care_visit resolves it at any point.
    """
    actions: list[str] = []
    if alert.status == "resolved":
        return actions

    if saw_confirming_event:
        alert.status = "resolved"
        alert.resolved_at = now
        actions.append("resolved")
        alert.actions.extend(actions)
        return actions

    if alert.accepted_at is None and alert.resend_count == 0:
        if now - alert.created_at >= timedelta(minutes=cfg.alert_accept_min):
            alert.resend_count += 1
            alert.charge_notified = True
            actions.extend(["resend", "notify_charge"])

    if alert.status != "escalated":
        if now - alert.created_at >= timedelta(minutes=cfg.alert_resolve_min):
            alert.status = "escalated"
            actions.append("escalate")

    alert.actions.extend(actions)
    return actions


def allow_send(sent_this_hour: int, cfg) -> bool:
    return sent_this_hour < cfg.alerts_per_cna_per_hour


def group_room(room_order: int, span: int = 2) -> int:
    """Neighboring rooms share a group so one walk can cover them."""
    return room_order // span
