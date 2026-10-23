from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from aalu.adapters.base import PolledAdapter
from aalu.adapters.scenario import Scenario
from aalu.core.geo import EARTH_R_M, Polyline
from aalu.core.models import DataQuality, GnssFix, GnssReading


class Route(Polyline):
    """Polyline the fake car drives. ``loop`` = closed circuit, else stop at the end."""

    def __init__(self, points: Sequence[tuple[float, float]], loop: bool = True) -> None:
        pts = list(points)
        if loop and len(pts) >= 2 and pts[0] != pts[-1]:
            pts.append(pts[0])
        super().__init__(pts)
        self.loop = loop

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
                lat0 + math.degrees(radius_m * math.cos(a) / EARTH_R_M),
                lon0 + math.degrees(radius_m * math.sin(a)
                                    / (EARTH_R_M * math.cos(math.radians(lat0)))),
            ))
        return cls(pts)

    def at(self, distance_m: float) -> tuple[float, float, float]:
        return super().at(distance_m % self.length if self.loop else distance_m)


class FakeGnss(PolledAdapter):
    """Drives along a recorded road loop (or a circle) while ACC is on, or along the
    current navigation route when one is set."""

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
        self._home_route = route or Route.circle((46.0679, 11.1211), 2000.0)
        self._route = self._home_route
        self._cruise = cruise_kmh
        self._distance = 0.0
        self._lock = threading.Lock()
        self._last = clock()

    def follow(self, points: Sequence[tuple[float, float]] | None) -> None:
        """Drive along a navigation route (stopping at its end); None = back to the loop.

        Called from the GUI thread when a destination is chosen, so the simulated car
        actually drives to it."""
        with self._lock:
            if points is None:
                self._route, self._distance = self._home_route, 0.0
            else:
                self._route, self._distance = Route(points, loop=False), 0.0

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
        with self._lock:
            route = self._route
            if not route.loop and self._distance >= route.length:
                speed = 0.0  # arrived: parked at the destination
            self._distance = max(0.0, self._distance + direction * (speed / 3.6) * dt)
            lat, lon, heading = route.at(self._distance)
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
