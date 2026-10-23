"""Local HTTP server for the map view (localhost only).

    /web/<file>                     map page and vendored JavaScript (apps/dashboard/web)
    /assets/<file>                  fonts and sprites of the map style (<maps_dir>/_assets)
    /packs.json                     installed map packs (name, bbox, zoom range)
    /tiles/<pack>/<z>/<x>/<y>.mvt   vector tiles read from <pack>/map.pmtiles
    /osm/<z>/<x>/<y>.png            online raster fallback (OSM), via the tile proxy pool

Everything except /osm works without Internet.
"""

from __future__ import annotations

import http.client
import json
import logging
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from aalu.maps.pack import ASSETS_DIR, MapPack
from aalu.services.tile_proxy import _ConnectionPool

log = logging.getLogger(__name__)

_TILE = re.compile(r"^/tiles/([\w.-]+)/(\d{1,2})/(\d{1,7})/(\d{1,7})\.mvt$")
_OSM = re.compile(r"^/osm/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/x-protobuf", ".pbf")


class _PmtilesPack:
    def __init__(self, pack: MapPack) -> None:
        from pmtiles.reader import MmapSource, Reader
        from pmtiles.tile import Compression

        self.pack = pack
        self._file = open(pack.pmtiles, "rb")  # noqa: SIM115 (kept open for mmap)
        self._reader = Reader(MmapSource(self._file))
        header = self._reader.header()
        self.minzoom = header["min_zoom"]
        self.maxzoom = header["max_zoom"]
        self.gzip = header["tile_compression"] == Compression.GZIP
        self._lock = threading.Lock()

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        with self._lock:
            return self._reader.get(z, x, y)

    def info(self) -> dict[str, Any]:
        return {"name": self.pack.name, "bbox": list(self.pack.bbox),
                "minzoom": self.minzoom, "maxzoom": self.maxzoom}


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        log.exception("map server: request from %s failed", client_address)


class MapServer:
    def __init__(self, web_dir: Path, maps_dir: Path, packs: list[MapPack],
                 osm_upstream: str | None, user_agent: str) -> None:
        self._web = web_dir.resolve()
        self._assets = (maps_dir / ASSETS_DIR).resolve()
        self._packs: dict[str, _PmtilesPack] = {}
        for pack in packs:
            if pack.has("map"):
                try:
                    self._packs[pack.name] = _PmtilesPack(pack)
                except Exception:
                    log.exception("map pack %s: cannot open %s", pack.name, pack.pmtiles)
        self._osm = _ConnectionPool(osm_upstream, 4, 10.0) if osm_upstream else None
        self._user_agent = user_agent
        self._server: _Server | None = None

    @property
    def url(self) -> str:
        assert self._server is not None, "map server not started"
        return f"http://127.0.0.1:{self._server.server_address[1]}/"

    def packs(self) -> list[dict[str, Any]]:
        return [p.info() for p in self._packs.values()]

    def start(self) -> str:
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def handle(self) -> None:
                try:
                    super().handle()
                except ConnectionError:
                    log.debug("map server: client closed the connection")

            def do_GET(self) -> None:  # noqa: N802
                path = unquote(self.path.split("?", 1)[0])
                if m := _TILE.match(path):
                    pack = server._packs.get(m.group(1))
                    data = pack.tile(*map(int, m.groups()[1:])) if pack else None
                    if data is None:
                        self._reply(204, b"")  # empty: outside the pack or no data there
                    else:
                        headers = {"Content-Type": "application/x-protobuf",
                                   "Cache-Control": "max-age=86400"}
                        if pack and pack.gzip:
                            headers["Content-Encoding"] = "gzip"
                        self._reply(200, data, headers)
                elif m := _OSM.match(path):
                    self._osm(f"/{m.group(1)}/{m.group(2)}/{m.group(3)}.png")
                elif path == "/packs.json":
                    self._reply(200, json.dumps(server.packs()).encode(),
                                {"Content-Type": "application/json"})
                elif path.startswith("/web/"):
                    self._file(server._web, path[len("/web/"):])
                elif path.startswith("/assets/"):
                    self._file(server._assets, path[len("/assets/"):])
                else:
                    self._reply(404, b"")

            def _osm(self, tile: str) -> None:
                if server._osm is None:
                    self._reply(404, b"")
                    return
                try:
                    status, headers, body = server._osm.get(
                        tile, {"User-Agent": server._user_agent})
                except (OSError, http.client.HTTPException):
                    self._reply(502, b"")  # offline: no online fallback, packs still work
                    return
                self._reply(status, body, headers)

            def _file(self, base: Path, rel: str) -> None:
                target = (base / rel).resolve()
                if base not in target.parents or not target.is_file():
                    self._reply(404, b"")  # also refuses ../ escapes
                    return
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self._reply(200, target.read_bytes(), {"Content-Type": ctype,
                                                       "Cache-Control": "max-age=3600"})

            def _reply(self, status: int, body: bytes, headers: dict[str, str] | None = None
                       ) -> None:
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                log.debug("map server: " + format, *args)

        self._server = _Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, name="map-server",
                         daemon=True).start()
        log.info("map server %s (%d offline pack(s))", self.url, len(self._packs))
        return self.url

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
