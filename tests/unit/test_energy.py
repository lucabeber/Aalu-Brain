import pytest

from aalu.core.models import BatteryReading, DataQuality, DcDcReading, SolarReading
from aalu.core.state_store import SourceSnapshot
from aalu.services.energy import EnergyBalance, EnergyConfig

LIVE = DataQuality.VALID


def snaps(net_a, soc=50.0, solar_a=10.0, engine_a=0.0, quality=LIVE, solar_quality=LIVE):
    def snap(source, reading, q):
        return SourceSnapshot(source, reading, q, 0.0, False)
    return (
        snap("house_battery", BatteryReading(quality=quality, voltage_v=13.0, current_a=net_a,
                                             soc_pct=soc), quality),
        snap("solar", SolarReading(quality=solar_quality, battery_current_a=solar_a),
             solar_quality),
        snap("dcdc", DcDcReading(quality=LIVE, output_current_a=engine_a,
                                 charge_state="bulk" if engine_a else "off"), LIVE),
    )


def balance(**cfg):
    return EnergyBalance(EnergyConfig(capacity_ah=200, reserve_soc_pct=10, **cfg))


def test_charging_time_to_full():
    e = balance().update(0, *snaps(net_a=10.0, soc=50.0, solar_a=8.0, engine_a=6.0))
    assert e["state"] == "charging"
    assert e["minutes"] == pytest.approx(0.5 * 200 / 10 * 60)  # 10 h
    assert e["consumption_a"] == pytest.approx(4.0)
    assert e["solar_w"] == 104 and e["engine_w"] == 78 and e["consumption_w"] == 52
    assert e["net_w"] == 130


def test_discharging_time_to_reserve():
    e = balance().update(0, *snaps(net_a=-4.0, soc=50.0, solar_a=0.0))
    assert e["state"] == "discharging"
    assert e["minutes"] == pytest.approx(0.40 * 200 / 4 * 60)  # 50 % -> 10 % reserve = 20 h


def test_balanced_and_full_have_no_estimate():
    assert balance().update(0, *snaps(net_a=0.2))["state"] == "balanced"
    e = balance().update(0, *snaps(net_a=2.0, soc=100.0))
    assert e["state"] == "full" and e["minutes"] is None


def test_estimate_is_smoothed():
    b = balance(smoothing_s=60)
    b.update(0, *snaps(net_a=-4.0))
    e = b.update(1, *snaps(net_a=-8.0))  # fridge just switched on
    avg = -4.0 + (1 - 2.718281828 ** (-1 / 60)) * (-4.0)
    assert e["net_a"] == -8.0  # instantaneous value shown as is
    assert e["minutes"] == pytest.approx(0.40 * 200 / -avg * 60, rel=1e-3)


def test_consumption_unknown_when_a_source_is_missing():
    e = balance().update(0, *snaps(net_a=-4.0, solar_quality=DataQuality.DISCONNECTED))
    assert e["consumption_a"] is None and e["solar_w"] is None
    assert e["state"] == "discharging"  # still known from the shunt alone


def test_stale_battery_gives_no_numbers():
    e = balance().update(0, *snaps(net_a=-4.0, quality=DataQuality.STALE))
    assert e["soc_pct"] is None and e["minutes"] is None and e["state"] == "unknown"
