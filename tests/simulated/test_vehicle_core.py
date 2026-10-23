"""Roadmap §7 failure cases, driven through VehicleCore with fake adapters.

Adapters are not started (no threads): each step reads them by hand and
feeds the readings, with a manually advanced clock.
"""

import pytest

from aalu.core.models import DataQuality, GnssFix, GnssReading
from aalu.core.modes import VehicleMode
from aalu.services.config import load_config
from aalu.services.vehicle_core import LOAD_CONFIRM_TIMEOUT_S, VehicleCore
from conftest import ROOT


@pytest.fixture
def core(clock, tmp_path):
    import dataclasses

    cfg = load_config(ROOT / "config" / "dev.toml")
    # Isolated from this machine: no downloaded map packs, trips in a temp folder.
    cfg = dataclasses.replace(
        cfg, trips_dir=str(tmp_path / "trips"), gpx_dir=str(tmp_path / "gpx"),
        map=dataclasses.replace(cfg.map, maps_dir=str(tmp_path / "maps")))
    return VehicleCore(cfg, clock=clock)


def step(core, clock, seconds=1.0):
    clock.advance(seconds)
    for adapter in core.adapters:
        if adapter.simulated:  # skip the real system-health adapter
            result = adapter.read()
            for reading in result if isinstance(result, list) else [result] if result else []:
                core.ingest(reading)
    core.tick()


def quality(core, source):
    return core.store.snapshot(source).quality


def test_boot_with_acc_goes_to_drive(core, clock):
    assert core.modes.mode is VehicleMode.STANDBY
    step(core, clock)
    assert core.modes.mode is VehicleMode.DRIVE


def test_boot_without_acc_goes_to_camp_then_follows_acc(core, clock):
    core.scenario.acc_on = False
    step(core, clock)
    assert core.modes.mode is VehicleMode.CAMP
    core.scenario.acc_on = True
    step(core, clock)
    assert core.modes.mode is VehicleMode.DRIVE
    core.scenario.acc_on = False
    step(core, clock)
    assert core.modes.mode is VehicleMode.CAMP


def test_gnss_without_fix_never_invents_position(core, clock):
    core.scenario.gnss_fix = False
    step(core, clock)
    view = core.store.snapshot("gnss").view()
    assert view["fix"] == "no_fix"
    assert view["lat"] is None and view["speed_kmh"] is None
    assert core.drive_locked  # unknown speed in DRIVE: settings stay locked


def test_victron_disconnect_goes_stale_then_disconnected_with_notice(core, clock):
    step(core, clock)
    assert quality(core, "house_battery") is DataQuality.SIMULATED
    core.scenario.victron_connected = False
    for _ in range(6):
        step(core, clock)
    assert quality(core, "house_battery") is DataQuality.STALE
    assert "soc_pct" in core.store.snapshot("house_battery").view()
    for _ in range(15):
        step(core, clock)
    assert quality(core, "house_battery") is DataQuality.DISCONNECTED
    assert "soc_pct" not in core.store.snapshot("house_battery").view()
    assert "house_battery.unavailable" in [a.id for a in core.alarms.active]


def test_low_soc_raises_alarm(core, clock):
    core.scenario.low_soc = True
    step(core, clock)
    assert "battery.soc_low" in [a.id for a in core.alarms.active]


def test_reverse_requires_live_inputs(core, clock):
    core.scenario.reverse = True
    step(core, clock)
    assert core.reverse_active
    core.scenario.mcu_connected = False
    for _ in range(2):
        step(core, clock)
    # Inputs are stale: no longer trusted as "reverse engaged".
    assert not core.reverse_active


def test_phone_disconnected_disables_player(core, clock):
    core.scenario.phone_connected = False
    step(core, clock)
    view = core.store.snapshot("media").view()
    assert view["link"] == "disconnected" and view["title"] is None


def test_load_request_confirmed_by_mcu(core, clock):
    core.scenario.acc_on = False
    step(core, clock)
    assert core.request_load("light_living", True)
    assert core.loads_view()["outputs"]["light_living"] == {
        "on": False, "pending": True, "requested": True,
    }
    step(core, clock, 0.5)
    assert core.loads_view()["outputs"]["light_living"]["on"] is True
    assert core.loads_view()["outputs"]["light_living"]["pending"] is False


def test_load_commands_refused_without_mcu(core, clock):
    step(core, clock)
    core.scenario.mcu_connected = False
    for _ in range(3):
        step(core, clock)
    assert not core.loads_available()
    assert core.request_load("water_pump", True) is False


def test_unconfirmed_request_expires(core, clock):
    step(core, clock)
    assert core.request_load("water_pump", True)
    core.scenario.mcu_connected = False  # request lost on the wire
    step(core, clock, LOAD_CONFIRM_TIMEOUT_S + 0.5)
    assert core.loads_view()["outputs"]["water_pump"]["pending"] is False
    assert any("not confirmed" in text for _, text in core.events)


