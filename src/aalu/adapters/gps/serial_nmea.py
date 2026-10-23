"""Real GNSS adapter: NMEA lines from a serial port, or replayed from a log file.

Serial access needs the optional ``pyserial`` dependency (``pip install .[serial]``).
On unplug or read errors the adapter goes quiet and retries with backoff;
the state store reports the source as stale and then disconnected meanwhile.

``gpsd`` integration (roadmap phase 4) can replace this later behind the same
adapter interface; this direct reader is kept for bench tests and logs.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from aalu.adapters.base import Publish
from aalu.adapters.gps.nmea import NmeaAccumulator
from aalu.core.models import DataQuality

log = logging.getLogger(__name__)


class NmeaSerialAdapter:
    sources = ("gnss",)
    simulated = False

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self._port = port
        self._baudrate = baudrate
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, publish: Publish) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(publish,),
                                        name="adapter-gnss", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _lines(self) -> Iterator[str]:
        import serial  # optional dependency, imported only when used

        with serial.Serial(self._port, self._baudrate, timeout=1.0) as port:
            log.info("GNSS: opened %s @ %d", self._port, self._baudrate)
            while not self._stop.is_set():
                raw = port.readline()
                if raw:
                    yield raw.decode("ascii", errors="replace")

    def _run(self, publish: Publish) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            acc = NmeaAccumulator()
            try:
                for line in self._lines():
                    backoff = 1.0
                    reading = acc.feed(line)
                    if reading is not None:
                        publish(reading)
            except Exception as exc:  # serial.SerialException, OSError, ImportError...
                log.warning("GNSS: %s unavailable (%s); retry in %.0fs", self._port, exc, backoff)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30.0)


class NmeaReplayAdapter:
    """Replays a saved NMEA log at roughly real time, looping. For bench/demo use."""

    sources = ("gnss",)
    simulated = True  # recorded data, not a live measurement

    def __init__(self, path: str | Path, epoch_s: float = 1.0) -> None:
        self._path = Path(path)
        self._epoch_s = epoch_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, publish: Publish) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(publish,),
                                        name="adapter-gnss-replay", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self, publish: Publish) -> None:
        while not self._stop.is_set():
            acc = NmeaAccumulator()
            for line in self._path.read_text(errors="replace").splitlines():
                if self._stop.is_set():
                    return
                reading = acc.feed(line)
                if reading is not None:
                    publish(replace(reading, quality=DataQuality.SIMULATED))
                    self._stop.wait(self._epoch_s)
