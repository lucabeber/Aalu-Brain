from datetime import UTC, datetime

from aalu.core.models import BatteryReading, DataQuality, GnssFix, GnssReading


def test_contract_envelope_matches_roadmap_example():
    r = GnssReading(
        quality=DataQuality.VALID, ts_utc=datetime(2026, 10, 23, 12, tzinfo=UTC),
        fix=GnssFix.FIX_3D, speed_kmh=73.4, lat=46.0, lon=11.0, heading_deg=285.0,
    )
    d = r.to_dict()
    assert d["schema_version"] == 1
    assert d["source"] == "gnss"
    assert d["ts_utc"] == "2026-10-23T12:00:00Z"
    assert d["quality"] == "valid"
    assert d["fix"] == "3d"
    assert d["speed_kmh"] == 73.4


def test_unknown_values_are_none_not_zero():
    r = BatteryReading(quality=DataQuality.STALE)
    assert r.to_dict()["soc_pct"] is None
    assert r.to_dict()["voltage_v"] is None


def test_measured_fields_exclude_envelope():
    fields = BatteryReading(quality=DataQuality.VALID, soc_pct=50.0).measured_fields()
    assert "quality" not in fields and "source" not in fields
    assert fields["soc_pct"] == 50.0


def test_live_qualities():
    assert DataQuality.VALID.is_live and DataQuality.SIMULATED.is_live
    assert not DataQuality.STALE.is_live
    assert not DataQuality.DISCONNECTED.is_live
    assert not DataQuality.ERROR.is_live
