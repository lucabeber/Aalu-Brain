from functools import reduce

import pytest

from aalu.adapters.gps.nmea import NmeaAccumulator, checksum_ok
from aalu.core.models import GnssFix
from conftest import FIXTURES


def sentence(body: str) -> str:
    return f"${body}*{reduce(lambda a, c: a ^ ord(c), body, 0):02X}"


def run(lines):
    acc = NmeaAccumulator()
    readings = [r for r in (acc.feed(line) for line in lines) if r is not None]
    return acc, readings


def run_file(name):
    return run((FIXTURES / "nmea" / name).read_text().splitlines())


def test_checksum():
    good = sentence("GPGGA,,,,,,0,00,99.99,,,,,,")
    assert checksum_ok(good)
    assert not checksum_ok(good[:-2] + "00")
    assert not checksum_ok("GPGGA,no,dollar*00")
    assert not checksum_ok("$GPGGA,no,star")


def test_no_fix_log_never_reports_a_position():
    """Receiver indoors at 115200 baud: sentences arrive, but status V / 0 satellites."""
    acc, readings = run_file("no_fix_indoor.nmea")
    assert len(readings) >= 5
    for r in readings:
        assert r.fix is GnssFix.NO_FIX
        assert r.lat is None and r.lon is None
        assert r.speed_kmh is None and r.heading_deg is None
        assert r.gnss_time_utc is None  # no invented date
        assert r.satellites in (0, None)
    assert acc.rejected == 0


def test_fix_log_ublox_order():
    _, readings = run_file("drive_fix.nmea")
    # 5 epochs, the last one is still open (closed by the next RMC): 4 readings.
    assert len(readings) == 4
    first = readings[0]
    assert first.fix is GnssFix.FIX_3D
    assert first.satellites == 9  # from the GGA of the *same* epoch
    assert first.lat == pytest.approx(46 + 4.0740 / 60, abs=1e-6)
    assert first.lon == pytest.approx(11 + 7.2660 / 60, abs=1e-6)
    assert first.speed_kmh == pytest.approx(32.4 * 1.852, abs=0.1)
    assert first.alt_m == pytest.approx(194.3)
    assert first.gnss_time_utc.isoformat() == "2026-10-23T13:00:00+00:00"
    assert readings[1].lat > readings[0].lat  # moving north, epochs not mixed


def test_rmc_last_order_also_grouped_correctly():
    lines = []
    for i, sats in enumerate((7, 8, 9)):
        t = f"1400{i:02d}.00"
        lines += [
            sentence(f"GPGGA,{t},4604.0000,N,01107.0000,E,1,{sats:02d},1.0,200.0,M,,M,,"),
            sentence("GPGSA,A,3,01,02,03,04,,,,,,,,,1.5,1.0,1.1"),
            sentence(f"GPRMC,{t},A,4604.0000,N,01107.0000,E,0.0,,231026,,,A"),
        ]
    _, readings = run(lines)
    assert [r.satellites for r in readings] == [7, 8]


def test_valid_rmc_contradicted_by_gga_quality_zero_is_no_fix():
    _, readings = run([
        sentence("GPRMC,120000.00,A,4604.0000,N,01107.0000,E,0.0,,231026,,,A"),
        sentence("GPGGA,120000.00,4604.0000,N,01107.0000,E,0,00,,,M,,M,,"),
        sentence("GPRMC,120001.00,A,4604.0000,N,01107.0000,E,0.0,,231026,,,A"),
    ])
    assert readings[0].fix is GnssFix.NO_FIX and readings[0].lat is None


def test_2d_fix_has_no_altitude():
    _, readings = run([
        sentence("GPRMC,120000.00,A,4604.0000,N,01107.0000,E,10.0,90.0,231026,,,A"),
        sentence("GPGGA,120000.00,4604.0000,N,01107.0000,E,1,04,2.5,210.0,M,,M,,"),
        sentence("GPGSA,A,2,01,02,03,04,,,,,,,,,2.7,2.5,1.0"),
        sentence("GPRMC,120001.00,A,4604.0000,N,01107.0000,E,10.0,90.0,231026,,,A"),
    ])
    assert readings[0].fix is GnssFix.FIX_2D
    assert readings[0].alt_m is None
    assert readings[0].lat is not None


def test_implausible_speed_is_dropped():
    _, readings = run([
        sentence("GPRMC,120000.00,A,4604.0000,N,01107.0000,E,999.0,90.0,231026,,,A"),
        sentence("GPRMC,120001.00,A,4604.0000,N,01107.0000,E,10.0,90.0,231026,,,A"),
    ])
    assert readings[0].fix is GnssFix.NO_FIX and readings[0].lat is None


def test_1980_receiver_date_not_reported():
    _, readings = run([
        sentence("GPRMC,000012.00,A,4604.0000,N,01107.0000,E,0.0,,060180,,,A"),
        sentence("GPRMC,000013.00,A,4604.0000,N,01107.0000,E,0.0,,060180,,,A"),
    ])
    assert readings[0].lat is not None
    assert readings[0].gnss_time_utc is None


def test_gga_only_receiver():
    _, readings = run([
        sentence("GPGGA,120000.00,4604.0000,S,01107.0000,W,1,06,1.1,20.0,M,,M,,"),
        sentence("GPGGA,120001.00,4604.0000,S,01107.0000,W,1,06,1.1,20.0,M,,M,,"),
    ])
    assert readings[0].fix is GnssFix.FIX_3D
    assert readings[0].lat == pytest.approx(-(46 + 4 / 60))
    assert readings[0].lon == pytest.approx(-(11 + 7 / 60))
    assert readings[0].speed_kmh is None


def test_garbage_and_truncated_lines_are_counted_not_raised():
    acc, readings = run([
        "", "garbage", "$GPRMC,1*00", sentence("GPRMC,1"), "\x00\xff$GPGGA",
    ])
    assert readings == []
    assert acc.rejected == 4
