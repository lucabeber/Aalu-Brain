"""Offline map packs: everything needed to show, search and route a region without Internet.

    <maps_dir>/<name>/pack.json        metadata (bbox, sources, build date, sizes)
    <maps_dir>/<name>/map.pmtiles      vector map (Protomaps basemap schema)
    <maps_dir>/<name>/valhalla/        routing graph tiles (Valhalla)
    <maps_dir>/<name>/places.sqlite    search index (places, POIs, streets, addresses)
    <maps_dir>/_assets/                fonts and sprites shared by all packs
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACK_FILE = "pack.json"
ASSETS_DIR = "_assets"


@dataclass(frozen=True)
class MapPack:
    name: str
    path: Path
    bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat
    meta: dict[str, Any]

    @property
    def pmtiles(self) -> Path:
        return self.path / "map.pmtiles"

    @property
    def valhalla_dir(self) -> Path:
        return self.path / "valhalla"

    @property
    def places_db(self) -> Path:
        return self.path / "places.sqlite"

    def contains(self, lat: float, lon: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        return x0 <= lon <= x1 and y0 <= lat <= y1

    def has(self, part: str) -> bool:
        target = {"map": self.pmtiles, "routing": self.valhalla_dir, "search": self.places_db}[part]
        return target.is_dir() and any(target.iterdir()) if target.suffix == "" else target.exists()


def load_pack(path: Path) -> MapPack:
    meta = json.loads((path / PACK_FILE).read_text())
    return MapPack(meta["name"], path, tuple(meta["bbox"]), meta)  # type: ignore[arg-type]


def find_packs(maps_dir: Path) -> list[MapPack]:
    """All built packs under ``maps_dir`` (folders with a pack.json), sorted by name."""
    if not maps_dir.is_dir():
        return []
    packs = []
    for d in sorted(maps_dir.iterdir()):
        if (d / PACK_FILE).is_file():
            try:
                packs.append(load_pack(d))
            except (OSError, ValueError, KeyError):
                continue
    return packs


def write_pack_meta(path: Path, meta: dict[str, Any]) -> None:
    tmp = path / (PACK_FILE + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2))
    tmp.replace(path / PACK_FILE)
