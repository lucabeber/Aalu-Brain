"""Offline place search: an SQLite FTS5 index built from an OSM extract.

Indexed: settlements (city ... hamlet), points of interest (fuel, campsites, peaks,
shops, ...), named streets (one row per street and town) and house-number
addresses. Bilingual names (South Tyrol: name:it / name:de) are searchable.

Query rules: every word must match the start of a word (accents ignored), e.g.
"via roma 12 tren" finds "Via Roma 12, Trento". Ranking = text relevance, then
importance of the kind of place, then distance from the vehicle.
"""

from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from aalu.core.geo import LatLon, haversine_m
from aalu.services.navigation import Place

SETTLEMENT_RANK = {"city": 100, "town": 90, "village": 75, "suburb": 60, "hamlet": 55,
                   "neighbourhood": 45, "locality": 40, "isolated_dwelling": 30}
CONTEXT_TYPES = ("city", "town", "village", "hamlet")
POI_KEYS = ("amenity", "tourism", "shop", "leisure", "historic", "natural", "railway",
            "aeroway", "mountain_pass", "office", "craft")
ROAD_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
              "residential", "living_street", "pedestrian", "service", "track", "road",
              "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
ALT_NAME_KEYS = ("name:it", "name:de", "name:en", "alt_name", "official_name", "loc_name")
KIND_RANK = {"place": 0, "poi": 30, "street": 20, "address": 10}

