"""Vehicle Core: adapters -> state store -> mode machine / alarms -> UI views.

Qt-free. The owner calls :meth:`ingest` with readings (on its own thread) and
:meth:`tick` about once a second.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aalu.adapters.audio.fake import FakeAudioOutput, FakePhone
from aalu.adapters.base import (
    Adapter,
    AudioOutputController,
    LoadController,
    MediaController,
    Publish,
)
from aalu.adapters.gps.fake import FakeGnss, Route
from aalu.adapters.gps.serial_nmea import NmeaReplayAdapter, NmeaSerialAdapter
from aalu.adapters.mcu.fake import FakeMcu
from aalu.adapters.scenario import Scenario
from aalu.adapters.system.health import SystemHealthAdapter
from aalu.adapters.victron.fake import FakeVictron
from aalu.core.alarms import AlarmEngine
from aalu.core.models import GnssFix, GnssReading, Reading, VehicleInputsReading
from aalu.core.modes import ModeEvent, ModeMachine, Transition, VehicleMode
from aalu.core.state_store import StateStore
from aalu.services.config import AppConfig, ConfigError
from aalu.services.energy import EnergyBalance, EnergyConfig

log = logging.getLogger(__name__)

SOURCE_LABELS = {
    "gnss": "GNSS",
    "house_battery": "House battery",
    "solar": "Solar charger",
    "dcdc": "Engine charger (DC-DC)",
    "fresh_water": "Fresh water",
    "grey_water": "Grey water",
    "media": "Bluetooth",
    "audio_output": "Audio output",
    "vehicle_inputs": "Vehicle inputs",
    "loads": "Loads",
    "system": "System",
}
# Sources whose loss is shown as a (non-invasive) notice in the alarm panel.
WATCHED_SOURCES = ("gnss", "house_battery", "solar", "dcdc", "vehicle_inputs", "loads")
ENERGY_SOURCES = {"house_battery", "solar", "dcdc"}

LOAD_CONFIRM_TIMEOUT_S = 3.0
PARKED_SPEED_KMH = 3.0


@dataclass
class _Request:
    on: bool
    at: float


class VehicleCore:
    def __init__(self, config: AppConfig, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self._clock = clock
        self.scenario = Scenario()
        self.store = StateStore(config.freshness, clock=clock)
        self.modes = ModeMachine(on_transition=self._on_transition)
        self.alarms = AlarmEngine(
            config.alarm_rules, {s: SOURCE_LABELS[s] for s in WATCHED_SOURCES}
        )
        # Wall-clock time is for display only (may be wrong offline without RTC battery).
        self.events: deque[tuple[str, str]] = deque(maxlen=200)
        self._requests: dict[str, _Request] = {}
        self._booted = False
        self._started_at = clock()
        self._never_seen_checked: set[str] = set()
        self._last_activity = clock()
        self._listeners: list[Callable[[set[str]], None]] = []
        self.energy = EnergyBalance(EnergyConfig(
            capacity_ah=config.battery_capacity_ah,
            reserve_soc_pct=config.battery_reserve_soc_pct,
        ))
        self.energy_view: dict[str, Any] = {}

        self.media: MediaController | None = None
        self.audio: AudioOutputController | None = None
        self.load_controller: LoadController | None = None
        self.adapters: list[Adapter] = self._build_adapters()
        for adapter in self.adapters:
            for source in adapter.sources:
                self.store.register(source, simulated=adapter.simulated)
        self._update_energy()  # "unknown" until the battery monitor reports

    # --- lifecycle -------------------------------------------------------
    def start(self, publish: Publish) -> None:
        """Start adapters. ``publish`` must marshal readings to :meth:`ingest`'s thread."""
        for adapter in self.adapters:
            adapter.start(publish)
        self._event("System started")

    def stop(self) -> None:
        for adapter in self.adapters:
            adapter.stop()

    def subscribe(self, listener: Callable[[set[str]], None]) -> None:
        """``listener(topics)`` is called after state changes; topics are source ids or
        ``mode``, ``alarms``, ``events``, ``loads``."""
        self._listeners.append(listener)

    # --- inputs ----------------------------------------------------------
    def ingest(self, reading: Reading) -> None:
        topics = {reading.source}
        self.store.update(reading)
        if isinstance(reading, VehicleInputsReading) and reading.acc_on is not None:
            before = self.modes.mode
            if not self._booted:
                self._booted = True
                self.modes.handle(ModeEvent.ACC_ON if reading.acc_on else ModeEvent.USER_WAKE)
            else:
                self.modes.set_acc(reading.acc_on)
            if self.modes.mode != before:
                topics.add("mode")
        if reading.source == "loads":
            self._settle_requests()
            topics.add("loads")
        if reading.source in ENERGY_SOURCES:
            self._update_energy()
            topics.add("energy")
        if self.alarms.evaluate(self.store.snapshot(reading.source)):
            topics.add("alarms")
        self._emit(topics)

    def tick(self) -> None:
        topics: set[str] = set()
        for source in self.store.refresh():
            topics.add(source)
            snap = self.store.snapshot(source)
            self._event(f"{SOURCE_LABELS.get(source, source)}: {snap.quality.value}")
            if self.alarms.evaluate(snap):
                topics.add("alarms")
            if source == "loads":
                topics.add("loads")
            if source in ENERGY_SOURCES:
                self._update_energy()
                topics.add("energy")
        topics |= self._check_never_seen()
        if self._expire_requests():
            topics.add("loads")
        timeout = self.config.camp_idle_timeout_s
        if (
            timeout > 0
            and self.modes.mode is VehicleMode.CAMP
            and self._clock() - self._last_activity > timeout
            and self.modes.handle(ModeEvent.IDLE_TIMEOUT)
        ):
            topics.add("mode")
        # Ages tick every second, keep diagnostics fresh.
        topics.add("diagnostics")
        self._emit(topics)

    def user_activity(self) -> None:
        self._last_activity = self._clock()
        if self.modes.mode is VehicleMode.STANDBY and self.modes.handle(ModeEvent.USER_WAKE):
            self._emit({"mode"})

    # --- commands --------------------------------------------------------
    def loads_available(self) -> bool:
        return self.load_controller is not None and self.store.snapshot("loads").quality.is_live

    def request_load(self, output: str, on: bool) -> bool:
        if not self.loads_available():
            log.warning("load %s request refused: MCU not available", output)
            return False
        assert self.load_controller is not None
        self.load_controller.request(output, on)
        self._requests[output] = _Request(on, self._clock())
        self._event(f"Request {output} {'ON' if on else 'OFF'}")
        self._emit({"loads", "events"})
        return True

    # --- derived state for the UI -----------------------------------------
    @property
    def drive_locked(self) -> bool:
        """Complex settings are locked in DRIVE unless GNSS proves we are parked."""
        if self.modes.mode is not VehicleMode.DRIVE:
            return False
        snap = self.store.snapshot("gnss")
        reading = snap.reading
        if not (snap.quality.is_live and isinstance(reading, GnssReading)):
            return True
        if reading.fix is GnssFix.NO_FIX or reading.speed_kmh is None:
            return True
        return reading.speed_kmh > PARKED_SPEED_KMH

    @property
    def reverse_active(self) -> bool:
        snap = self.store.snapshot("vehicle_inputs")
        reading = snap.reading
        return (snap.quality.is_live and isinstance(reading, VehicleInputsReading)
                and reading.reverse is True)

    def loads_view(self) -> dict[str, Any]:
        snap = self.store.snapshot("loads")
        confirmed: dict[str, bool] = {}
        if snap.quality.is_live and snap.reading is not None:
            confirmed = dict(getattr(snap.reading, "outputs", {}))
        names = list(confirmed) or list(getattr(self.load_controller, "output_names", ()))
        out: dict[str, Any] = {"available": self.loads_available(), "quality": snap.quality.value,
                               "simulated": snap.simulated, "outputs": {}}
        for name in names:
            req = self._requests.get(name)
            out["outputs"][name] = {
                "on": confirmed.get(name),  # None = unknown
                "pending": req is not None,
                "requested": None if req is None else req.on,
            }
        return out

    def diagnostics(self) -> list[dict[str, Any]]:
        rows = []
        for source in self.store.sources():
            snap = self.store.snapshot(source)
            rows.append({
                "source": source,
                "label": SOURCE_LABELS.get(source, source),
                "quality": snap.quality.value,
                "simulated": snap.simulated,
                "age_s": None if snap.age_s is None else round(snap.age_s, 1),
            })
        return rows

    def any_simulated(self) -> bool:
        return any(self.store.snapshot(s).simulated for s in self.store.sources())

    # --- internals -------------------------------------------------------
    def _build_adapters(self) -> list[Adapter]:
        c, sc = self.config, self.scenario
        adapters: list[Adapter] = []

        kind = c.gnss.get("adapter", "fake")
        if kind == "fake":
            route = None
            if c.gnss.get("route"):
                try:
                    route = Route.load(c.resolve(c.gnss["route"]))
                except (OSError, ValueError, KeyError) as exc:
                    log.warning("fake GNSS: route %s unusable (%s), driving a circle",
                                c.gnss["route"], exc)
            adapters.append(FakeGnss(sc, clock=self._clock, route=route))
        elif kind == "serial":
            adapters.append(NmeaSerialAdapter(c.gnss["port"], int(c.gnss.get("baudrate", 115200))))
        elif kind == "replay":
            adapters.append(NmeaReplayAdapter(c.gnss["file"]))
        elif kind != "none":
            raise ConfigError(f"unknown gnss adapter {kind!r}")

        mcu: FakeMcu | None = None
        kind = c.mcu.get("adapter", "fake")
        if kind == "fake":
            mcu = FakeMcu(sc, clock=self._clock)
            self.load_controller = mcu
            adapters.append(mcu)
        elif kind != "none":
            raise ConfigError(f"mcu: adapter {kind!r} not implemented yet")

        kind = c.victron.get("adapter", "fake")
        if kind == "fake":
            adapters.append(FakeVictron(
                sc, clock=self._clock, capacity_ah=c.battery_capacity_ah,
                time_scale=c.sim_time_scale,
                # Switched loads draw from the simulated battery.
                extra_load_a=mcu.confirmed_load_a if mcu else (lambda: 0.0),
            ))
        elif kind != "none":
            raise ConfigError(f"victron: adapter {kind!r} not implemented yet")

        kind = c.media.get("adapter", "fake")
        if kind == "fake":
            self.media = FakePhone(sc, clock=self._clock)
            self.audio = FakeAudioOutput()
            adapters += [self.media, self.audio]
        elif kind != "none":
            raise ConfigError(f"media: adapter {kind!r} not implemented yet")

        if c.system.get("adapter", "real") == "real":
            adapters.append(SystemHealthAdapter(c.system.get("data_dir", "/")))
        return adapters

    def _check_never_seen(self) -> set[str]:
        """A source missing since boot never changes quality, so refresh() never reports it.
        Evaluate it once its disconnect timeout has elapsed since startup."""
        topics: set[str] = set()
        uptime = self._clock() - self._started_at
        for source in self.store.sources():
            if source in self._never_seen_checked:
                continue
            snap = self.store.snapshot(source)
            if snap.reading is not None:
                self._never_seen_checked.add(source)
            elif uptime >= self.store.freshness_for(source).disconnected_after_s:
                self._never_seen_checked.add(source)
                self._event(f"{SOURCE_LABELS.get(source, source)}: no data since startup")
                if self.alarms.evaluate(snap):
                    topics.add("alarms")
        return topics

    def _update_energy(self) -> None:
        self.energy_view = self.energy.update(
            self._clock(),
            self.store.snapshot("house_battery"),
            self.store.snapshot("solar"),
            self.store.snapshot("dcdc"),
        )

    def _settle_requests(self) -> None:
        snap = self.store.snapshot("loads")
        outputs = getattr(snap.reading, "outputs", {}) if snap.reading else {}
        for name, req in list(self._requests.items()):
            if outputs.get(name) == req.on:
                del self._requests[name]

    def _expire_requests(self) -> bool:
        now, expired = self._clock(), False
        for name, req in list(self._requests.items()):
            if now - req.at > LOAD_CONFIRM_TIMEOUT_S:
                del self._requests[name]
                self._event(f"{name}: command not confirmed by the MCU")
                expired = True
        return expired

    def _on_transition(self, t: Transition) -> None:
        self._event(f"Mode {t.previous.value.upper()} → {t.current.value.upper()}")

    def _event(self, text: str) -> None:
        log.info(text)
        self.events.appendleft((datetime.now().strftime("%H:%M:%S"), text))
        self._emit({"events"})

    def _emit(self, topics: set[str]) -> None:
        for listener in self._listeners:
            listener(topics)
