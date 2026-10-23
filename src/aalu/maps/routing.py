"""Offline routing and GPX map matching with Valhalla (pyvalhalla), on map-pack tiles."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from aalu.core.geo import LatLon, decode_polyline
from aalu.maps.pack import MapPack
from aalu.services.navigation import Maneuver, NavError, PlannedRoute, RouteOptions

log = logging.getLogger(__name__)

# Valhalla maneuver type -> simple arrow kind for the UI.
_KIND = {
    1: "start", 2: "start", 3: "start", 4: "destination", 5: "destination", 6: "destination",
    7: "straight", 8: "straight", 9: "slight_right", 10: "right", 11: "sharp_right",
    12: "uturn", 13: "uturn", 14: "sharp_left", 15: "left", 16: "slight_left",
    17: "straight", 18: "slight_right", 19: "slight_left", 20: "slight_right",
    21: "slight_left", 22: "straight", 23: "slight_right", 24: "slight_left",
    25: "merge", 26: "roundabout", 27: "roundabout", 28: "ferry", 29: "ferry",
    37: "merge", 38: "merge", 39: "merge",
}


class ValhallaRouter:
    """Routes with the first pack whose area contains both ends."""

    def __init__(self, packs: list[MapPack], language: str = "en-US") -> None:
        import importlib.util

        installed = importlib.util.find_spec("valhalla") is not None
        if not installed:
            log.warning("offline routing unavailable: pyvalhalla not installed (.[maps] extra)")
        self._packs = [p for p in packs if p.has("routing")] if installed else []
        self._language = language
        self._actors: dict[str, Any] = {}
        self._lock = threading.Lock()  # Valhalla actors are not shared between threads

    @property
    def available(self) -> bool:
        return bool(self._packs)

    def _actor(self, *points: LatLon):
        pack = next((p for p in self._packs if all(p.contains(*pt) for pt in points)), None)
        if pack is None:
            raise NavError("Outside the downloaded maps: build a map pack for this area")
        if pack.name not in self._actors:
            import valhalla
            from valhalla import get_config

            cfg = get_config(tile_extract="", tile_dir=str(Path(pack.valhalla_dir).resolve()))
            self._actors[pack.name] = valhalla.Actor(cfg)
        return self._actors[pack.name]

    def route(self, start: LatLon, end: LatLon,
              options: RouteOptions | None = None) -> PlannedRoute:
        opts = options or RouteOptions()
        costing = {
            "use_highways": 0.0 if opts.avoid_motorways else 0.5,
            "use_tolls": 0.0 if opts.avoid_tolls else 0.5,
            "use_ferry": 0.0 if opts.avoid_ferries else 0.5,
            "exclude_unpaved": opts.avoid_unpaved,
        }
        query = {
            "locations": [{"lat": start[0], "lon": start[1]}, {"lat": end[0], "lon": end[1]}],
            "costing": "auto",
            "costing_options": {"auto": costing},
            "units": "kilometers",
            "directions_options": {"language": self._language},
        }
        with self._lock:
            actor = self._actor(start, end)
            try:
                result = actor.route(query)
            except Exception as exc:  # ValhallaError: no route, no road near a point...
                raise NavError(_friendly(str(exc))) from exc
        return _planned(result["trip"])

    def trace(self, points: list[LatLon]) -> dict[str, Any]:
        """Map-match a track (GPX): which points are on a road (``matched``) and which not."""
        query = {"shape": [{"lat": a, "lon": b} for a, b in points], "costing": "auto",
                 "shape_match": "map_snap",
                 "filters": {"attributes": ["matched.type", "matched.edge_index"],
                             "action": "include"}}
        with self._lock:
            actor = self._actor(points[0], points[-1])
            try:
                return actor.trace_attributes(query)
            except Exception as exc:
                raise NavError(_friendly(str(exc))) from exc

    def trace_route(self, points: list[LatLon]) -> PlannedRoute:
        """Road route that follows a track closely, with maneuvers."""
        query = {"shape": [{"lat": a, "lon": b} for a, b in points], "costing": "auto",
                 "shape_match": "map_snap", "units": "kilometers",
                 "directions_options": {"language": self._language}}
        with self._lock:
            actor = self._actor(points[0], points[-1])
            try:
                result = actor.trace_route(query)
            except Exception as exc:
                raise NavError(_friendly(str(exc))) from exc
        return _planned(result["trip"])


def _planned(trip: dict[str, Any]) -> PlannedRoute:
    points: list[LatLon] = []
    maneuvers: list[Maneuver] = []
    for leg in trip["legs"]:
        offset = max(0, len(points) - 1)
        shape = decode_polyline(leg["shape"])
        points.extend(shape if not points else shape[1:])
        for m in leg["maneuvers"]:
            if maneuvers and m.get("type") in (1, 2, 3):
                continue  # the "start" of a later leg is not a maneuver for the driver
            maneuvers.append(Maneuver(
                instruction=m.get("instruction", ""),
                kind=_KIND.get(m.get("type", 0), "straight"),
                begin_index=offset + m.get("begin_shape_index", 0),
                length_m=m.get("length", 0.0) * 1000,
                street=", ".join(m.get("street_names", [])[:1]),
            ))
    summary = trip["summary"]
    if len(points) < 2:
        raise NavError("No route found to this destination")
    return PlannedRoute(points, summary["length"] * 1000, summary["time"], maneuvers)


def _friendly(message: str) -> str:
    if "No suitable edges" in message:
        return "No road near the start or the destination"
    if "No path could be found" in message:
        return "No route found with these options"
    return "Routing failed: " + message.split(":")[-1].strip()
