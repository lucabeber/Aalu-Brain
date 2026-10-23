from __future__ import annotations

import math
import time
from collections.abc import Callable

from aalu.adapters.base import PolledAdapter
from aalu.adapters.scenario import Scenario
from aalu.core.models import BatteryReading, DataQuality, DcDcReading, Reading, SolarReading

BASE_LOAD_A = 1.8          # Pi, screens, inverter standby, parasitic loads
FRIDGE_A = 4.5             # compressor fridge, cycling
DCDC_MAX_A = 30.0          # e.g. Orion XS 12/12-50 limited to 30 A
SOLAR_PEAK_W = 400.0


class FakeVictron(PolledAdapter):
    """SmartShunt + MPPT + Orion DC-DC. SOC is integrated from the net current.

    ``extra_load_a`` returns the current of the loads switched on from the UI
    (lights, pump), so toggling them visibly changes the energy balance.
    ``time_scale`` speeds up SOC changes for demos; currents stay realistic.
    """

    sources = ("house_battery", "solar", "dcdc")
    simulated = True
    interval_s = 1.0

    def __init__(
        self,
        scenario: Scenario,
        clock: Callable[[], float] = time.monotonic,
        capacity_ah: float = 200.0,
        initial_soc_pct: float = 78.0,
        time_scale: float = 1.0,
        extra_load_a: Callable[[], float] = lambda: 0.0,
    ) -> None:
        super().__init__()
        self._scenario = scenario
        self._clock = clock
        self._capacity = capacity_ah
        self._soc = initial_soc_pct
        self._scale = time_scale
        self._extra_load_a = extra_load_a
        self._yield_kwh = 0.0
        self._t0 = clock()
        self._last = self._t0

    def read(self) -> list[Reading] | None:
        now = self._clock()
        t = now - self._t0
        dt_h = (now - self._last) * self._scale / 3600.0
        self._last = now
        sc = self._scenario
        if not sc.victron_connected:
            return None

        battery_v = 12.8 + 0.8 * self._soc / 100.0  # resting voltage, LiFePO4-like

        # Chargers taper when the battery is nearly full.
        taper = 1.0 if self._soc < 95 else max(0.03, (100.0 - self._soc) / 5.0)

        clouds = 0.85 + 0.15 * math.sin(t / 23.0)
        pv_w = SOLAR_PEAK_W * 0.8 * clouds * taper if sc.sunny else 6.0
        solar_a = pv_w * 0.96 / battery_v

        engine = sc.engine_running and sc.acc_on
        dcdc_a = DCDC_MAX_A * taper if engine else 0.0

        fridge_on = (t % 600) < 240  # 40 % duty cycle
        load_a = BASE_LOAD_A + (FRIDGE_A if fridge_on else 0.0) + self._extra_load_a()
        net_a = solar_a + dcdc_a - load_a

        self._soc = min(100.0, max(0.0, self._soc + net_a * dt_h / self._capacity * 100.0))
        self._yield_kwh += pv_w * dt_h / 1000.0
        soc = 15.0 if sc.low_soc else self._soc
        voltage = battery_v + net_a * 0.008  # internal resistance

        battery = BatteryReading(
            quality=DataQuality.SIMULATED,
            voltage_v=round(voltage, 2),
            current_a=round(net_a, 1),
            power_w=round(voltage * net_a),
            soc_pct=round(soc, 1),
            consumed_ah=round((100.0 - soc) / 100.0 * self._capacity, 1),
        )
        solar = SolarReading(
            quality=DataQuality.SIMULATED,
            pv_power_w=round(pv_w),
            pv_voltage_v=round(36.0 + 4.0 * clouds, 1) if pv_w > 10 else 0.0,
            battery_current_a=round(solar_a, 1),
            yield_today_kwh=round(self._yield_kwh, 2),
            charge_state=("float" if taper < 0.2 else "bulk") if pv_w > 10 else "off",
        )
        dcdc = DcDcReading(
            quality=DataQuality.SIMULATED,
            input_voltage_v=14.1 if engine else 12.6,
            output_voltage_v=round(voltage, 2),
            output_current_a=round(dcdc_a, 1),
            charge_state=("float" if taper < 0.2 else "bulk") if engine else "off",
        )
        return [battery, solar, dcdc]
