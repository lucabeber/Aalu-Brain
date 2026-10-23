"""Small geodesy helpers: distances, bearings, progress along a polyline."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence

EARTH_R_M = 6_371_000.0

LatLon = tuple[float, float]


def haversine_m(a: LatLon, b: LatLon) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(min(1.0, h)))


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(y, x)) % 360.0


class Polyline:
    """Open polyline addressed by distance from its start."""

    def __init__(self, points: Sequence[LatLon]) -> None:
        if len(points) < 2:
            raise ValueError("polyline needs at least two points")
        self.points = list(points)
        self.cum = [0.0]
        for a, b in zip(self.points, self.points[1:], strict=False):
            self.cum.append(self.cum[-1] + haversine_m(a, b))
        self.length = self.cum[-1]

    def at(self, distance_m: float) -> tuple[float, float, float]:
        """(lat, lon, heading) at a distance from the start, clamped to the ends."""
        d = min(max(distance_m, 0.0), self.length)
        i = max(0, min(len(self.cum) - 2, bisect.bisect_right(self.cum, d) - 1))
        a, b = self.points[i], self.points[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        f = 0.0 if seg == 0 else (d - self.cum[i]) / seg
        return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, bearing_deg(a, b)

    def locate(self, p: LatLon, hint: int = 0, window: int = 400) -> tuple[float, float, int]:
        """Project ``p`` on the polyline: (distance along it, distance off it, segment index).

        Searches segments around ``hint`` (the previous result) so progress stays cheap and
        does not jump to another part of a route that passes the same place twice.
        """
        lo = max(0, hint - 20)
        hi = min(len(self.points) - 1, hint + window)
        best = (math.inf, 0.0, lo)
        lat0 = math.radians(p[0])
        kx = EARTH_R_M * math.cos(lat0) * math.pi / 180  # metres per degree of longitude
        ky = EARTH_R_M * math.pi / 180
        px, py = p[1] * kx, p[0] * ky
        for i in range(lo, hi):
            (alat, alon), (blat, blon) = self.points[i], self.points[i + 1]
            ax, ay, bx, by = alon * kx, alat * ky, blon * kx, blat * ky
            dx, dy = bx - ax, by - ay
            seg2 = dx * dx + dy * dy
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
            off = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if off < best[0]:
                best = (off, self.cum[i] + t * (self.cum[i + 1] - self.cum[i]), i)
        off, along, idx = best
        return along, off, idx


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    factor = 10.0 ** precision
    points: list[LatLon] = []
    index = lat = lon = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        points.append((lat / factor, lon / factor))
    return points
