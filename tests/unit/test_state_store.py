import pytest

from aalu.core.models import BatteryReading, DataQuality
from aalu.core.state_store import Freshness, StateStore


def make_store(clock):
    return StateStore({"house_battery": Freshness(5, 15)}, clock=clock)


def test_never_received_is_disconnected(clock):
    store = make_store(clock)
    store.register("house_battery", simulated=False)
    snap = store.snapshot("house_battery")
    assert snap.quality is DataQuality.DISCONNECTED
    assert snap.reading is None and snap.age_s is None


def test_degrades_valid_to_stale_to_disconnected(clock):
    store = make_store(clock)
    store.update(BatteryReading(quality=DataQuality.VALID, soc_pct=80.0))
    assert store.snapshot("house_battery").quality is DataQuality.VALID

    clock.advance(5.1)
    assert store.refresh() == ["house_battery"]
    assert store.snapshot("house_battery").quality is DataQuality.STALE

    clock.advance(10)
    assert store.refresh() == ["house_battery"]
    assert store.snapshot("house_battery").quality is DataQuality.DISCONNECTED
    assert store.refresh() == []  # no repeated change notifications


def test_view_keeps_values_while_stale_but_drops_them_when_disconnected(clock):
    store = make_store(clock)
    store.update(BatteryReading(quality=DataQuality.VALID, soc_pct=80.0))
    clock.advance(6)
    store.refresh()
    view = store.snapshot("house_battery").view()
    assert view["quality"] == "stale" and view["soc_pct"] == 80.0

    clock.advance(10)
    store.refresh()
    view = store.snapshot("house_battery").view()
    assert view["quality"] == "disconnected"
    assert "soc_pct" not in view  # an old number can never be shown as current


def test_new_reading_restores_quality(clock):
    store = make_store(clock)
    store.update(BatteryReading(quality=DataQuality.SIMULATED, soc_pct=80.0))
    clock.advance(20)
    store.refresh()
    store.update(BatteryReading(quality=DataQuality.SIMULATED, soc_pct=79.0))
    assert store.snapshot("house_battery").quality is DataQuality.SIMULATED


def test_error_reading_shows_no_values(clock):
    store = make_store(clock)
    store.update(BatteryReading(quality=DataQuality.ERROR, soc_pct=80.0))
    assert "soc_pct" not in store.snapshot("house_battery").view()


def test_listeners_called_on_update_and_degradation(clock):
    store = make_store(clock)
    seen = []
    store.subscribe(seen.append)
    store.update(BatteryReading(quality=DataQuality.VALID))
    clock.advance(6)
    store.refresh()
    assert seen == ["house_battery", "house_battery"]


def test_freshness_validation():
    with pytest.raises(ValueError):
        Freshness(10, 5)
