"""Destination search and route guidance for the dashboard map.

Geocoding and routing sit behind small interfaces. The current implementations
use public OpenStreetMap services (Nominatim, OSRM demo server), so they need
Internet; OSM Scout Server can provide both offline later (same interfaces).

Usage policies respected: a real User-Agent, at most one Nominatim request per
second, search only on explicit submit (no search-as-you-type).

Threading: network calls run in a worker thread; results are handed back with
``post(fn)``, which the owner runs on its own thread (the Qt bridge queues it to
the GUI thread). Tests pass a synchronous executor and ``post``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from aalu.core.geo import LatLon, Polyline, haversine_m

log = logging.getLogger(__name__)

OFF_ROUTE_M = 60.0  # farther than this from the route ...
OFF_ROUTE_FIXES = 3  # ... for this many fixes in a row -> recalculate
ARRIVAL_M = 40.0
DUPLICATE_M = 3000.0  # same name within this distance = same place

FetchJson = Callable[[str, dict[str, str], float], Any]


class NavError(Exception):
    """Message is shown to the user as is."""


def http_fetch_json(url: str, headers: dict[str, str], timeout: float) -> Any:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise NavError(f"Service error ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NavError("No Internet connection: search and routing need it for now") from exc
    except ValueError as exc:
        raise NavError("Unexpected answer from the service") from exc


@dataclass(frozen=True)
class Place:
    name: str
    detail: str
    lat: float
    lon: float
    kind: str = ""


@dataclass(frozen=True)
class Maneuver:
    instruction: str  # "Turn left onto Via Roma."
    kind: str  # e.g. "left", "right", "roundabout", "destination" (for the arrow icon)
    begin_index: int  # index in PlannedRoute.points where the maneuver happens
    length_m: float  # distance of the stretch after the maneuver
    street: str = ""


@dataclass(frozen=True)
class RouteOptions:
    avoid_motorways: bool = False
    avoid_tolls: bool = False
    avoid_ferries: bool = False
    avoid_unpaved: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {"avoid_motorways": self.avoid_motorways, "avoid_tolls": self.avoid_tolls,
                "avoid_ferries": self.avoid_ferries, "avoid_unpaved": self.avoid_unpaved}


@dataclass(frozen=True)
class PlannedRoute:
    points: list[LatLon]
    distance_m: float
    duration_s: float
    maneuvers: list[Maneuver] = field(default_factory=list)


class Geocoder(Protocol):
    def search(self, query: str, near: LatLon | None, limit: int) -> list[Place]: ...


class Router(Protocol):
    def route(self, start: LatLon, end: LatLon,
              options: RouteOptions | None = None) -> PlannedRoute: ...


class NominatimGeocoder:
    MIN_INTERVAL_S = 1.1

    def __init__(self, url: str, user_agent: str, fetch: FetchJson = http_fetch_json,
                 language: str = "en", timeout: float = 10.0) -> None:
        self._url = url.rstrip("/")
        self._headers = {"User-Agent": user_agent}
        self._fetch = fetch
        self._language = language
        self._timeout = timeout
        self._lock = threading.Lock()
        self._last = 0.0

    def search(self, query: str, near: LatLon | None, limit: int = 8) -> list[Place]:
        params: dict[str, Any] = {"q": query, "format": "jsonv2", "limit": limit,
                                  "addressdetails": 0, "accept-language": self._language}
        if near is not None:
            lat, lon = near
            # Prefer results around the vehicle without excluding the rest of the world.
            params["viewbox"] = f"{lon - 0.7},{lat + 0.5},{lon + 0.7},{lat - 0.5}"
            params["bounded"] = 0
        with self._lock:  # one request per second at most (Nominatim usage policy)
            wait = self.MIN_INTERVAL_S - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        data = self._fetch(f"{self._url}/search?{urllib.parse.urlencode(params)}",
                           self._headers, self._timeout)
        places: list[Place] = []
        for item in data if isinstance(data, list) else []:
            try:
                full = str(item.get("display_name", ""))
                name = item.get("name") or full.split(",")[0]
                detail = ", ".join(p.strip() for p in full.split(",")[1:4])
                place = Place(name, detail, float(item["lat"]), float(item["lon"]),
                              str(item.get("type", "")))
            except (KeyError, TypeError, ValueError):
                continue
            # The same town often comes back as node + boundary: keep the first only.
            if not any(p.name == place.name and haversine_m((p.lat, p.lon), (place.lat, place.lon))
                       < DUPLICATE_M for p in places):
                places.append(place)
        return places


class OsrmRouter:
    def __init__(self, url: str, user_agent: str, fetch: FetchJson = http_fetch_json,
                 timeout: float = 15.0) -> None:
        self._url = url.rstrip("/")
        self._headers = {"User-Agent": user_agent}
        self._fetch = fetch
        self._timeout = timeout

    def route(self, start: LatLon, end: LatLon,
              options: RouteOptions | None = None) -> PlannedRoute:
        coords = f"{start[1]:.6f},{start[0]:.6f};{end[1]:.6f},{end[0]:.6f}"
        exclude = []
        if options:  # OSRM car profile supports these exclusion classes (not "unpaved")
            exclude = [c for c, on in (("motorway", options.avoid_motorways),
                                       ("toll", options.avoid_tolls),
                                       ("ferry", options.avoid_ferries)) if on]
        extra = f"&exclude={','.join(exclude)}" if exclude else ""
        data = self._fetch(f"{self._url}/route/v1/driving/{coords}"
                           "?overview=full&geometries=geojson&alternatives=false&steps=false"
                           + extra, self._headers, self._timeout)
        if not isinstance(data, dict) or data.get("code") != "Ok" or not data.get("routes"):
            raise NavError("No route found to this destination")
        r = data["routes"][0]
        points = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
        if len(points) < 2:
            raise NavError("No route found to this destination")
        return PlannedRoute(points, float(r["distance"]), float(r["duration"]))


class FallbackGeocoder:
    """Try each geocoder in order (offline first); the first answer with results wins."""

    def __init__(self, geocoders: list[Geocoder]) -> None:
        self._geocoders = geocoders

    def search(self, query: str, near: LatLon | None, limit: int = 8) -> list[Place]:
        error: NavError | None = None
        for g in self._geocoders:
            try:
                places = g.search(query, near, limit)
            except NavError as exc:
                error = exc
                continue
            if places:
                return places
        if error is not None:
            raise error
        return []


class FallbackRouter:
    """Try each router in order (offline first) until one finds a route."""

    def __init__(self, routers: list[Router]) -> None:
        self._routers = routers

    def route(self, start: LatLon, end: LatLon, options: RouteOptions | None = None
              ) -> PlannedRoute:
        error: NavError = NavError("No routing available")
        for r in self._routers:
            try:
                return r.route(start, end, options)
            except NavError as exc:
                error = exc
        raise error


class NavigationController:
    """Start/destination selection, route planning, progress and guidance.

    Route states: none | routing | preview (planned from another start, not followed) |
    active (navigating from the vehicle) | arrived | error.
    """

    def __init__(self, geocoder: Geocoder, router: Router,
                 post: Callable[[Callable[[], None]], None] = lambda fn: fn(),
                 executor: Executor | None = None,
                 on_route: Callable[[list[LatLon] | None], None] = lambda pts: None) -> None:
        self._geocoder = geocoder
        self._router = router
        self.post = post
        self._executor = executor or ThreadPoolExecutor(max_workers=1,
                                                        thread_name_prefix="navigation")
        self._on_route = on_route  # e.g. let the simulated car follow the route
        self._listeners: list[Callable[[], None]] = []
        self._token = 0
        self._search: dict[str, Any] = {"state": "idle", "query": "", "results": [],
                                        "error": None, "target": "destination"}
        self._results: list[Place] = []
        self.start_place: Place | None = None  # None = current vehicle position
        self.destination: Place | None = None
        self.options = RouteOptions()
        self._route: PlannedRoute | None = None
        self._line: Polyline | None = None
        self._route_state = "none"
        self._route_error: str | None = None
        self._progress: dict[str, Any] = {}
        self._hint = 0
        self._off_count = 0
        self._last_pos: LatLon | None = None
        self.route_id = 0  # changes whenever a new route geometry is available
        self.planned_from: LatLon | None = None
        self.track: Any = None  # HybridTrack when following a GPX file
        self.track_source: str | None = None  # GPX file path, saved with the trip
        self._track_join = 0

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    @property
    def state(self) -> str:
        return self._route_state

    @property
    def route(self) -> PlannedRoute | None:
        return self._route

    # --- search ---------------------------------------------------------------
    def search(self, query: str, near: LatLon | None, target: str = "destination") -> None:
        query = query.strip()
        if not query:
            return
        self._token += 1
        token = self._token
        target = "start" if target == "start" else "destination"
        self._search = {"state": "searching", "query": query, "results": [], "error": None,
                        "target": target}
        self._changed()

        def job() -> None:
            try:
                places, error = self._geocoder.search(query, near, 8), None
            except NavError as exc:
                places, error = [], str(exc)
            except Exception:  # never let a parsing bug kill the worker silently
                log.exception("search failed")
                places, error = [], "Search failed"
            self.post(lambda: self._search_done(token, query, near, target, places, error))

        self._executor.submit(job)

    def clear_search(self) -> None:
        self._search = {"state": "idle", "query": "", "results": [], "error": None,
                        "target": self._search.get("target", "destination")}
        self._results = []
        self._changed()

    # --- start / destination / options ---------------------------------------
    def choose(self, index: int, position: LatLon | None) -> None:
        """Use search result ``index`` for the field the search was made for."""
        if not 0 <= index < len(self._results):
            return
        self.set_point(self._search.get("target", "destination"), self._results[index], position)

    def set_point(self, target: str, place: Place | None, position: LatLon | None) -> None:
        if target == "start":
            self.start_place = place
        else:
            self.destination = place
        self._replan(position)

    def set_options(self, options: RouteOptions, position: LatLon | None) -> None:
        self.options = options
        self._replan(position)

    def start_navigation(self, position: LatLon | None) -> None:
        """From a preview: drive the destination from where the vehicle is now."""
        self.start_place = None
        self._replan(position)

    def follow_track(self, track: Any, destination: Place, source: str,
                     position: LatLon | None, preview: bool) -> None:
        """Navigate a matched GPX track (see aalu.maps.hybrid.HybridTrack)."""
        self.track, self.track_source, self._track_join = track, source, 0
        self.destination = destination
        self.start_place = destination if preview else None  # preview: not from the car
        if preview or position is None:
            self._token += 1
            route = track.route_from(None, 0)
            self._route_done(self._token, route.points[0], True, route, None)
        else:
            self._plan(position)

    def cancel(self) -> None:
        self._token += 1
        self.destination = self._route = self._line = None
        self.start_place = None
        self.track = self.track_source = None
        self.route_id += 1
        self._route_state, self._route_error, self._progress = "none", None, {}
        self._on_route(None)
        self._changed()

    def _replan(self, position: LatLon | None) -> None:
        if self.destination is None:
            self._changed()
            return
        start = ((self.start_place.lat, self.start_place.lon) if self.start_place
                 else position)
        if start is None:
            self._route_state, self._route_error = "error", "No GPS position: choose a start"
            self._changed()
            return
        self._plan(start)

    # --- progress ---------------------------------------------------------------
    def update_position(self, pos: LatLon | None) -> None:
        """Feed every GNSS fix (None = no fix). Updates progress, re-routes, detects arrival."""
        self._last_pos = pos
        if self._route_state != "active" or pos is None:
            return
        if self._line is None or self._route is None:
            return
        along, off, self._hint = self._line.locate(pos, self._hint)
        remaining = max(0.0, self._line.length - along)
        dest = self.destination
        to_dest = haversine_m(pos, (dest.lat, dest.lon)) if dest else remaining
        if to_dest <= ARRIVAL_M or remaining <= ARRIVAL_M:
            self._route_state = "arrived"
            self._progress = {"remaining_m": 0, "remaining_s": 0, "off_route": False,
                              "next": None}
            self._changed()
            return
        self._off_count = self._off_count + 1 if off > OFF_ROUTE_M else 0
        ratio = remaining / self._line.length if self._line.length else 0.0
        self._progress = {
            "remaining_m": round(remaining),
            "remaining_s": round(self._route.duration_s * ratio),
            "off_route": self._off_count > 0,
            "next": self._next_maneuver(along),
        }
        if self._off_count >= OFF_ROUTE_FIXES:
            log.info("navigation: off route by %.0f m, recalculating", off)
            self._off_count = 0
            if self.track is not None:
                # Back to the GPX track at the nearest point ahead, not straight to the end.
                self._track_join = self.track.nearest_index(pos, self._track_join)
            self._plan(pos)
        else:
            self._changed()

    # --- view for the UI --------------------------------------------------------
    def view(self) -> dict[str, Any]:
        def place(p: Place | None) -> dict[str, Any] | None:
            return None if p is None else {"name": p.name, "detail": p.detail,
                                           "lat": p.lat, "lon": p.lon}

        track = None
        if self.track is not None and self._route is not None:
            track = {"name": self.track.name, "file": self.track_source,
                     "road_m": round(getattr(self._route, "road_m", 0.0)),
                     "offroad_m": round(getattr(self._route, "offroad_m", 0.0))}
        return {
            "search": dict(self._search),
            "start": None if self.track is not None else place(self.start_place),
            "options": self.options.as_dict(),
            "track": track,
            "route": {
                "state": self._route_state,
                "error": self._route_error,
                "destination": place(self.destination),
                "distance_m": None if self._route is None else round(self._route.distance_m),
                "duration_s": None if self._route is None else round(self._route.duration_s),
                "route_id": self.route_id,
                **self._progress,
            },
        }

    def _next_maneuver(self, along: float) -> dict[str, Any] | None:
        """The next maneuver ahead of the vehicle and the distance to it."""
        if self._route is None or self._line is None:
            return None
        cum = self._line.cum
        for m in self._route.maneuvers:
            at = cum[min(m.begin_index, len(cum) - 1)]
            if at > along + 5:
                return {"instruction": m.instruction, "kind": m.kind, "street": m.street,
                        "distance_m": round(at - along)}
        return None

    def path(self) -> list[dict[str, Any]]:
        """Route geometry for the map; fetch it only when ``route_id`` changes."""
        if self._route is None:
            return []
        kinds = getattr(self._route, "kinds", None)
        return [{"lat": lat, "lon": lon, "kind": kinds[i] if kinds else "road"}
                for i, (lat, lon) in enumerate(self._route.points)]

    # --- internals ------------------------------------------------------------
    def _plan(self, start: LatLon) -> None:
        dest = self.destination
        assert dest is not None
        self._token += 1
        token = self._token
        preview = self.start_place is not None
        self._route_state, self._route_error = "routing", None
        self._changed()
        options = self.options

        track, join = self.track, self._track_join

        def job() -> None:
            try:
                if track is not None:
                    route, error = track.route_from(start, join, self._router), None
                else:
                    route, error = self._router.route(start, (dest.lat, dest.lon), options), None
            except NavError as exc:
                route, error = None, str(exc)
            except Exception:
                log.exception("routing failed")
                route, error = None, "Routing failed"
            self.post(lambda: self._route_done(token, start, preview, route, error))

        self._executor.submit(job)

    def _search_done(self, token: int, query: str, near: LatLon | None, target: str,
                     places: list[Place], error: str | None) -> None:
        if token != self._token:
            return  # superseded by a newer search or a route request
        self._results = places
        rows = []
        for p in places:
            dist = None if near is None else round(haversine_m(near, (p.lat, p.lon)))
            rows.append({"name": p.name, "detail": p.detail, "kind": p.kind,
                         "lat": p.lat, "lon": p.lon, "distance_m": dist})
        state = "error" if error else ("done" if places else "empty")
        self._search = {"state": state, "query": query, "results": rows, "error": error,
                        "target": target}
        self._changed()

    def load_route(self, route: PlannedRoute, destination: Place,
                   start: Place | None, position: LatLon | None) -> None:
        """Use an already computed route (saved trip, GPX track) instead of planning one."""
        self._token += 1
        self.destination, self.start_place = destination, start
        first = route.points[0]
        preview = start is not None and (position is None or haversine_m(position, first) > 300)
        self._route_done(self._token, first, preview, route, None)

    def _route_done(self, token: int, start: LatLon, preview: bool,
                    route: PlannedRoute | None, error: str | None) -> None:
        if token != self._token:
            return
        if route is None:
            self._route_state, self._route_error = "error", error
        else:
            self._route, self._line = route, Polyline(route.points)
            self.route_id += 1
            self.planned_from = start
            self._hint, self._off_count = 0, 0
            self._route_state = "preview" if preview else "active"
            self._progress = {"remaining_m": round(route.distance_m),
                              "remaining_s": round(route.duration_s), "off_route": False,
                              "next": self._next_maneuver(0.0)}
            if not preview:
                self._on_route(route.points)
            log.info("navigation: %s %.1f km, %.0f min to %s", self._route_state,
                     route.distance_m / 1000, route.duration_s / 60,
                     self.destination.name if self.destination else "?")
        self._changed()

    def _changed(self) -> None:
        for listener in self._listeners:
            listener()
