from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from aalu.adapters.base import PolledAdapter
from aalu.adapters.scenario import Scenario
from aalu.core.models import DataQuality, LoadsReading, Reading, TankReading, VehicleInputsReading

DEFAULT_OUTPUTS = ("light_living", "light_kitchen", "light_awning", "water_pump")
# Simulated current draw of each output when on (A at 12 V).
LOAD_CURRENT_A = {"light_living": 1.2, "light_kitchen": 0.8, "light_awning": 1.5,
                  "water_pump": 4.5}


class FakeMcu(PolledAdapter):
    """I/O microcontroller: protected inputs, tank senders and load outputs.

    Load requests are confirmed only after ``confirm_delay_s``, like a real
    MCU round trip, so the UI must distinguish "requested" from "confirmed".
    """

    sources = ("vehicle_inputs", "fresh_water", "grey_water", "loads")
    simulated = True
    interval_s = 0.25

    def __init__(
        self,
        scenario: Scenario,
        clock: Callable[[], float] = time.monotonic,
        outputs: tuple[str, ...] = DEFAULT_OUTPUTS,
        confirm_delay_s: float = 0.4,
    ) -> None:
        super().__init__()
        self._scenario = scenario
        self._clock = clock
        self._lock = threading.Lock()
        self._outputs = dict.fromkeys(outputs, False)
        self._pending: dict[str, tuple[bool, float]] = {}
        self._confirm_delay = confirm_delay_s

    # LoadController
    @property
    def output_names(self) -> tuple[str, ...]:
        return tuple(self._outputs)

    def confirmed_load_a(self) -> float:
        """Current drawn by the outputs that are on (feeds the fake battery)."""
        with self._lock:
            return sum(LOAD_CURRENT_A.get(n, 0.0) for n, on in self._outputs.items() if on)

    def request(self, output: str, on: bool) -> None:
        if output not in self._outputs:
            raise KeyError(output)
        if not self._scenario.mcu_connected:
            return  # lost on the wire: the UI keeps showing the confirmed state
        with self._lock:
            self._pending[output] = (bool(on), self._clock() + self._confirm_delay)

    def read(self) -> list[Reading] | None:
        sc = self._scenario
        if not sc.mcu_connected:
            return None
        now = self._clock()
        with self._lock:
            for name, (value, due) in list(self._pending.items()):
                if now >= due:
                    self._outputs[name] = value
                    del self._pending[name]
            outputs = dict(self._outputs)

        pump_on = outputs.get("water_pump", False)
        fresh = 64.0 - (6.0 if pump_on else 0.0) + 2.0 * math.sin(now / 30.0)  # sloshing
        return [
            VehicleInputsReading(
                quality=DataQuality.SIMULATED,
                acc_on=sc.acc_on,
                reverse=sc.reverse and sc.acc_on,
            ),
            TankReading(source="fresh_water", quality=DataQuality.SIMULATED,
                        level_pct=round(fresh), capacity_l=100.0),
            TankReading(source="grey_water", quality=DataQuality.SIMULATED,
                        level_pct=31.0, capacity_l=80.0),
            LoadsReading(quality=DataQuality.SIMULATED, outputs=outputs),
        ]
