"""Saved trips: one folder per trip, named by date, time, start and destination.

    <trips_dir>/2026-10-23_16-40_Trento-Lago-di-Tovel/
        trip.json   metadata: start, destination, options, planned and driven figures
        route.gpx   the planned route
        track.gpx   what was actually driven (rewritten every 30 s while driving)

A trip is "planned" (saved from a preview), "driving", "completed" (arrived),
"cancelled" or "interrupted" (power lost while driving; found on next start).
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aalu.core.geo import LatLon, haversine_m
from aalu.maps.gpx import GpxPoint, write_gpx

log = logging.getLogger(__name__)

MIN_STEP_M = 15.0  # record a point when moved this far ...
MIN_STEP_S = 10.0  # ... or this much time passed
FLUSH_S = 30.0  # rewrite track.gpx this often while driving
VALID_YEAR = 2024


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-")[:40] or "place"


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat(timespec="seconds")


@dataclass
class _Recording:
    folder: Path
    meta: dict[str, Any]
    points: list[GpxPoint] = field(default_factory=list)
    last: LatLon | None = None
    last_t: float = 0.0
    last_flush: float = 0.0
    distance_m: float = 0.0
    max_speed: float = 0.0
    started_mono: float = 0.0


class TripStore:
    def __init__(self, root: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.root = root
        self._clock = clock
        self._rec: _Recording | None = None
        self.root.mkdir(parents=True, exist_ok=True)
        self._mark_interrupted()

    @property
    def recording(self) -> bool:
        return self._rec is not None

    # --- creating ---------------------------------------------------------------
    def _new_folder(self, start_name: str, dest_name: str) -> Path:
        now = _now()
        stamp = now.strftime("%Y-%m-%d_%H-%M") if now.year >= VALID_YEAR else "noclock"
        base = f"{stamp}_{_slug(start_name)}-{_slug(dest_name)}"
        folder, n = self.root / base, 1
        while folder.exists():
            folder, n = self.root / f"{base}_{n}", n + 1
        folder.mkdir(parents=True)
        return folder

    def _base_meta(self, start: dict[str, Any], destination: dict[str, Any],
                   options: dict[str, bool], route_points: list[LatLon],
                   distance_m: float, duration_s: float, source: str | None) -> dict[str, Any]:
        return {
            "name": f"{start['name']} → {destination['name']}",
            "created": _iso(_now()),
            "start": start, "destination": destination, "options": options,
            "planned": {"distance_m": round(distance_m), "duration_s": round(duration_s)},
            "source": source,  # e.g. the GPX file this trip came from
        }

    def save_planned(self, start: dict[str, Any], destination: dict[str, Any],
                     options: dict[str, bool], route_points: list[LatLon], distance_m: float,
                     duration_s: float, source: str | None = None) -> Path:
        folder = self._new_folder(start["name"], destination["name"])
        meta = self._base_meta(start, destination, options, route_points, distance_m,
                               duration_s, source)
        meta["status"] = "planned"
        self._write_route(folder, meta["name"], route_points, start, destination)
        self._write_meta(folder, meta)
        log.info("trip planned: %s", folder.name)
        return folder

    def start(self, start: dict[str, Any], destination: dict[str, Any],
              options: dict[str, bool], route_points: list[LatLon], distance_m: float,
              duration_s: float, source: str | None = None) -> Path:
        if self._rec is not None:
            self.finish("changed")
        folder = self._new_folder(start["name"], destination["name"])
        meta = self._base_meta(start, destination, options, route_points, distance_m,
                               duration_s, source)
        meta.update({"status": "driving", "driven": {"started": _iso(_now())}})
        self._write_route(folder, meta["name"], route_points, start, destination)
        self._write_meta(folder, meta)
        self._rec = _Recording(folder, meta, started_mono=self._clock())
        log.info("trip started: %s", folder.name)
        return folder

    def add_point(self, lat: float, lon: float, speed_kmh: float | None,
                  ele: float | None = None) -> None:
        rec = self._rec
        if rec is None:
            return
        now = self._clock()
        if rec.last is not None:
            step = haversine_m(rec.last, (lat, lon))
            if step < MIN_STEP_M and now - rec.last_t < MIN_STEP_S:
                return
            if step < 2000:  # ignore jumps (GPS glitch, simulation restart)
                rec.distance_m += step
        rec.points.append(GpxPoint(lat, lon, ele, datetime.now(UTC)))
        rec.last, rec.last_t = (lat, lon), now
        if speed_kmh is not None:
            rec.max_speed = max(rec.max_speed, speed_kmh)
        if now - rec.last_flush >= FLUSH_S:
            self._flush(rec)

    def update_route(self, route_points: list[LatLon], distance_m: float,
                     duration_s: float) -> None:
        """After a recalculation: keep the planned route file current."""
        rec = self._rec
        if rec is None:
            return
        rec.meta["planned"] = {"distance_m": round(distance_m), "duration_s": round(duration_s)}
        rec.meta["recalculations"] = rec.meta.get("recalculations", 0) + 1
        self._write_route(rec.folder, rec.meta["name"], route_points, rec.meta["start"],
                          rec.meta["destination"])

    def finish(self, status: str) -> Path | None:
        rec, self._rec = self._rec, None
        if rec is None:
            return None
        rec.meta["status"] = status
        self._flush(rec, final=True)
        log.info("trip %s: %s (%.1f km)", status, rec.folder.name, rec.distance_m / 1000)
        return rec.folder

    # --- reading ------------------------------------------------------------------
    def list(self) -> list[dict[str, Any]]:
        trips = []
        for folder in sorted(self.root.iterdir(), reverse=True):
            meta_file = folder / "trip.json"
            if not meta_file.is_file():
                continue
            try:
                meta = json.loads(meta_file.read_text())
            except (OSError, ValueError):
                continue
            meta["id"] = folder.name
            trips.append(meta)
        return trips

    def load(self, trip_id: str) -> dict[str, Any]:
        folder = (self.root / trip_id).resolve()
        if folder.parent != self.root.resolve():
            raise ValueError("invalid trip id")
        meta = json.loads((folder / "trip.json").read_text())
        meta["id"] = trip_id
        return meta

    # --- internals ------------------------------------------------------------------
    def _flush(self, rec: _Recording, final: bool = False) -> None:
        rec.last_flush = self._clock()
        elapsed = self._clock() - rec.started_mono
        driven = rec.meta.setdefault("driven", {})
        driven.update({
            "distance_m": round(rec.distance_m),
            "duration_s": round(elapsed),
            "max_speed_kmh": round(rec.max_speed),
            "avg_speed_kmh": round(rec.distance_m / elapsed * 3.6) if elapsed > 0 else 0,
            "points": len(rec.points),
        })
        if final:
            driven["ended"] = _iso(_now())
        if rec.points:
            write_gpx(rec.folder / "track.gpx", rec.meta["name"] + " (driven)", [rec.points],
                      time=rec.points[0].time)
        self._write_meta(rec.folder, rec.meta)

    @staticmethod
    def _write_route(folder: Path, name: str, points: list[LatLon], start: dict[str, Any],
                     destination: dict[str, Any]) -> None:
        wpts = [(GpxPoint(start["lat"], start["lon"]), start["name"]),
                (GpxPoint(destination["lat"], destination["lon"]), destination["name"])]
        write_gpx(folder / "route.gpx", name + " (planned)",
                  [[GpxPoint(a, b) for a, b in points]], wpts)

    @staticmethod
    def _write_meta(folder: Path, meta: dict[str, Any]) -> None:
        tmp = folder / "trip.json.tmp"
        tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        tmp.replace(folder / "trip.json")

    def _mark_interrupted(self) -> None:
        """A trip still 'driving' at startup was cut by a power loss or crash."""
        for folder in self.root.iterdir() if self.root.is_dir() else []:
            meta_file = folder / "trip.json"
            try:
                meta = json.loads(meta_file.read_text())
            except (OSError, ValueError):
                continue
            if meta.get("status") == "driving":
                meta["status"] = "interrupted"
                self._write_meta(folder, meta)