def test_drive_lock_released_when_parked(core, clock):
    step(core, clock)
    assert core.drive_locked
    core.scenario.acc_on = False
    step(core, clock)
    assert core.modes.mode is VehicleMode.CAMP and not core.drive_locked


def test_source_missing_since_boot_raises_notice_after_timeout(core, clock):
    core.scenario.victron_connected = False
    step(core, clock)
    assert "house_battery.unavailable" not in [a.id for a in core.alarms.active]  # boot grace
    for _ in range(20):
        step(core, clock)
    assert "house_battery.unavailable" in [a.id for a in core.alarms.active]


def test_energy_view_combines_battery_solar_engine(core, clock):
    step(core, clock)
    e = core.energy_view
    assert e["solar_w"] > 0 and e["engine_w"] > 0 and e["consumption_w"] > 0
    assert e["state"] == "charging" and e["minutes"] > 0
    assert e["net_w"] == pytest.approx(e["solar_w"] + e["engine_w"] - e["consumption_w"], abs=2)


def test_energy_view_discharging_estimate_and_switched_loads(core, clock):
    core.scenario.acc_on = False
    core.scenario.sunny = False
    step(core, clock)
    e1 = core.energy_view
    assert e1["state"] == "discharging" and e1["engine_w"] == 0
    assert core.request_load("water_pump", True)
    step(core, clock, 0.5)
    step(core, clock)
    assert core.energy_view["consumption_a"] > e1["consumption_a"] + 4


def test_energy_view_without_victron_has_no_numbers(core, clock):
    core.scenario.victron_connected = False
    for _ in range(25):
        step(core, clock)
    e = core.energy_view
    assert e["soc_pct"] is None and e["consumption_w"] is None and e["minutes"] is None
    assert e["state"] == "unknown" and e["quality"] == "disconnected"


def test_save_clip_windows_and_unavailable_service(core, clock):
    calls = []

    class FakeVideo:
        def protect(self, before_s=None, after_s=None):
            calls.append((before_s, after_s))
            return True

    core.video = FakeVideo()
    assert core.protect_clip() and core.protect_clip(long=True)
    assert calls == [(60, 60), (300, 600)]
    assert "last 5 min + next 10 min" in core.events[0][1]
    core.video = None
    assert core.protect_clip(long=True) is False
    assert "NOT saved" in core.events[0][1]


def test_destination_typing_blocked_while_driving(core, clock):
    step(core, clock)
    assert core.drive_locked
    assert core.search_destination("Riva") is False
    assert "blocked while driving" in core.events[0][1]


def test_trip_recorded_from_start_to_arrival(core, clock, tmp_path):
    from aalu.services.navigation import Place, PlannedRoute

    step(core, clock)
    here = core.position()
    end = (here[0] + 0.002, here[1])
    route = PlannedRoute([here, end], 222.0, 30.0)
    core.navigation.load_route(route, Place("Testplace", "", *end), None, here)
    assert core.trips.recording
    for lat in (here[0] + 0.0005, here[0] + 0.001, here[0] + 0.0015, end[0]):
        core._fake_gnss.follow(None)  # keep the fake car from moving on its own
        core.ingest(GnssReading(quality=DataQuality.SIMULATED, fix=GnssFix.FIX_3D,
                                lat=lat, lon=here[1], speed_kmh=30.0))
        clock.advance(11)
    assert core.navigation.state == "arrived" and not core.trips.recording
    (trip,) = core.trips_view()
    assert trip["status"] == "completed" and trip["destination"]["name"] == "Testplace"
    assert 150 < trip["driven"]["distance_m"] < 260
    folder = tmp_path / "trips" / trip["id"]
    assert (folder / "track.gpx").exists() and (folder / "route.gpx").exists()
    assert trip["id"].endswith("Testplace")


def test_planned_trip_saved_and_driven_again(core, clock):
    from aalu.services.navigation import Place, PlannedRoute

    step(core, clock)
    here = core.position()
    route = PlannedRoute([(46.0, 11.0), (46.01, 11.0)], 1112.0, 120.0)
    core.navigation.load_route(route, Place("Far", "", 46.01, 11.0), Place("Away", "", 46.0, 11.0),
                               here)
    assert core.navigation.state == "preview" and not core.trips.recording
    assert core.save_planned_trip()
    (trip,) = core.trips_view()
    assert trip["status"] == "planned" and trip["start"]["name"] == "Away"
    calls = []
    core.navigation._plan = lambda start: calls.append(start)  # no routing engine in this test
    assert core.drive_trip(trip["id"])
    assert calls == [here] and core.navigation.destination.name == "Far"
