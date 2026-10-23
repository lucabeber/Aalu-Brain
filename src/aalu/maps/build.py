"""Build an offline map pack (map, routing, search) for one region.

Run with Internet, at home (PC or Pi), then the pack works without network:

    python scripts/build_map_pack.py trentino-alto-adige

Steps (each is skipped when its output already exists, unless --force):
1. download the region's OSM extract (.osm.pbf)
2. search index    -> places.sqlite   (and the region extent)
3. map             -> map.pmtiles     (cut out of the Protomaps daily world build)
4. routing graph   -> valhalla/       (pyvalhalla's valhalla_build_tiles)
5. shared assets   -> _assets/        (fonts and sprites for the map style, once)
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from aalu.maps.pack import ASSETS_DIR, write_pack_meta
from aalu.maps.places import build_index

log = logging.getLogger(__name__)

USER_AGENT = "AALU-map-pack-builder/0.1 (private camper project)"

REGIONS = {
    "trentino-alto-adige":
        "https://download.openstreetmap.fr/extracts/europe/italy/trentino_alto_adige-latest.osm.pbf",
    "veneto": "https://download.openstreetmap.fr/extracts/europe/italy/veneto-latest.osm.pbf",
    "lombardia": "https://download.openstreetmap.fr/extracts/europe/italy/lombardia-latest.osm.pbf",
    "italy-nord-est": "https://download.geofabrik.de/europe/italy/nord-est-latest.osm.pbf",
    "italy-nord-ovest": "https://download.geofabrik.de/europe/italy/nord-ovest-latest.osm.pbf",
    "italy": "https://download.geofabrik.de/europe/italy-latest.osm.pbf",
    "austria": "https://download.geofabrik.de/europe/austria-latest.osm.pbf",
    "switzerland": "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf",
    "alps": "https://download.geofabrik.de/europe/alps-latest.osm.pbf",
}

PROTOMAPS_BUILDS = "https://build-metadata.protomaps.dev/builds.json"
PROTOMAPS_BUILD_URL = "https://build.protomaps.com/{key}"
PMTILES_VERSION = "1.31.2"
PMTILES_TOOL_URL = ("https://github.com/protomaps/go-pmtiles/releases/download/v{v}/"
                    "go-pmtiles_{v}_Linux_{arch}.tar.gz")
ASSETS_URL = "https://raw.githubusercontent.com/protomaps/basemaps-assets/main/"
FONTS = ("Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic")
SPRITES = ("light", "dark")
MAX_ZOOM = 15  # highest zoom of the Protomaps build; the map over-zooms beyond it


def _download(url: str, target: Path, quiet: bool = False) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last = 0, 0.0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if not quiet and total and time.monotonic() - last > 2:
                last = time.monotonic()
                log.info("  %s: %d / %d MB", target.name, done >> 20, total >> 20)
    part.replace(target)
    return target


def _pmtiles_tool(maps_dir: Path) -> Path:
    arch = {"x86_64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine()]
    tool = maps_dir / "_tools" / f"pmtiles-{PMTILES_VERSION}"
    if not tool.exists():
        archive = _download(PMTILES_TOOL_URL.format(v=PMTILES_VERSION, arch=arch),
                            maps_dir / "_tools" / f"pmtiles-{PMTILES_VERSION}.tar.gz", quiet=True)
        with tarfile.open(archive) as tar:
            member = next(m for m in tar.getmembers() if m.name.endswith("pmtiles") and m.isfile())
            member.name = tool.name
            tar.extract(member, tool.parent, filter="data")
        archive.unlink()
        tool.chmod(0o755)
    return tool


def _latest_protomaps_build() -> tuple[str, str]:
    req = urllib.request.Request(PROTOMAPS_BUILDS, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        builds = json.load(resp)
    latest = builds[-1]
    return latest["key"], latest.get("version", "")


def build_assets(maps_dir: Path, force: bool = False) -> Path:
    """Fonts (glyph ranges) and sprites used by the Protomaps style. Shared by all packs."""
    assets = maps_dir / ASSETS_DIR
    marker = assets / ".complete"
    if marker.exists() and not force:
        return assets
    jobs: list[tuple[str, Path]] = []
    for font in FONTS:
        for start in range(0, 65536, 256):
            name = f"{start}-{start + 255}.pbf"
            jobs.append((f"{ASSETS_URL}fonts/{quote(font)}/{name}", assets / "fonts" / font / name))
    for sprite in SPRITES:
        for suffix in (".json", ".png", "@2x.json", "@2x.png"):
            jobs.append((f"{ASSETS_URL}sprites/v4/{sprite}{suffix}",
                         assets / "sprites" / "v4" / f"{sprite}{suffix}"))
    jobs.append((f"{ASSETS_URL}fonts/OFL.txt", assets / "fonts" / "OFL.txt"))
    log.info("assets: %d files (fonts and sprites)", len(jobs))

    def fetch(job: tuple[str, Path]) -> None:
        url, target = job
        if not target.exists() or force:
            _download(url, target, quiet=True)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fetch, jobs))
    marker.write_text(datetime.now(UTC).isoformat())
    return assets


def build_routing(pbf: Path, out_dir: Path) -> None:
    import valhalla
    from valhalla import get_config

    tmp = out_dir.with_name(out_dir.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    config = get_config(tile_extract="", tile_dir=str(tmp.resolve()))
    config_file = tmp / "valhalla.json"
    config_file.write_text(json.dumps(config))
    tool = Path(valhalla.__file__).parent / "bin" / "valhalla_build_tiles"
    subprocess.run([str(tool), "-c", str(config_file), str(pbf)], check=True,
                   stdout=subprocess.DEVNULL)
    config_file.unlink()
    shutil.rmtree(out_dir, ignore_errors=True)
    tmp.replace(out_dir)


def build_pack(name: str, maps_dir: Path, pbf_url: str | None = None,
               force: bool = False, max_zoom: int = MAX_ZOOM) -> Path:
    url = pbf_url or REGIONS.get(name)
    if not url:
        raise ValueError(f"unknown region {name!r}: pass --pbf-url (known: {', '.join(REGIONS)})")
    pack = maps_dir / name
    pack.mkdir(parents=True, exist_ok=True)
    pbf = maps_dir / "_downloads" / f"{name}.osm.pbf"
    meta_file = pack / "pack.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    meta.update({"name": name, "source_pbf": url})
    started = time.monotonic()

    if force or not pbf.exists():
        log.info("1/5 downloading %s", url)
        _download(url, pbf)
    meta["pbf_size_mb"] = round(pbf.stat().st_size / 1e6)

    db = pack / "places.sqlite"
    if force or not db.exists() or "bbox" not in meta:
        log.info("2/5 search index")
        rows, (x0, y0, x1, y1) = build_index(pbf, db)
        margin = 0.02
        meta["bbox"] = [round(x0 - margin, 4), round(y0 - margin, 4),
                        round(x1 + margin, 4), round(y1 + margin, 4)]
        meta["places"] = rows
    bbox = meta["bbox"]

    pm = pack / "map.pmtiles"
    if force or not pm.exists():
        key, version = _latest_protomaps_build()
        log.info("3/5 map: extracting %s (basemap %s) for bbox %s", key, version, bbox)
        tool = _pmtiles_tool(maps_dir)
        tmp = pm.with_suffix(".pmtiles.part")
        subprocess.run([str(tool), "extract", PROTOMAPS_BUILD_URL.format(key=key), str(tmp),
                        "--bbox=" + ",".join(str(v) for v in bbox), f"--maxzoom={max_zoom}",
                        "--download-threads=4"], check=True)
        tmp.replace(pm)
        meta.update({"map_build": key, "map_schema": version, "map_maxzoom": max_zoom})

    routing = pack / "valhalla"
    if force or not routing.is_dir():
        log.info("4/5 routing graph (Valhalla)")
        build_routing(pbf, routing)

    log.info("5/5 shared assets")
    build_assets(maps_dir)

    def size(p: Path) -> int:
        return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*")
                                                        if f.is_file())

    meta.update({
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "sizes_mb": {"map": round(size(pm) / 1e6), "routing": round(size(routing) / 1e6),
                     "search": round(size(db) / 1e6)},
    })
    write_pack_meta(pack, meta)
    log.info("pack %s ready in %.0f s: %s", name, time.monotonic() - started, meta["sizes_mb"])
    return pack
