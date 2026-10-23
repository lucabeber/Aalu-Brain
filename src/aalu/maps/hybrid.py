"""GPX tracks as navigable routes: road-snapped where the track follows roads, the
original track where it leaves them (off-road), plus a road approach from the vehicle.

    track points -> map matching (Valhalla trace_attributes) -> road / off-road runs
    road run     -> trace_route: road geometry + turn instructions
    off-road run -> original points, "follow the GPX track" guidance
    vehicle      -> route to the chosen joining point of the track
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from aalu.core.geo import LatLon, Polyline, haversine_m
from aalu.services.navigation import Maneuver, NavError, PlannedRoute, Router

log = logging.getLogger(__name__)

RESAMPLE_M = 25.0  # keep one track point every ~25 m for matching
CHUNK_M = 150_000.0  # Valhalla limits a trace to 200 km: match in chunks
MIN_RUN = 4  # shorter runs of either kind are absorbed by their neighbours
OFFROAD_KMH = 12.0  # assumed speed on unmatched stretches
JOIN_M = 150.0  # closer than this to the track: no approach route needed
DETOUR_RATIO = 1.5  # snapped road longer than this x the GPX stretch: keep the GPX


@dataclass(frozen=True)
class HybridRoute(PlannedRoute):
    """PlannedRoute with a kind ("road" / "offroad") for every point."""

    kinds: list[str] = field(default_factory=list)
    road_m: float = 0.0
    offroad_m: float = 0.0


def resample(points: list[LatLon], step_m: float = RESAMPLE_M) -> list[LatLon]:
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    acc = 0.0
    for a, b in zip(points, points[1:], strict=False):
        acc += haversine_m(a, b)
        if acc >= step_m:
            out.append(b)
            acc = 0.0
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _runs(flags: list[bool]) -> list[tuple[bool, int, int]]:
    """[(on_road, start, end_inclusive)] with short runs merged into their neighbours."""
    flags = list(flags)
    changed = True
    while changed:
        changed = False
        runs = _raw_runs(flags)
        for k, (kind, a, b) in enumerate(runs):
            if b - a + 1 < MIN_RUN and len(runs) > 1 and 0 < k < len(runs) - 1:
                for i in range(a, b + 1):
                    flags[i] = not kind
                changed = True
                break
    return _raw_runs(flags)


def _raw_runs(flags: list[bool]) -> list[tuple[bool, int, int]]:
    runs: list[tuple[bool, int, int]] = []
    start = 0
    for i in range(1, len(flags) + 1):
        if i == len(flags) or flags[i] != flags[start]:
            runs.append((flags[start], start, i - 1))
            start = i
    return runs


class HybridTrack:
    """A matched GPX track, computed once; routes join it at any point."""

    def __init__(self, router, points: list[LatLon], name: str) -> None:
        if len(points) < 2:
            raise NavError("The GPX file has no track")
        self.name = name
        self._router = router  # ValhallaRouter (trace, trace_route, route) or None
        self.points = resample(points)
        self.base = self._build()

    # --- matching -----------------------------------------------------------------
    def _on_road_flags(self) -> list[bool]:
        if self._router is None or not getattr(self._router, "available", False):
            return [False] * len(self.points)  # no routing data: keep the whole track
        flags: list[bool] = []
        chunk: list[LatLon] = []
        length = 0.0
        for i, p in enumerate(self.points):
            if chunk:
                length += haversine_m(chunk[-1], p)
            chunk.append(p)
            if length >= CHUNK_M or i == len(self.points) - 1:
                flags.extend(self._match(chunk))
                chunk, length = [], 0.0
        return flags

    def _match(self, chunk: list[LatLon]) -> list[bool]:
        try:
            result = self._router.trace(chunk)
        except NavError as exc:
            log.info("GPX: map matching failed for a chunk (%s): kept as track", exc)
            return [False] * len(chunk)
        types = [m.get("type") for m in result.get("matched_points", [])]
        if len(types) != len(chunk):
            return [False] * len(chunk)
        return [t in ("matched", "interpolated") for t in types]

    def _build(self) -> HybridRoute:
        flags = self._on_road_flags()
        points: list[LatLon] = []
        kinds: list[str] = []
        maneuvers: list[Maneuver] = []
        duration = road_m = off_m = 0.0
        for on_road, a, b in _runs(flags):
            seg = self.points[a:b + 1]
            if points and seg[0] != points[-1]:
                seg = [points[-1], *seg]  # keep the line continuous between runs
            routed = None
            if on_road and len(seg) >= 2:
                try:
                    routed = self._router.trace_route(seg)
                except NavError as exc:
                    log.info("GPX: road stretch not routable (%s): kept as track", exc)
                gpx_len = Polyline(seg).length
                if routed is not None and routed.distance_m > DETOUR_RATIO * gpx_len + 50:
                    # Snapping invented a detour (track only touched a road): keep the GPX.
                    log.info("GPX: road stretch %.0f m vs track %.0f m: kept as track",
                             routed.distance_m, gpx_len)
                    routed = None
            offset = max(0, len(points) - 1)
            if routed is not None and kinds and kinds[-1] == "offroad":
                maneuvers.append(Maneuver("Back on the road.", "straight", offset, 0.0))
            if routed is not None:
                new = routed.points if not points else routed.points[1:]
                points.extend(new)
                kinds.extend(["road"] * len(new))
                for m in routed.maneuvers:
                    if m.kind in ("start", "destination") and maneuvers:
                        continue
                    if m.kind == "destination":
                        continue
                    maneuvers.append(Maneuver(m.instruction, m.kind, offset + m.begin_index,
                                              m.length_m, m.street))
                duration += routed.duration_s
                road_m += routed.distance_m
            else:
                new = seg if not points else seg[1:]
                length = Polyline(seg).length if len(seg) >= 2 else 0.0
                maneuvers.append(Maneuver("Leave the road: follow the GPX track (off-road).",
                                          "offroad", offset, length))
                points.extend(new)
                kinds.extend(["offroad"] * len(new))
                duration += length / (OFFROAD_KMH / 3.6)
                off_m += length
        if len(points) < 2:
            raise NavError("The GPX track could not be used")
        maneuvers.append(Maneuver(f"End of the track: {self.name}.", "destination",
                                  len(points) - 1, 0.0))
        total = Polyline(points).length
        return HybridRoute(points, total, duration, maneuvers, kinds, road_m, off_m)

    # --- routes for navigation -------------------------------------------------------
    def nearest_index(self, pos: LatLon, after: int = 0) -> int:
        line = Polyline(self.base.points)
        _, _, idx = line.locate(pos, hint=after, window=len(self.base.points))
        return idx

    def route_from(self, position: LatLon | None, join_index: int = 0,
                   approach: Router | None = None) -> HybridRoute:
        """The track from ``join_index`` on, with a road approach from ``position``."""
        base = self.base
        join_index = max(0, min(join_index, len(base.points) - 2))
        tail_pts = base.points[join_index:]
        tail_kinds = base.kinds[join_index:]
        tail_m = [Maneuver(m.instruction, m.kind, m.begin_index - join_index, m.length_m,
                           m.street) for m in base.maneuvers if m.begin_index >= join_index]
        ratio = Polyline(tail_pts).length / base.distance_m if base.distance_m else 1.0
        duration = base.duration_s * ratio
        join = tail_pts[0]
        if position is None or haversine_m(position, join) <= JOIN_M or approach is None:
            return HybridRoute(tail_pts, Polyline(tail_pts).length, duration, tail_m, tail_kinds,
                               base.road_m * ratio, base.offroad_m * ratio)
        to_track = approach.route(position, join)
        n = len(to_track.points)
        pts = to_track.points + tail_pts[1:]
        kinds = ["road"] * n + tail_kinds[1:]
        mans = [m for m in to_track.maneuvers if m.kind != "destination"]
        mans.append(Maneuver(f"Join the GPX track: {self.name}.", "straight", n - 1, 0.0))
        mans += [Maneuver(m.instruction, m.kind, m.begin_index + n - 1, m.length_m, m.street)
                 for m in tail_m]
        return HybridRoute(pts, Polyline(pts).length, to_track.duration_s + duration, mans, kinds,
                           to_track.distance_m + base.road_m * ratio, base.offroad_m * ratio)
