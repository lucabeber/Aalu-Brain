"""The user's GPX files: scan a folder, index them, search, load.

The index (name, date, length, start/end and their place names) is cached in
``<gpx_dir>/.aalu-gpx-index.json`` and refreshed only for new or changed files.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aalu.core.geo import LatLon, Polyline, haversine_m
from aalu.maps.gpx import GpxData, read_gpx

log = logging.getLogger(__name__)

INDEX_FILE = ".aalu-gpx-index.json"


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


class GpxLibrary:
    def __init__(self, root: Path, namer: Callable[[float, float], str | None]) -> None:
        self.root = root
        self._namer = namer
        self._entries: dict[str, dict[str, Any]] = {}

    def refresh(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            self._entries = {}
            return []
        cache = self._load_cache()
        entries: dict[str, dict[str, Any]] = {}
        for path in sorted(self.root.rglob("*.gpx")):
            rel = path.relative_to(self.root).as_posix()
            try:
                st = path.stat()
            except OSError:
                continue
            old = cache.get(rel)
            if old and old.get("mtime") == st.st_mtime and old.get("size") == st.st_size:
                entries[rel] = old
                continue
            try:
                entries[rel] = self._describe(path, rel, st.st_mtime, st.st_size)
            except Exception as exc:  # broken file: show it, do not stop the scan
                log.info("GPX %s unreadable: %s", rel, exc)
                entries[rel] = {"id": rel, "name": path.stem, "error": str(exc)[:120],
                                "mtime": st.st_mtime, "size": st.st_size}
        self._entries = entries
        self._save_cache(entries)
        return list(entries.values())

    def search(self, query: str, near: LatLon | None, limit: int = 50) -> list[dict[str, Any]]:
        if not self._entries:
            self.refresh()
        words = _norm(query).split()
        out = []
        for e in self._entries.values():
            text = _norm(" ".join(str(e.get(k) or "") for k in
                                  ("name", "id", "start_name", "end_name", "date")))
            if all(w in text for w in words):
                row = dict(e)
                if near and e.get("start"):
                    row["distance_m"] = round(haversine_m(near, (e["start"]["lat"],
                                                                 e["start"]["lon"])))
                out.append(row)
        # Nearest first when we know where we are, else most recent first.
        out.sort(key=lambda r: (r.get("error") is not None,
                                r.get("distance_m", 0) if near else 0,
                                "" if near else _neg(r.get("date") or "")))
        return out[:limit]

    def load(self, gpx_id: str) -> tuple[GpxData, list[LatLon], Path]:
        path = (self.root / gpx_id).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("invalid GPX id")
        data = read_gpx(path)
        points = [(p.lat, p.lon) for p in data.all_points()]
        if len(points) < 2:
            raise ValueError("no track in this GPX file")
        return data, points, path

    # --- internals ----------------------------------------------------------------
    def _describe(self, path: Path, rel: str, mtime: float, size: int) -> dict[str, Any]:
        data = read_gpx(path)
        pts = [(p.lat, p.lon) for p in data.all_points()]
        if len(pts) < 2:
            raise ValueError("no track points")
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        start, end = pts[0], pts[-1]
        return {
            "id": rel,
            "name": data.name or path.stem.replace("_", " "),
            "date": data.time.date().isoformat() if data.time else None,
            "points": len(pts),
            "length_m": round(Polyline(pts).length),
            "bbox": [min(lons), min(lats), max(lons), max(lats)],
            "start": {"lat": start[0], "lon": start[1]},
            "end": {"lat": end[0], "lon": end[1]},
            "start_name": self._namer(*start),
            "end_name": self._namer(*end),
            "loop": haversine_m(start, end) < 300,
            "mtime": mtime, "size": size,
        }

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads((self.root / INDEX_FILE).read_text())
        except (OSError, ValueError):
            return {}

    def _save_cache(self, entries: dict[str, dict[str, Any]]) -> None:
        try:
            tmp = self.root / (INDEX_FILE + ".tmp")
            tmp.write_text(json.dumps(entries, ensure_ascii=False))
            tmp.replace(self.root / INDEX_FILE)
        except OSError:
            pass  # read-only folder (e.g. a USB stick): just scan again next time


def _neg(date: str) -> str:
    """Sort key for newest-first on ISO dates."""
    return "".join(chr(255 - ord(c)) for c in date) if re.match(r"\d{4}-", date) else "~"
