import pytest

from aalu.core.alarms import AlarmEngine, Severity, ThresholdRule
from aalu.core.models import BatteryReading, DataQuality
from aalu.core.state_store import SourceSnapshot

RULE = ThresholdRule(
    id="soc_low", source="house_battery", field="soc_pct", direction="below",
    set_at=20, clear_at=25, severity=Severity.WARNING, message="low",
)


def snap(soc, quality=DataQuality.VALID):
    reading = BatteryReading(quality=quality, soc_pct=soc)
    return SourceSnapshot("house_battery", reading, quality, 0.0, False)


def ids(engine):
    return [a.id for a in engine.active]


def test_hysteresis():
    e = AlarmEngine([RULE], {})
    e.evaluate(snap(21))
    assert ids(e) == []
    assert e.evaluate(snap(20)) is True
    assert ids(e) == ["soc_low"]
    e.evaluate(snap(23))  # inside the hysteresis band: stays active
    assert ids(e) == ["soc_low"]
    e.evaluate(snap(25))
    assert ids(e) == []


def test_stale_data_neither_trips_nor_clears():
    e = AlarmEngine([RULE], {})
    e.evaluate(snap(10, DataQuality.STALE))
    assert ids(e) == []
    e.evaluate(snap(10))
    e.evaluate(snap(90, DataQuality.STALE))
    assert ids(e) == ["soc_low"]


def test_unavailable_notice_for_watched_source():
    e = AlarmEngine([], {"house_battery": "House battery"})
    e.evaluate(SourceSnapshot("house_battery", None, DataQuality.DISCONNECTED, None, False))
    assert e.active[0].id == "house_battery.unavailable"
    assert e.active[0].severity is Severity.INFO
    assert e.active[0].message == "House battery: no data"
    e.evaluate(snap(80))
    assert ids(e) == []


def test_sorted_by_severity():
    crit = ThresholdRule("soc_crit", "house_battery", "soc_pct", "below", 10, 15,
                         Severity.CRITICAL, "crit")
    e = AlarmEngine([RULE, crit], {})
    e.evaluate(snap(5))
    assert ids(e) == ["soc_crit", "soc_low"]


def test_rule_validation():
    with pytest.raises(ValueError):
        ThresholdRule("x", "s", "f", "below", 20, 15, Severity.INFO, "m")
    with pytest.raises(ValueError):
        ThresholdRule("x", "s", "f", "above", 80, 85, Severity.INFO, "m")