SCHEMA = """
CREATE TABLE places (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    alt TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,          -- place | poi | street | address
    category TEXT NOT NULL,      -- e.g. town, fuel, camp_site, residential
    rank INTEGER NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    lat REAL NOT NULL,
    lon REAL NOT NULL
);
CREATE INDEX places_kind_pos ON places(kind, lat, lon);
CREATE VIRTUAL TABLE places_fts USING fts5(
    name, alt, context, content='places', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""


@dataclass
class _Row:
    name: str
    alt: str
    kind: str
    category: str
    rank: int
    lat: float
    lon: float
    context: str = ""


def _centroid(way) -> LatLon | None:
    lats, lons = [], []
    for n in way.nodes:
        if n.location.valid():
            lats.append(n.location.lat)
            lons.append(n.location.lon)
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _area_centroid(area) -> LatLon | None:
    lats, lons = [], []
    for ring in area.outer_rings():
        for n in ring:
            if n.location.valid():
                lats.append(n.location.lat)
                lons.append(n.location.lon)
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _classify(tags) -> tuple[str, str, int] | None:
    place = tags.get("place")
    if place in SETTLEMENT_RANK:
        return "place", place, SETTLEMENT_RANK[place]
    for key in POI_KEYS:
        value = tags.get(key)
        if value and value not in ("yes", "no"):
            # Things a camper actually looks for rank higher.
            bonus = 20 if value in ("fuel", "camp_site", "caravan_site", "charging_station",
                                    "sanitary_dump_station", "drinking_water", "parking",
                                    "peak", "mountain_pass", "station") else 0
            return "poi", value if key != "mountain_pass" else "mountain_pass", 40 + bonus
    highway = tags.get("highway")
    if highway in ROAD_TYPES:
        return "street", highway, 30
    return None


def collect(pbf: Path) -> tuple[list[_Row], tuple[float, float, float, float]]:
    """Read the OSM extract. Returns rows and the data extent
    (min_lon, min_lat, max_lon, max_lat)."""
    import osmium

    rows: list[_Row] = []
    streets: dict[tuple[str, int, int], _Row] = {}
    ext = [180.0, 90.0, -180.0, -90.0]

    def grow(lat: float, lon: float) -> None:
        ext[0], ext[1] = min(ext[0], lon), min(ext[1], lat)
        ext[2], ext[3] = max(ext[2], lon), max(ext[3], lat)

    fp = osmium.FileProcessor(str(pbf)).with_locations().with_areas().with_filter(
        osmium.filter.KeyFilter("name", "addr:housenumber"))
    for obj in fp:
        if obj.is_node():
            if not obj.location.valid():
                continue
            pos: LatLon | None = (obj.location.lat, obj.location.lon)
        elif obj.is_way():
            pos = _centroid(obj)
        elif obj.is_area() and not obj.from_way():
            # Multipolygon relations (big lakes, parks, glaciers). Areas built from closed
            # ways are skipped: the way itself was already handled.
            pos = _area_centroid(obj)
            if pos is None or obj.tags.get("boundary"):
                continue
        else:
            continue
        if pos is None:
            continue
        tags = obj.tags
        grow(*pos)
        house, street = tags.get("addr:housenumber"), tags.get("addr:street")
        if house and street:
            rows.append(_Row(f"{street} {house}", "", "address", "address", 20, *pos,
                             context=tags.get("addr:city") or tags.get("addr:place") or ""))
        name = tags.get("name")
        if not name:
            continue
        cls = _classify(tags)
        if cls is None:
            continue
        kind, category, rank = cls
        alt = " ".join(v for k in ALT_NAME_KEYS if (v := tags.get(k)) and v != name)
        row = _Row(name, alt, kind, category, rank, *pos)
        if kind == "street":
            # A street is split into many ways: keep one row per name and ~1 km cell.
            key = (name, int(pos[0] * 100), int(pos[1] * 100))
            streets.setdefault(key, row)
        else:
            rows.append(row)
    rows.extend(streets.values())
    return rows, (ext[0], ext[1], ext[2], ext[3])


def _assign_context(rows: list[_Row]) -> None:
    """Nearest settlement name for every non-settlement row (grid of 0.1°)."""
    grid: dict[tuple[int, int], list[_Row]] = {}
    for r in rows:
        if r.kind == "place" and r.category in CONTEXT_TYPES:
            grid.setdefault((int(r.lat * 10), int(r.lon * 10)), []).append(r)
    for r in rows:
        if r.context or (r.kind == "place" and r.category in CONTEXT_TYPES):
            continue
        cx, cy = int(r.lat * 10), int(r.lon * 10)
        best, best_d = None, math.inf
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for p in grid.get((cx + dx, cy + dy), ()):
                    d = (p.lat - r.lat) ** 2 + ((p.lon - r.lon) * 0.7) ** 2
                    if d < best_d:
                        best, best_d = p, d
        if best is not None:
            r.context = best.name


def build_index(pbf: Path, db_path: Path) -> tuple[int, tuple[float, float, float, float]]:
    rows, extent = collect(pbf)
    _assign_context(rows)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO places(name, alt, kind, category, rank, context, lat, lon) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ((r.name, r.alt, r.kind, r.category, r.rank, r.context, r.lat, r.lon) for r in rows))
    con.execute("INSERT INTO places_fts(places_fts) VALUES ('rebuild')")
    con.execute("INSERT INTO places_fts(places_fts) VALUES ('optimize')")
    con.commit()
    con.execute("VACUUM")
    con.close()
    tmp.replace(db_path)
    return len(rows), extent


def _tokens(query: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode()
    return [t for t in re.split(r"[^\w]+", plain.lower()) if t]


class LocalGeocoder:
    """Search one or more pack indexes. Thread-safe: one connection per call."""

    def __init__(self, dbs: Iterable[Path]) -> None:
        self._dbs = [p for p in dbs if p.exists()]

    @property
    def available(self) -> bool:
        return bool(self._dbs)

    def search(self, query: str, near: LatLon | None, limit: int = 8) -> list[Place]:
        tokens = _tokens(query)
        if not tokens:
            return []
        candidates = self._candidates(tokens, near)
        if not any(full for _, _, full in candidates) and any(t.isdigit() for t in tokens):
            # "via roma 12 trento" without that house number: offer the street itself.
            candidates += self._candidates([t for t in tokens if not t.isdigit()], near)
        # Results matching every word whole come first; scores of the two queries
        # (with and without house number) are not comparable, so order by that first.
        candidates.sort(key=lambda c: (not c[2], c[0]))
        out: list[Place] = []
        for _, p, _ in candidates:
            if not any(q.name == p.name and haversine_m((q.lat, q.lon), (p.lat, p.lon)) < 1500
                       for q in out):
                out.append(p)
            if len(out) >= limit:
                break
        return out

    def _candidates(self, tokens: list[str], near: LatLon | None
                    ) -> list[tuple[float, Place, bool]]:
        """(score, place, every query word matched as a whole word)."""
        if not tokens:
            return []
        match = " ".join(f'"{t}"*' for t in tokens)
        candidates: list[tuple[float, Place, bool]] = []
        for db in self._dbs:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                cur = con.execute(
                    "SELECT p.name, p.context, p.category, p.rank, p.lat, p.lon, "
                    "bm25(places_fts, 10.0, 5.0, 2.0) FROM places_fts JOIN places p "
                    "ON p.id = places_fts.rowid WHERE places_fts MATCH ? "
                    "ORDER BY bm25(places_fts, 10.0, 5.0, 2.0) LIMIT 300", (match,))
                for name, context, category, rank, lat, lon, bm25 in cur:
                    score = bm25 - rank / 25.0  # bm25 is negative: lower = better
                    if near is not None:
                        km = haversine_m(near, (lat, lon)) / 1000
                        score += math.log1p(km) * 0.6
                    words = set(_tokens(f"{name} {context}"))
                    whole = sum(t in words for t in tokens) / len(tokens)
                    score -= 6.0 * whole  # "roma" (whole word) beats "romagnosi" (prefix)
                    if " ".join(_tokens(name)) == " ".join(tokens):
                        score -= 3.0  # exact name
                    detail = ", ".join(x for x in (context, category.replace("_", " ")) if x)
                    candidates.append((score, Place(name, detail, lat, lon, category),
                                       whole == 1.0))
            except sqlite3.OperationalError:
                continue
            finally:
                con.close()
        return candidates

    def reverse(self, lat: float, lon: float, max_km: float = 8.0) -> str | None:
        """Name of the nearest town or village (for trip and GPX names). Districts and
        hamlets count only when no town is near: "Trento" rather than "Centro storico"."""
        d = max_km / 111.0
        weight = {"city": 0.5, "town": 0.7, "village": 1.0, "hamlet": 2.0, "suburb": 3.0}
        best: tuple[float, str] | None = None
        for db in self._dbs:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                for name, category, plat, plon in con.execute(
                        "SELECT name, category, lat, lon FROM places WHERE kind='place' AND "
                        "category IN ('city','town','village','hamlet','suburb') AND lat BETWEEN "
                        "? AND ? AND lon BETWEEN ? AND ?",
                        (lat - d, lat + d, lon - d * 1.5, lon + d * 1.5)):
                    dist = haversine_m((lat, lon), (plat, plon))
                    if dist > max_km * 1000:
                        continue
                    score = dist * weight[category]
                    if best is None or score < best[0]:
                        best = (score, name)
            finally:
                con.close()
        return None if best is None else best[1]
