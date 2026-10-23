"""Qt bridge: exposes VehicleCore state to QML and routes touch commands back.

QML sees two context objects:
- ``Vehicle``: a QQmlPropertyMap of plain values (one key per source plus
  ``mode``, ``alarms``, ...), each key with its own change notification.
- ``Backend``: slots for commands (media, audio, loads, simulation, theme).

Python ``None`` arrives in QML as ``undefined``: test with ``v == null``.
"""

from __future__ import annotations

import dataclasses
import logging
import subprocess

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtQml import QQmlPropertyMap

from aalu.core.models import Reading
from aalu.services.vehicle_core import VehicleCore

log = logging.getLogger(__name__)


class Backend(QObject):
    # Emitted from adapter threads; Qt queues delivery to the GUI thread.
    _reading = Signal(object)
    nightModeChanged = Signal()

    def __init__(self, core: VehicleCore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self._night = core.config.night_mode
        self.vehicle = QQmlPropertyMap(self)
        self._reading.connect(self._on_reading)
        core.subscribe(self._on_topics)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(core.tick)

        self._push_all()

    def start(self) -> None:
        self._core.start(self._reading.emit)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._core.stop()

    # --- state push ------------------------------------------------------
    def _on_reading(self, reading: Reading) -> None:
        self._core.ingest(reading)

    def _on_topics(self, topics: set[str]) -> None:
        core = self._core
        for topic in topics:
            if topic in core.store.sources():
                self.vehicle.insert(topic, core.store.snapshot(topic).view())
        if topics & {"mode", "gnss", "vehicle_inputs"}:
            self.vehicle.insert("mode", core.modes.mode.value)
            self.vehicle.insert("driveLocked", core.drive_locked)
            self.vehicle.insert("reverse", core.reverse_active)
        if topics & {"loads", "vehicle_inputs"}:
            self.vehicle.insert("loadsView", core.loads_view())
        if "energy" in topics:
            self.vehicle.insert("energy", core.energy_view)
        if "alarms" in topics:
            self.vehicle.insert("alarms", [
                {"id": a.id, "severity": a.severity.value, "message": a.message}
                for a in core.alarms.active
            ])
        if "events" in topics:
            self.vehicle.insert("events", [{"time": t, "text": x} for t, x in core.events])
        if "diagnostics" in topics:
            self.vehicle.insert("diagnostics", core.diagnostics())
            # Ages change every second; refresh the per-source views too.
            for source in core.store.sources():
                self.vehicle.insert(source, core.store.snapshot(source).view())

    def _push_all(self) -> None:
        core = self._core
        self.vehicle.insert("simulated", core.any_simulated())
        self.vehicle.insert("scenario", core.scenario.as_dict())
        self.vehicle.insert("navigationAvailable", bool(core.config.navigation_command))
        self.vehicle.insert("mapConfig", dataclasses.asdict(core.config.map))
        self._on_topics(set(core.store.sources())
                        | {"mode", "alarms", "events", "diagnostics", "loads", "energy"})

    # --- theme -----------------------------------------------------------
    def _get_night(self) -> bool:
        return self._night

    def _set_night(self, value: bool) -> None:
        if value != self._night:
            self._night = value
            self.nightModeChanged.emit()

    nightMode = Property(bool, _get_night, _set_night, notify=nightModeChanged)

    # --- commands from QML -----------------------------------------------
    @Slot()
    def userActivity(self) -> None:
        self._core.user_activity()

    @Slot()
    def mediaPlay(self) -> None:
        if self._core.media:
            self._core.media.play()

    @Slot()
    def mediaPause(self) -> None:
        if self._core.media:
            self._core.media.pause()

    @Slot()
    def mediaNext(self) -> None:
        if self._core.media:
            self._core.media.next()

    @Slot()
    def mediaPrevious(self) -> None:
        if self._core.media:
            self._core.media.previous()

    @Slot(int)
    def setVolume(self, pct: int) -> None:
        if self._core.audio:
            self._core.audio.set_volume(pct)

    @Slot(bool)
    def setMuted(self, muted: bool) -> None:
        if self._core.audio:
            self._core.audio.set_muted(muted)

    @Slot(str)
    def setEqPreset(self, name: str) -> None:
        if self._core.audio and not self._core.drive_locked:
            self._core.audio.set_eq_preset(name)

    @Slot(str, bool)
    def setLoad(self, output: str, on: bool) -> None:
        self._core.request_load(output, on)

    @Slot(str, bool)
    def setScenario(self, key: str, value: bool) -> None:
        self._core.scenario.set(key, value)
        self.vehicle.insert("scenario", self._core.scenario.as_dict())

    @Slot()
    def launchNavigation(self) -> None:
        cmd = self._core.config.navigation_command
        if not cmd:
            return
        try:
            # Separate process (roadmap phase 4): a navigation crash cannot take the dashboard down.
            subprocess.Popen(cmd, start_new_session=True)
        except OSError:
            log.exception("navigation: cannot start %s", cmd)
