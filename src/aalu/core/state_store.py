"""Latest reading per source, with age-based quality degradation.

The store is single-threaded by design: adapters running in worker threads must
hand readings over to the owner thread (the Qt bridge does this with a queued
signal). Age is measured with a monotonic clock, so a wrong wall clock (Pi
without RTC battery, no NTP offline) never makes data look fresh.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aalu.core.models import DataQuality, Reading


@dataclass(frozen=True)
class Freshness:
    stale_after_s: float
    disconnected_after_s: float

    def __post_init__(self) -> None:
        if not 0 < self.stale_after_s < self.disconnected_after_s:
            raise ValueError("need 0 < stale_after_s < disconnected_after_s")


DEFAULT_FRESHNESS = Freshness(stale_after_s=5.0, disconnected_after_s=15.0)


@dataclass(frozen=True)
class SourceSnapshot:
    source: str
    reading: Reading | None
    quality: DataQuality
    age_s: float | None
    simulated: bool

    def view(self) -> dict[str, Any]:
        """Flat dict for the UI.

        Measured values are dropped once the source is disconnected or in
        error, so the UI can only show dashes, never a frozen old number.
        """
        out: dict[str, Any] = {
            "source": self.source,
            "quality": self.quality.value,
            "simulated": self.simulated,
            "age_s": None if self.age_s is None else round(self.age_s, 1),
        }
        if self.reading is not None and self.quality in (
            DataQuality.VALID,
            DataQuality.SIMULATED,
            DataQuality.STALE,
        ):
            out.update(self.reading.measured_fields())
        return out


@dataclass
class _Entry:
    reading: Reading | None = None
    received_at: float | None = None
    quality: DataQuality = DataQuality.DISCONNECTED
    simulated: bool = False


Listener = Callable[[str], None]


class StateStore:
    def __init__(
        self,
        freshness: Mapping[str, Freshness] | None = None,
        default_freshness: Freshness = DEFAULT_FRESHNESS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._freshness = dict(freshness or {})
        self._default = default_freshness
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._listeners: list[Listener] = []

    # --- registration / subscription -------------------------------------
    def register(self, source: str, *, simulated: bool) -> None:
        self._entries.setdefault(source, _Entry()).simulated = simulated

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def sources(self) -> list[str]:
        return sorted(self._entries)

    def freshness_for(self, source: str) -> Freshness:
        return self._freshness.get(source, self._default)

    # --- updates ---------------------------------------------------------
    def update(self, reading: Reading) -> None:
        entry = self._entries.setdefault(reading.source, _Entry())
        entry.reading = reading
        entry.received_at = self._clock()
        entry.quality = reading.quality
        self._notify(reading.source)

    def refresh(self) -> list[str]:
        """Re-evaluate age-based quality. Returns sources whose quality changed."""
        changed: list[str] = []
        for source, entry in self._entries.items():
            new_quality = self._effective_quality(source, entry)
            if new_quality != entry.quality:
                entry.quality = new_quality
                changed.append(source)
        for source in changed:
            self._notify(source)
        return changed

    def snapshot(self, source: str) -> SourceSnapshot:
        entry = self._entries.get(source, _Entry())
        age = None if entry.received_at is None else self._clock() - entry.received_at
        return SourceSnapshot(
            source=source,
            reading=entry.reading,
            quality=entry.quality,
            age_s=age,
            simulated=entry.simulated,
        )

    # --- internals -------------------------------------------------------
    def _effective_quality(self, source: str, entry: _Entry) -> DataQuality:
        if entry.reading is None or entry.received_at is None:
            return DataQuality.DISCONNECTED
        age = self._clock() - entry.received_at
        fresh = self.freshness_for(source)
        if age >= fresh.disconnected_after_s:
            return DataQuality.DISCONNECTED
        if age >= fresh.stale_after_s:
            return DataQuality.STALE
        return entry.reading.quality

    def _notify(self, source: str) -> None:
        for listener in self._listeners:
            listener(source)
