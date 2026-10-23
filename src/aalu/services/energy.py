"""House battery energy balance: sources, consumption, net, time to full/empty.

The battery monitor (shunt) measures the *net* current. Chargers report what
they deliver. Consumption is not measured directly:

    consumption = solar + engine (DC-DC) - net

so it is only shown when all three are live. Time estimates use an
exponentially smoothed net current (fridge cycling would otherwise make them
jump) and are approximations: charging slows down near 100 % (absorption).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from aalu.core.models import BatteryReading, DcDcReading, SolarReading
from aalu.core.state_store import SourceSnapshot

IDLE_BAND_A = 0.5  # |net| below this: "balanced", no estimate


@dataclass(frozen=True)
class EnergyConfig:
    capacity_ah: float = 200.0
    reserve_soc_pct: float = 10.0  # "empty" = this SOC, not 0 %
    smoothing_s: float = 60.0


def _live(snap: SourceSnapshot, kind: type) -> Any | None:
    if snap.quality.is_live and isinstance(snap.reading, kind):
        return snap.reading
    return None


class EnergyBalance:
    def __init__(self, config: EnergyConfig) -> None:
        self._cfg = config
        self._net_avg: float | None = None
        self._last_t: float | None = None

    def reset(self) -> None:
        self._net_avg = None
        self._last_t = None

    def update(self, now: float, battery: SourceSnapshot, solar: SourceSnapshot,
               dcdc: SourceSnapshot) -> dict[str, Any]:
        b: BatteryReading | None = _live(battery, BatteryReading)
        s: SolarReading | None = _live(solar, SolarReading)
        d: DcDcReading | None = _live(dcdc, DcDcReading)

        voltage = b.voltage_v if b else None
        net_a = b.current_a if b else None
        solar_a = s.battery_current_a if s else None
        engine_a = d.output_current_a if d else None

        consumption_a = None
        if net_a is not None and solar_a is not None and engine_a is not None:
            consumption_a = max(0.0, solar_a + engine_a - net_a)

        # Smoothed net current for the estimates.
        if net_a is None:
            self.reset()
        else:
            if self._net_avg is None or self._last_t is None:
                self._net_avg = net_a
            else:
                alpha = 1.0 - math.exp(-max(0.0, now - self._last_t) / self._cfg.smoothing_s)
                self._net_avg += alpha * (net_a - self._net_avg)
            self._last_t = now

        soc = b.soc_pct if b else None
        state, minutes = "unknown", None
        if soc is not None and self._net_avg is not None:
            avg = self._net_avg
            if avg > IDLE_BAND_A:
                state = "full" if soc >= 99.5 else "charging"
                if state == "charging":
                    minutes = (100.0 - soc) / 100.0 * self._cfg.capacity_ah / avg * 60.0
            elif avg < -IDLE_BAND_A:
                state = "discharging"
                usable = max(0.0, soc - self._cfg.reserve_soc_pct)
                minutes = usable / 100.0 * self._cfg.capacity_ah / -avg * 60.0
            else:
                state = "balanced"

        def watts(amps: float | None) -> float | None:
            if amps is None or voltage is None:
                return None
            return round(amps * voltage)

        return {
            "quality": battery.quality.value,
            "simulated": battery.simulated or solar.simulated or dcdc.simulated,
            "soc_pct": soc,
            "voltage_v": voltage,
            "net_a": net_a,
            "net_w": watts(net_a),
            "solar_a": solar_a,
            "solar_w": watts(solar_a),
            "solar_quality": solar.quality.value,
            "engine_a": engine_a,
            "engine_w": watts(engine_a),
            "engine_state": d.charge_state if d else None,
            "engine_quality": dcdc.quality.value,
            "consumption_a": None if consumption_a is None else round(consumption_a, 1),
            "consumption_w": watts(consumption_a),
            "state": state,  # charging | discharging | balanced | full | unknown
            "minutes": None if minutes is None else round(minutes),
            "reserve_soc_pct": self._cfg.reserve_soc_pct,
            "capacity_ah": self._cfg.capacity_ah,
        }
