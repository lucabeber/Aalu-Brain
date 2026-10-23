"""Threshold alarms with hysteresis, plus "source not available" notices.

A threshold alarm is only evaluated on live data. Stale data neither raises
nor clears it, so an alarm cannot flicker because a device went silent;
disconnection is reported separately as a non-invasive notice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from aalu.core.models import DataQuality
from aalu.core.state_store import SourceSnapshot


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ThresholdRule:
    id: str
    source: str
    field: str
    direction: Literal["below", "above"]
    set_at: float
    clear_at: float
    severity: Severity
    message: str

    def __post_init__(self) -> None:
        if self.direction == "below":
            ok = self.clear_at > self.set_at
        else:
            ok = self.clear_at < self.set_at
        if not ok:
            raise ValueError(f"{self.id}: clear_at must be on the safe side of set_at")


@dataclass(frozen=True)
class Alarm:
    id: str
    severity: Severity
    message: str
    source: str


class AlarmEngine:
    def __init__(self, rules: list[ThresholdRule], watched_sources: dict[str, str]) -> None:
        """``watched_sources`` maps source id -> human label for availability notices."""
        self._rules = rules
        self._watched = watched_sources
        self._active: dict[str, Alarm] = {}

    @property
    def active(self) -> list[Alarm]:
        order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        return sorted(self._active.values(), key=lambda a: (order[a.severity], a.id))

    def evaluate(self, snap: SourceSnapshot) -> bool:
        """Update alarms for one source. Returns True if the active set changed."""
        before = set(self._active)

        for rule in (r for r in self._rules if r.source == snap.source):
            if not snap.quality.is_live or snap.reading is None:
                continue
            value = getattr(snap.reading, rule.field, None)
            if value is None:
                continue
            active = rule.id in self._active
            if rule.direction == "below":
                trip, clear = value <= rule.set_at, value >= rule.clear_at
            else:
                trip, clear = value >= rule.set_at, value <= rule.clear_at
            if not active and trip:
                self._active[rule.id] = Alarm(rule.id, rule.severity, rule.message, rule.source)
            elif active and clear:
                del self._active[rule.id]

        if snap.source in self._watched:
            notice_id = f"{snap.source}.unavailable"
            if snap.quality in (DataQuality.DISCONNECTED, DataQuality.ERROR):
                self._active[notice_id] = Alarm(
                    notice_id,
                    Severity.INFO,
                    f"{self._watched[snap.source]}: no data",
                    snap.source,
                )
            else:
                self._active.pop(notice_id, None)

        return set(self._active) != before
