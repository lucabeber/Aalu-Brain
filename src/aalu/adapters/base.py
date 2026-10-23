"""Adapter interfaces shared by fake and real implementations.

An adapter produces readings for one or more sources (``sources``) and pushes them through
``publish``. It may call ``publish`` from any thread; the consumer is
responsible for marshalling to its own thread. An adapter that loses its
device simply stops publishing: the state store turns silence into
``stale`` and then ``disconnected``.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Protocol

from aalu.core.models import Reading

Publish = Callable[[Reading], None]
log = logging.getLogger(__name__)


class Adapter(Protocol):
    sources: tuple[str, ...]
    simulated: bool

    def start(self, publish: Publish) -> None: ...
    def stop(self) -> None: ...


class PolledAdapter(ABC):
    """Adapter that is sampled at a fixed interval by a background thread."""

    sources: tuple[str, ...]
    simulated: bool = False
    interval_s: float = 1.0

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @abstractmethod
    def read(self) -> Reading | list[Reading] | None:
        """Return reading(s), or None when the device is not available."""

    def start(self, publish: Publish) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(publish,), name=f"adapter-{self.sources[0]}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self, publish: Publish) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                reading = self.read()
            except Exception:  # an adapter bug must not kill the dashboard
                log.exception("adapter %s: read failed", self.sources)
                reading = None
            if isinstance(reading, list):
                for r in reading:
                    publish(r)
            elif reading is not None:
                publish(reading)
            self._stop.wait(max(0.0, self.interval_s - (time.monotonic() - started)))


class MediaController(Protocol):
    """Remote control of the phone's player (AVRCP on the real adapter)."""

    def play(self) -> None: ...
    def pause(self) -> None: ...
    def next(self) -> None: ...
    def previous(self) -> None: ...


class AudioOutputController(Protocol):
    """Local output: one volume stage only, to avoid double digital gain."""

    def set_volume(self, pct: int) -> None: ...
    def set_muted(self, muted: bool) -> None: ...
    def set_eq_preset(self, name: str) -> None: ...


class LoadController(Protocol):
    """Requests output changes from the I/O MCU.

    A request is not a state: the UI must show the state the MCU confirms
    through a ``LoadsReading``.
    """

    output_names: tuple[str, ...]

    def request(self, output: str, on: bool) -> None: ...
