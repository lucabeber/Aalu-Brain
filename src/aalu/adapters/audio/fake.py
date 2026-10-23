from __future__ import annotations

import threading
import time
from collections.abc import Callable

from aalu.adapters.base import PolledAdapter
from aalu.adapters.scenario import Scenario
from aalu.core.models import (
    AudioOutputReading,
    DataQuality,
    MediaReading,
    PhoneLink,
    PlaybackStatus,
)

EQ_PRESETS = ("flat", "voice", "drive", "night")

_PLAYLIST = (
    ("Demo track one", "Simulated artist", "Test album", 214_000),
    ("Demo track two", "Simulated artist", "Test album", 187_000),
    ("Demo track three", "Another artist", "Compilation", 245_000),
)


class FakePhone(PolledAdapter):
    """Phone connected over A2DP/AVRCP, with a fixed playlist."""

    sources = ("media",)
    simulated = True
    interval_s = 0.5

    def __init__(self, scenario: Scenario, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self._scenario = scenario
        self._clock = clock
        self._lock = threading.Lock()
        self._track = 0
        self._position_ms = 0.0
        self._playing = True
        self._last = clock()

    # MediaController
    def play(self) -> None:
        with self._lock:
            self._playing = True

    def pause(self) -> None:
        with self._lock:
            self._playing = False

    def next(self) -> None:
        with self._lock:
            self._track = (self._track + 1) % len(_PLAYLIST)
            self._position_ms = 0.0

    def previous(self) -> None:
        with self._lock:
            # Like most head units: restart the track unless we are at its beginning.
            if self._position_ms > 3000:
                self._position_ms = 0.0
            else:
                self._track = (self._track - 1) % len(_PLAYLIST)
                self._position_ms = 0.0

    def read(self) -> MediaReading:
        now = self._clock()
        with self._lock:
            dt, self._last = now - self._last, now
            if not self._scenario.phone_connected:
                return MediaReading(quality=DataQuality.SIMULATED, link=PhoneLink.DISCONNECTED)
            title, artist, album, duration = _PLAYLIST[self._track]
            if self._playing:
                self._position_ms += dt * 1000.0
                if self._position_ms >= duration:
                    self._track = (self._track + 1) % len(_PLAYLIST)
                    self._position_ms = 0.0
                    title, artist, album, duration = _PLAYLIST[self._track]
            return MediaReading(
                quality=DataQuality.SIMULATED,
                link=PhoneLink.CONNECTED,
                device_name="Simulated phone",
                status=PlaybackStatus.PLAYING if self._playing else PlaybackStatus.PAUSED,
                title=title,
                artist=artist,
                album=album,
                position_ms=int(self._position_ms),
                duration_ms=duration,
            )


class FakeAudioOutput(PolledAdapter):
    sources = ("audio_output",)
    simulated = True
    interval_s = 1.0

    def __init__(self) -> None:
        super().__init__()
        self._volume = 35
        self._muted = False
        self._eq = "flat"
        self._publish: Callable[[AudioOutputReading], None] | None = None

    def start(self, publish) -> None:  # type: ignore[override]
        self._publish = publish
        super().start(publish)

    def set_volume(self, pct: int) -> None:
        self._volume = max(0, min(100, int(pct)))
        self._push()

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._push()

    def set_eq_preset(self, name: str) -> None:
        if name not in EQ_PRESETS:
            raise ValueError(f"unknown EQ preset {name!r}")
        self._eq = name
        self._push()

    def read(self) -> AudioOutputReading:
        return AudioOutputReading(
            quality=DataQuality.SIMULATED,
            volume_pct=self._volume,
            muted=self._muted,
            eq_preset=self._eq,
        )

    def _push(self) -> None:
        # Immediate feedback for the slider instead of waiting for the next poll.
        if self._publish:
            self._publish(self.read())
