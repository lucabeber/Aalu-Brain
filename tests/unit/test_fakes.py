import pytest

from aalu.adapters.audio.fake import FakePhone
from aalu.adapters.gps.fake import FakeGnss
from aalu.adapters.mcu.fake import FakeMcu
from aalu.adapters.scenario import Scenario
from aalu.adapters.victron.fake import FakeVictron
from aalu.core.models import DataQuality, GnssFix, PhoneLink, PlaybackStatus


def test_fake_gnss_fix_no_fix_and_disconnect(clock):
    sc = Scenario()
    gnss = FakeGnss(sc, clock=clock)
    clock.advance(1)
    r = gnss.read()
    assert r.quality is DataQuality.SIMULATED and r.fix is GnssFix.FIX_3D
    assert 40 < r.speed_kmh < 80

    sc.gnss_fix = False
    r = gnss.read()
    assert r.fix is GnssFix.NO_FIX and r.lat is None and r.speed_kmh is None

    sc.gnss_connected = False
    assert gnss.read() is None


def test_fake_gnss_parked_when_acc_off(clock):
    sc = Scenario(acc_on=False)
    gnss = FakeGnss(sc, clock=clock)
    a = gnss.read()
    clock.advance(10)
    b = gnss.read()
    assert b.speed_kmh == 0 and (a.lat, a.lon) == (b.lat, b.lon)


def test_fake_victron_low_soc_and_disconnect(clock):
    sc = Scenario()
    victron = FakeVictron(sc, clock=clock)
    battery, solar, dcdc = victron.read()
    assert (battery.source, solar.source, dcdc.source) == ("house_battery", "solar", "dcdc")
    sc.low_soc = True
    battery, _, _ = victron.read()
    assert battery.soc_pct == 15.0
    sc.victron_connected = False
    assert victron.read() is None


def test_fake_mcu_confirms_load_after_delay(clock):
    sc = Scenario()
    mcu = FakeMcu(sc, clock=clock, confirm_delay_s=0.4)
    mcu.request("water_pump", True)
    loads = mcu.read()[-1]
    assert loads.outputs["water_pump"] is False  # requested, not yet confirmed
    clock.advance(0.5)
    loads = mcu.read()[-1]
    assert loads.outputs["water_pump"] is True


def test_fake_mcu_disconnected_drops_requests(clock):
    sc = Scenario(mcu_connected=False)
    mcu = FakeMcu(sc, clock=clock)
    mcu.request("light_living", True)
    assert mcu.read() is None
    sc.mcu_connected = True
    clock.advance(1)
    assert mcu.read()[-1].outputs["light_living"] is False


def test_fake_mcu_reverse_requires_acc(clock):
    sc = Scenario(acc_on=False, reverse=True)
    inputs = FakeMcu(sc, clock=clock).read()[0]
    assert inputs.reverse is False


def test_fake_phone_controls(clock):
    sc = Scenario()
    phone = FakePhone(sc, clock=clock)
    first = phone.read()
    assert first.link is PhoneLink.CONNECTED and first.status is PlaybackStatus.PLAYING
    phone.pause()
    assert phone.read().status is PlaybackStatus.PAUSED
    phone.next()
    assert phone.read().title != first.title
    clock.advance(10)
    phone.play()
    phone.read()
    phone.previous()  # >3 s into the track: restart it
    assert phone.read().position_ms == 0

    sc.phone_connected = False
    r = phone.read()
    assert r.link is PhoneLink.DISCONNECTED and r.title is None


def test_fake_victron_balance_follows_engine_sun_and_loads(clock):
    sc = Scenario()
    extra = {"a": 0.0}
    victron = FakeVictron(sc, clock=clock, extra_load_a=lambda: extra["a"])
    battery, solar, dcdc = victron.read()
    assert dcdc.output_current_a > 0 and solar.battery_current_a > 0
    # Net current is exactly what the shunt would see.
    consumption = solar.battery_current_a + dcdc.output_current_a - battery.current_a
    assert consumption > 0

    sc.engine_running = False
    sc.sunny = False
    battery, solar, dcdc = victron.read()
    assert dcdc.output_current_a == 0 and dcdc.charge_state == "off"
    assert battery.current_a < 0  # discharging

    before = battery.current_a
    extra["a"] = 5.0
    battery, _, _ = victron.read()
    assert battery.current_a == pytest.approx(before - 5.0, abs=0.2)


def test_fake_mcu_reports_confirmed_load_current(clock):
    mcu = FakeMcu(Scenario(), clock=clock, confirm_delay_s=0)
    assert mcu.confirmed_load_a() == 0
    mcu.request("water_pump", True)
    mcu.read()
    assert mcu.confirmed_load_a() == pytest.approx(4.5)


def test_route_loop_interpolation_and_heading():
    from aalu.adapters.gps.fake import Route

    route = Route([(46.0, 11.0), (46.001, 11.0), (46.001, 11.001)])
    assert route.points[0] == route.points[-1]  # closed
    lat, lon, heading = route.at(route.cum[1] / 2)
    assert lat == pytest.approx(46.0005) and lon == pytest.approx(11.0)
    assert heading == pytest.approx(0.0, abs=0.5)  # northbound
    assert route.at(route.length + 1)[:2] == pytest.approx(route.at(1)[:2])  # loops


def test_sample_route_loads_and_fake_gnss_follows_it(clock):
    from aalu.adapters.gps.fake import Route
    from conftest import ROOT

    route = Route.load(ROOT / "assets" / "sample-data" / "route_trento.json")
    assert 20_000 < route.length < 30_000
    gnss = FakeGnss(Scenario(), clock=clock, route=route)
    a = gnss.read()
    clock.advance(10)
    b = gnss.read()
    assert (a.lat, a.lon) != (b.lat, b.lon)


def test_reverse_moves_backwards_slowly(clock):
    sc = Scenario(reverse=True)
    gnss = FakeGnss(sc, clock=clock)
    clock.advance(1)
    assert gnss.read().speed_kmh == 4.0


def test_fake_gnss_follows_navigation_route_and_stops_at_the_end(clock):
    gnss = FakeGnss(Scenario(), clock=clock)
    gnss.follow([(46.0, 11.0), (46.001, 11.0)])  # ~111 m
    clock.advance(1)
    first = gnss.read()
    assert first.lat == pytest.approx(46.0, abs=0.0005)
    clock.advance(60)
    end = gnss.read()
    clock.advance(1)
    parked = gnss.read()
    assert end.lat == pytest.approx(46.001) and parked.speed_kmh == 0
    gnss.follow(None)  # back to the home loop
    clock.advance(1)
    assert gnss.read().lat != pytest.approx(46.001)
