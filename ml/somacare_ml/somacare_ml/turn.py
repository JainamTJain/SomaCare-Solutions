"""Turns noisy per-frame position readings into confirmed events.

Rules (all in config):
  a new position counts only after it holds for hold_s seconds with mean confidence at least min_conf
  an unsure reading (low confidence or 'unknown') never confirms anything and never resets a care timer
  a change seen while a second person is in the bed zone is a caregiver turn, otherwise self-repositioning
  silence longer than gap_s means the feed dropped, and the pending change is discarded
"""
from dataclasses import dataclass
from typing import Optional, List
from .config import TurnConfig


@dataclass
class Event:
    ts: float
    kind: str                       # 'position' | 'turn' | 'self_reposition' | 'uncertain' | 'feed_gap'
    position: Optional[str] = None
    previous: Optional[str] = None
    confidence: float = 0.0
    assisted: bool = False
    resets_timer: bool = False      # only confirmed changes do


class TurnDetector:
    def __init__(self, cfg: TurnConfig = TurnConfig(), initial: Optional[str] = None):
        self.cfg = cfg
        self.current = initial
        self._cand = None           # dict(label, since, conf_sum, n, persons_max)
        self._last_ts = None
        self._uncertain_since = None

    @property
    def uncertain_since(self):
        return self._uncertain_since

    def _sure(self, label, conf):
        return conf >= self.cfg.min_conf and label not in self.cfg.unknown_labels

    def update(self, ts: float, label: str, conf: float, persons: int = 1) -> List[Event]:
        out: List[Event] = []
        if self._last_ts is not None and ts - self._last_ts > self.cfg.gap_s:
            out.append(Event(ts, "feed_gap"))
            self._cand = None
            self._uncertain_since = None
        self._last_ts = ts

        if not self._sure(label, conf):
            if self._uncertain_since is None:
                self._uncertain_since = ts
                out.append(Event(ts, "uncertain", confidence=conf))
            # an unsure frame pauses a pending change but does not cancel it
            return out
        self._uncertain_since = None

        if self.current is None:
            self.current = label
            out.append(Event(ts, "position", position=label, previous=None, confidence=conf))
            return out

        if label == self.current:
            self._cand = None
            return out

        c = self._cand
        if c is None or c["label"] != label:
            self._cand = dict(label=label, since=ts, conf_sum=conf, n=1, persons_max=persons)
            return out
        c["conf_sum"] += conf; c["n"] += 1; c["persons_max"] = max(c["persons_max"], persons)
        mean_conf = c["conf_sum"] / c["n"]
        if ts - c["since"] >= self.cfg.hold_s and mean_conf >= self.cfg.min_conf:
            assisted = c["persons_max"] >= self.cfg.assisted_persons
            prev = self.current
            self.current = label
            self._cand = None
            out.append(Event(ts, "turn" if assisted else "self_reposition", position=label, previous=prev,
                             confidence=mean_conf, assisted=assisted, resets_timer=True))
        return out
