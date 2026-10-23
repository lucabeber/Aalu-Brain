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
from dataclasses import dataclass
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
class PlannedRoute:
    points: list[LatLon]
    distance_m: float
    duration_s: float


class Geocoder(Protocol):
    def search(self, query: str, near: LatLon | None, limit: int) -> list[Place]: ...


class Router(Protocol):
    def route(self, start: LatLon, end: LatLon) -> PlannedRoute: ...


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

    def route(self, start: LatLon, end: LatLon) -> PlannedRoute:
        coords = f"{start[1]:.6f},{start[0]:.6f};{end[1]:.6f},{end[0]:.6f}"
        data = self._fetch(f"{self._url}/route/v1/driving/{coords}"
                           "?overview=full&geometries=geojson&alternatives=false&steps=false",
                           self._headers, self._timeout)
        if not isinstance(data, dict) or data.get("code") != "Ok" or not data.get("routes"):
            raise NavError("No route found to this destination")
        r = data["routes"][0]
        points = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
        if len(points) < 2:
            raise NavError("No route found to this destination")
        return PlannedRoute(points, float(r["distance"]), float(r["duration"]))


class NavigationController:
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
                                        "error": None}
        self._results: list[Place] = []
        self._destination: Place | None = None
        self._route: PlannedRoute | None = None
        self._line: Polyline | None = None
        self._route_state = "none"  # none | routing | active | arrived | error
        self._route_error: str | None = None
        self._progress: dict[str, Any] = {}
        self._hint = 0
        self._off_count = 0
        self._last_pos: LatLon | None = None
        self.route_id = 0  # changes whenever a new route geometry is available

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    # --- commands (owner thread) -------------------------------------------
    def search(self, query: str, near: LatLon | None) -> None:
        query = query.strip()
        if not query:
            return
        self._token += 1
        token = self._token
        self._search = {"state": "searching", "query": query, "results": [], "error": None}
        self._changed()

        def job() -> None:
            try:
                places, error = self._geocoder.search(query, near, 8), None
            except NavError as exc:
                places, error = [], str(exc)
            except Exception:  # never let a parsing bug kill the worker silently
                log.exception("search failed")
                places, error = [], "Search failed"
            self.post(lambda: self._search_done(token, query, near, places, error))

        self._executor.submit(job)

    def choose(self, index: int, start: LatLon | None) -> None:
        if not 0 <= index < len(self._results):
            return
        if start is None:
            self._route_state, self._route_error = "error", "No GPS position: cannot plan a route"
            self._changed()
            return
        self._destination = self._results[index]
        self._plan(start)

    def cancel(self) -> None:
        self._token += 1
        self._destination = self._route = self._line = None
        self.route_id += 1
        self._route_state, self._route_error, self._progress = "none", None, {}
        self._on_route(None)
        self._changed()

    def clear_search(self) -> None:
        self._search = {"state": "idle", "query": "", "results": [], "error": None}
        self._results = []
        self._changed()

    def update_position(self, pos: LatLon | None) -> None:
        """Feed every GNSS fix (None = no fix). Updates progress, re-routes, detects arrival."""
        self._last_pos = pos
        if self._route_state != "active" or pos is None:
            return
        if self._line is None or self._route is None:
            return
        along, off, self._hint = self._line.locate(pos, self._hint)
        remaining = max(0.0, self._line.length - along)
        dest = self._destination
        to_dest = haversine_m(pos, (dest.lat, dest.lon)) if dest else remaining
        if to_dest <= ARRIVAL_M or remaining <= ARRIVAL_M:
            self._route_state = "arrived"
            self._progress = {"remaining_m": 0, "remaining_s": 0, "off_route": False}
            self._changed()
            return
        self._off_count = self._off_count + 1 if off > OFF_ROUTE_M else 0
        ratio = remaining / self._line.length if self._line.length else 0.0
        self._progress = {
            "remaining_m": round(remaining),
            "remaining_s": round(self._route.duration_s * ratio),
            "off_route": self._off_count > 0,
        }
        if self._off_count >= OFF_ROUTE_FIXES:
            log.info("navigation: off route by %.0f m, recalculating", off)
            self._off_count = 0
            self._plan(pos)
        else:
            self._changed()

    # --- view for the UI ----------------------------------------------------
    def view(self) -> dict[str, Any]:
        dest = self._destination
        return {
            "search": dict(self._search),
            "route": {
                "state": self._route_state,
                "error": self._route_error,
                "destination": None if dest is None else {
                    "name": dest.name, "detail": dest.detail, "lat": dest.lat, "lon": dest.lon},
                "distance_m": None if self._route is None else round(self._route.distance_m),
                "duration_s": None if self._route is None else round(self._route.duration_s),
                "route_id": self.route_id,
                **self._progress,
            },
        }

    def path(self) -> list[dict[str, float]]:
        """Route geometry for the map; fetch it only when ``route_id`` changes."""
        if self._route is None:
            return []
        return [{"lat": lat, "lon": lon} for lat, lon in self._route.points]

    # --- internals ------------------------------------------------------------
    def _plan(self, start: LatLon) -> None:
        dest = self._destination
        assert dest is not None
        self._token += 1
        token = self._token
        self._route_state, self._route_error = "routing", None
        self._changed()

        def job() -> None:
            try:
                route, error = self._router.route(start, (dest.lat, dest.lon)), None
            except NavError as exc:
                route, error = None, str(exc)
            except Exception:
                log.exception("routing failed")
                route, error = None, "Routing failed"
            self.post(lambda: self._route_done(token, route, error))

        self._executor.submit(job)

    def _search_done(self, token: int, query: str, near: LatLon | None,
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
        self._search = {"state": state, "query": query, "results": rows, "error": error}
        self._changed()

    def _route_done(self, token: int, route: PlannedRoute | None, error: str | None) -> None:
        if token != self._token:
            return
        if route is None:
            self._route_state, self._route_error = "error", error
        else:
            self._route, self._line = route, Polyline(route.points)
            self.route_id += 1
            self._route_state, self._hint, self._off_count = "active", 0, 0
            self._progress = {"remaining_m": round(route.distance_m),
                              "remaining_s": round(route.duration_s), "off_route": False}
            self._on_route(route.points)
            log.info("navigation: %.1f km, %.0f min to %s", route.distance_m / 1000,
                     route.duration_s / 60, self._destination.name if self._destination else "?")
        self._changed()

    def _changed(self) -> None:
        for listener in self._listeners:
            listener()
