"""Vehicle operating mode as an explicit state machine (roadmap §11).

The transition table is the single source of truth: any (mode, event) pair not
listed is ignored and logged, never guessed. The power policy (timeouts, what
STANDBY keeps alive) is provisional until the power supervisor is designed in
phase 9; see docs/decisions/0003-vehicle-mode-state-machine.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

log = logging.getLogger(__name__)


class VehicleMode(StrEnum):
    DRIVE = "drive"
    CAMP = "camp"
    STANDBY = "standby"
    SHUTDOWN = "shutdown"
    FAULT = "fault"


class ModeEvent(StrEnum):
    ACC_ON = "acc_on"
    ACC_OFF = "acc_off"
    IDLE_TIMEOUT = "idle_timeout"  # no user activity in CAMP for the configured time
    USER_WAKE = "user_wake"  # touch/button while in STANDBY
    SHUTDOWN_REQUEST = "shutdown_request"  # explicit user/maintenance request
    POWER_FAIL = "power_fail"  # supervisor reports loss of supply
    FAULT = "fault"
    FAULT_CLEARED = "fault_cleared"


M, E = VehicleMode, ModeEvent

# (from, event) -> to. FAULT_CLEARED is resolved dynamically (see _resolve).
_TRANSITIONS: dict[tuple[VehicleMode, ModeEvent], VehicleMode] = {
    (M.STANDBY, E.ACC_ON): M.DRIVE,
    (M.STANDBY, E.USER_WAKE): M.CAMP,
    (M.STANDBY, E.SHUTDOWN_REQUEST): M.SHUTDOWN,
    (M.CAMP, E.ACC_ON): M.DRIVE,
    (M.CAMP, E.IDLE_TIMEOUT): M.STANDBY,
    (M.CAMP, E.SHUTDOWN_REQUEST): M.SHUTDOWN,
    (M.DRIVE, E.ACC_OFF): M.CAMP,
    # No SHUTDOWN_REQUEST from DRIVE: the UI must not power off while driving.
}
_FROM_ANY: dict[ModeEvent, VehicleMode] = {
    E.POWER_FAIL: M.SHUTDOWN,
    E.FAULT: M.FAULT,
}


@dataclass(frozen=True)
class Transition:
    previous: VehicleMode
    current: VehicleMode
    event: ModeEvent


class ModeMachine:
    def __init__(
        self,
        initial: VehicleMode = VehicleMode.STANDBY,
        on_transition: Callable[[Transition], None] | None = None,
    ) -> None:
        self._mode = initial
        self._acc_on = False
        self._on_transition = on_transition

    @property
    def mode(self) -> VehicleMode:
        return self._mode

    def set_acc(self, acc_on: bool) -> Transition | None:
        """Convenience: feed the ACC level, emitting an edge event only on change."""
        if acc_on == self._acc_on:
            return None
        self._acc_on = acc_on
        return self.handle(ModeEvent.ACC_ON if acc_on else ModeEvent.ACC_OFF)

    def handle(self, event: ModeEvent) -> Transition | None:
        if event is ModeEvent.ACC_ON:
            self._acc_on = True
        elif event is ModeEvent.ACC_OFF:
            self._acc_on = False

        target = self._resolve(event)
        if target is None or target == self._mode:
            log.debug("mode %s: event %s ignored", self._mode, event)
            return None
        transition = Transition(self._mode, target, event)
        self._mode = target
        log.info("mode %s -> %s on %s", transition.previous, target, event)
        if self._on_transition:
            self._on_transition(transition)
        return transition

    def _resolve(self, event: ModeEvent) -> VehicleMode | None:
        if self._mode is VehicleMode.SHUTDOWN:
            return None  # terminal until reboot
        if event in _FROM_ANY:
            return _FROM_ANY[event]
        if self._mode is VehicleMode.FAULT:
            if event is ModeEvent.FAULT_CLEARED:
                return VehicleMode.DRIVE if self._acc_on else VehicleMode.CAMP
            return None
        return _TRANSITIONS.get((self._mode, event))
