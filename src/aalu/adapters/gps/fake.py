from __future__ import annotations

import bisect
import json
import math
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from aalu.adapters.base import PolledAdapter
from aalu.adapters.scenario import Scenario
from aalu.core.models import DataQuality, GnssFix, GnssReading

_EARTH_R_M = 6_371_000.0


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R_M * math.asin(math.sqrt(h))


def _bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = (math.radians(v) for v in a), (math.radians(v) for v in b)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(y, x)) % 360.0


class Route:
    """Closed polyline of (lat, lon) points, addressed by distance along it."""

    def __init__(self, points: Sequence[tuple[float, float]]) -> None:
        if len(points) < 2:
            raise ValueError("route needs at least two points")
        pts = list(points)
        if pts[0] != pts[-1]:
            pts.append(pts[0])  # loop
        self.points = pts
        self.cum = [0.0]
        for a, b in zip(pts, pts[1:], strict=False):
            self.cum.append(self.cum[-1] + _haversine_m(a, b))
        self.length = self.cum[-1]

    @classmethod
    def load(cls, path: str | Path) -> Route:
        data = json.loads(Path(path).read_text())
        return cls([(lat, lon) for lon, lat in data["lon_lat"]])

    @classmethod
    def circle(cls, center: tuple[float, float], radius_m: float, n: int = 72) -> Route:
        lat0, lon0 = center
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            pts.append((
                lat0 + math.degrees(radius_m * math.cos(a) / _EARTH_R_M),
                lon0 + math.degrees(radius_m * math.sin(a)
                                    / (_EARTH_R_M * math.cos(math.radians(lat0)))),
            ))
        return cls(pts)

    def at(self, distance_m: float) -> tuple[float, float, float]:
        """(lat, lon, heading) at a distance along the loop."""
        d = distance_m % self.length
        i = max(0, min(len(self.cum) - 2, bisect.bisect_right(self.cum, d) - 1))
        a, b = self.points[i], self.points[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        f = 0.0 if seg == 0 else (d - self.cum[i]) / seg
        lat = a[0] + (b[0] - a[0]) * f
        lon = a[1] + (b[1] - a[1]) * f
        return lat, lon, _bearing_deg(a, b)


class FakeGnss(PolledAdapter):
    """Drives along a recorded road loop (or a circle) while ACC is on."""

    sources = ("gnss",)
    simulated = True
    interval_s = 1.0

    def __init__(
        self,
        scenario: Scenario,
        clock: Callable[[], float] = time.monotonic,
        route: Route | None = None,
        cruise_kmh: float = 55.0,
    ) -> None:
        super().__init__()
        self._scenario = scenario
        self._clock = clock
        self._route = route or Route.circle((46.0679, 11.1211), 2000.0)
        self._cruise = cruise_kmh
        self._distance = 0.0
        self._last = clock()

    def read(self) -> GnssReading | None:
        now = self._clock()
        dt, self._last = now - self._last, now
        sc = self._scenario
        if not sc.gnss_connected:
            return None
        if not sc.gnss_fix:
            return GnssReading(quality=DataQuality.SIMULATED, fix=GnssFix.NO_FIX, satellites=0)

        if sc.reverse and sc.acc_on:
            speed, direction = 4.0, -1.0
        elif sc.acc_on:
            speed, direction = self._cruise + 10.0 * math.sin(now / 20.0), 1.0
        else:
            speed, direction = 0.0, 1.0
        self._distance += direction * (speed / 3.6) * dt
        lat, lon, heading = self._route.at(self._distance)
        return GnssReading(
            quality=DataQuality.SIMULATED,
            fix=GnssFix.FIX_3D,
            satellites=11,
            lat=round(lat, 6),
            lon=round(lon, 6),
            alt_m=194.0,
            speed_kmh=round(speed, 1),
            heading_deg=round(heading, 1),  # direction of the road, also when reversing
            hdop=0.9,
        )
