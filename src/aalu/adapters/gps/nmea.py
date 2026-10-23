"""NMEA 0183 parsing and fix logic (GNSS-01).

Rules (roadmap §3, §4 phase 4, §7):
- Sentences with a bad or missing checksum are rejected.
- RMC status ``V``, GGA quality ``0`` or GSA mode ``1`` mean *no fix*: no
  position, speed or heading is reported, even if the receiver sends numbers.
- Receiver time is reported only with a valid fix (no invented 1980 dates).
- Implausible values (out-of-range coordinates, speed > MAX_SPEED_KMH) drop the
  position for that cycle instead of passing it to the dashboard.

Any talker ID is accepted (GP, GN, GL, GA, GB, BD...).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from aalu.core.models import DataQuality, GnssFix, GnssReading

log = logging.getLogger(__name__)

KNOT_TO_KMH = 1.852
MAX_SPEED_KMH = 250.0
MIN_PLAUSIBLE_YEAR = 2024


def checksum_ok(sentence: str) -> bool:
    sentence = sentence.strip()
    if not sentence.startswith("$") or "*" not in sentence:
        return False
    body, _, given = sentence[1:].rpartition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(given[:2], 16)
    except ValueError:
        return False


def _float(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _int(value: str) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _coord(value: str, hemi: str, degree_digits: int) -> float | None:
    """ddmm.mmmm / dddmm.mmmm -> signed decimal degrees."""
    if not value or hemi not in ("N", "S", "E", "W") or len(value) < degree_digits + 2:
        return None
    try:
        deg = int(value[:degree_digits])
        minutes = float(value[degree_digits:])
    except ValueError:
        return None
    if minutes >= 60:
        return None
    result = deg + minutes / 60.0
    return -result if hemi in ("S", "W") else result


@dataclass
class _Cycle:
    """Everything learnt from the sentences of one receiver epoch."""

    rmc_valid: bool | None = None
    gga_quality: int | None = None
    gsa_mode: int | None = None
    satellites: int | None = None
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    speed_kmh: float | None = None
    heading_deg: float | None = None
    hdop: float | None = None
    time_utc: datetime | None = None
    seen: set[str] = field(default_factory=set)


_CYCLE_KEYS = ("RMC", "GGA")  # sent exactly once per epoch; GSA may repeat per constellation


class NmeaAccumulator:
    """Feed lines with :meth:`feed`; one reading is returned per receiver epoch.

    Receivers disagree on sentence order (u-blox starts with RMC, others end
    with it), so an epoch is closed when RMC or GGA *repeats*. This works for
    any order at the cost of up to one epoch of latency (1 s at 1 Hz).
    """

    def __init__(self, source: str = "gnss") -> None:
        self._source = source
        self._cycle = _Cycle()
        self.rejected = 0

    def feed(self, line: str) -> GnssReading | None:
        line = line.strip()
        if not line:
            return None
        if not checksum_ok(line):
            self.rejected += 1
            log.debug("NMEA rejected (checksum): %r", line)
            return None
        body = line[1:].rpartition("*")[0]
        parts = body.split(",")
        kind = parts[0][2:] if len(parts[0]) == 5 else parts[0]
        handler = {"RMC": self._rmc, "GGA": self._gga, "GSA": self._gsa}.get(kind)
        if handler is None:
            return None
        reading = None
        if kind in _CYCLE_KEYS and kind in self._cycle.seen:
            reading = self._build()
            self._cycle = _Cycle()
        try:
            handler(parts)
        except IndexError:
            self.rejected += 1
            log.debug("NMEA rejected (short): %r", line)
        return reading

    # --- sentence handlers -----------------------------------------------
    def _rmc(self, p: list[str]) -> None:
        # $--RMC,hhmmss.ss,A,llll.ll,a,yyyyy.yy,a,x.x,x.x,ddmmyy,x.x,a[,a]*hh
        c = self._cycle
        c.seen.add("RMC")
        c.rmc_valid = p[2] == "A"
        if len(p) > 12 and p[12] == "N":  # NMEA 2.3+ mode indicator: data not valid
            c.rmc_valid = False
        if not c.rmc_valid:
            return
        lat, lon = _coord(p[3], p[4], 2), _coord(p[5], p[6], 3)
        if lat is not None and lon is not None:
            c.lat, c.lon = lat, lon
        knots = _float(p[7])
        c.speed_kmh = None if knots is None else knots * KNOT_TO_KMH
        c.heading_deg = _float(p[8])
        c.time_utc = _rmc_time(p[1], p[9])

    def _gga(self, p: list[str]) -> None:
        # $--GGA,hhmmss.ss,llll.ll,a,yyyyy.yy,a,q,ss,h.h,alt,M,...*hh
        c = self._cycle
        c.seen.add("GGA")
        c.gga_quality = _int(p[6])
        c.satellites = _int(p[7])
        c.hdop = _float(p[8])
        if c.gga_quality:
            c.alt_m = _float(p[9])
            if c.lat is None or c.lon is None:  # RMC preferred when both present
                c.lat = _coord(p[2], p[3], 2)
                c.lon = _coord(p[4], p[5], 3)

    def _gsa(self, p: list[str]) -> None:
        # $--GSA,a,x,...  x: 1 = no fix, 2 = 2D, 3 = 3D. Several GSA per epoch on
        # multi-constellation receivers: keep the best.
        c = self._cycle
        c.seen.add("GSA")
        mode = _int(p[2])
        if mode is not None:
            c.gsa_mode = max(mode, c.gsa_mode or 0)

    # --- fix logic -------------------------------------------------------
    def _build(self) -> GnssReading:
        c = self._cycle
        says_fix = c.rmc_valid is True or bool(c.gga_quality)
        says_no_fix = c.rmc_valid is False or c.gga_quality == 0 or c.gsa_mode == 1
        has_fix = says_fix and not says_no_fix
        satellites = c.satellites
        if not has_fix:
            return GnssReading(
                source=self._source, quality=DataQuality.VALID, fix=GnssFix.NO_FIX,
                satellites=satellites,
            )

        plausible = (
            c.lat is not None and c.lon is not None
            and -90 <= c.lat <= 90 and -180 <= c.lon <= 180
            and not (c.lat == 0 and c.lon == 0)
            and (c.speed_kmh is None or 0 <= c.speed_kmh <= MAX_SPEED_KMH)
        )
        if not plausible:
            log.warning("GNSS: implausible fix dropped (lat=%s lon=%s v=%s)",
                        c.lat, c.lon, c.speed_kmh)
            return GnssReading(source=self._source, quality=DataQuality.VALID,
                               fix=GnssFix.NO_FIX, satellites=satellites)

        fix = GnssFix.FIX_2D if c.gsa_mode == 2 else GnssFix.FIX_3D
        assert c.lat is not None and c.lon is not None  # narrowed by `plausible`
        return GnssReading(
            source=self._source,
            quality=DataQuality.VALID,
            fix=fix,
            satellites=satellites,
            lat=round(c.lat, 7),
            lon=round(c.lon, 7),
            alt_m=c.alt_m if fix is GnssFix.FIX_3D else None,
            speed_kmh=None if c.speed_kmh is None else round(c.speed_kmh, 1),
            heading_deg=c.heading_deg,
            hdop=c.hdop,
            gnss_time_utc=c.time_utc,
        )


def _rmc_time(hhmmss: str, ddmmyy: str) -> datetime | None:
    if len(hhmmss) < 6 or len(ddmmyy) != 6:
        return None
    try:
        sec = float(hhmmss[4:])
        yy = int(ddmmyy[4:6])
        dt = datetime(
            # NMEA pivot: 80-99 = 19xx. A receiver after a GPS week rollover reports
            # 1980 dates, which must be rejected below, not read as 2080.
            (1900 if yy >= 80 else 2000) + yy, int(ddmmyy[2:4]), int(ddmmyy[0:2]),
            int(hhmmss[0:2]), int(hhmmss[2:4]), int(sec), int((sec % 1) * 1e6), tzinfo=UTC,
        )
    except ValueError:
        return None
    return dt if dt.year >= MIN_PLAUSIBLE_YEAR else None
