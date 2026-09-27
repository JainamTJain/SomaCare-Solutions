"""A position changes only after it holds for the configured window."""

from __future__ import annotations

from datetime import datetime


class PositionSmoother:
    def __init__(self, hold_s: float = 30, min_confidence: float = 0.7):
        self.hold_s = hold_s
        self.min_confidence = min_confidence
        self.current: str | None = None
        self._candidate: str | None = None
        self._since: datetime | None = None
        self._conf_sum = 0.0
        self._conf_n = 0

    def update(self, label: str, confidence: float, ts: datetime) -> tuple[str, str] | None:
        """Return (previous, new) when a smoothed change is committed."""
        if confidence < self.min_confidence:
            # Low confidence does not start a new class. Unknown is not a
            # trained class; it is what we report when we cannot commit.
            return None
        if label != self._candidate:
            self._candidate = label
            self._since = ts
            self._conf_sum = confidence
            self._conf_n = 1
            return None
        self._conf_sum += confidence
        self._conf_n += 1
        elapsed = (ts - self._since).total_seconds() if self._since else 0
        average = self._conf_sum / self._conf_n
        if elapsed >= self.hold_s and average >= self.min_confidence and label != self.current:
            previous = self.current
            self.current = label
            return previous, label
        return None
