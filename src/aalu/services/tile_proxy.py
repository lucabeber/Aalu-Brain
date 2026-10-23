"""Local map tile proxy: Qt fetches http://127.0.0.1:<port>/z/x/y.png, we fetch upstream.

Why: Qt's HTTP/2 client and the OSM tile CDN intermittently disagree on header
compression ("Server is unable to maintain the header compression context"), which
drops tiles. The osm plugin uses its own network manager, so HTTP/2 cannot be turned
off from QML. This proxy speaks HTTP/1.1 upstream over a small pool of persistent
connections (the OSM usage policy prefers keep-alive) and sends a proper User-Agent.
Later the upstream can be a local OSM Scout Server for offline maps.

Only z/x/y.png paths are served and the server binds to localhost only.
"""

from __future__ import annotations

import http.client
import logging
import queue
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

_TILE_PATH = re.compile(r"^/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")


class _ConnectionPool:
    def __init__(self, upstream: str, size: int, timeout: float) -> None:
        parts = urlsplit(upstream)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"unsupported tile upstream {upstream!r}")
        self._https = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port
        self.prefix = parts.path.rstrip("/")
        self._timeout = timeout
        self._idle: queue.LifoQueue[http.client.HTTPConnection] = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(size)

    def _new(self) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self._https else http.client.HTTPConnection
        return cls(self._host, self._port, timeout=self._timeout)

    def get(self, path: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        with self._slots:  # bounded concurrency towards the tile server
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                conn = self._new()
            for attempt in (1, 2):  # a kept-alive connection may have been closed
                try:
                    conn.request("GET", self.prefix + path, headers=headers)
                    resp = conn.getresponse()
                    body = resp.read()
                    if resp.will_close:
                        conn.close()
                    else:
                        self._idle.put(conn)
                    keep = ("Content-Type", "Cache-Control", "Expires", "Last-Modified", "ETag")
                    return resp.status, {k: v for k in keep if (v := resp.getheader(k))}, body
                except (OSError, http.client.HTTPException):
                    conn.close()
                    if attempt == 2:
                        raise
                    conn = self._new()
        raise AssertionError("unreachable")


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        # Default prints a traceback to stderr; keep unexpected errors in the app log instead.
        log.exception("tile proxy: request from %s failed", client_address)


class TileProxy:
    def __init__(self, upstream: str, user_agent: str, pool_size: int = 4,
                 timeout_s: float = 10.0) -> None:
        self._pool = _ConnectionPool(upstream, pool_size, timeout_s)
        self._user_agent = user_agent
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        assert self._server is not None, "proxy not started"
        return f"http://127.0.0.1:{self._server.server_address[1]}/"

    def start(self) -> str:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def handle(self) -> None:
                try:
                    super().handle()
                except ConnectionError:
                    # Normal: Qt cancels tiles that scrolled out of view while panning or
                    # zooming, closing the connection before the reply is written.
                    log.debug("tile proxy: client closed the connection")

            def do_GET(self) -> None:  # noqa: N802 (http.server API)
                if not _TILE_PATH.match(self.path):
                    self._reply(404, {}, b"")
                    return
                try:
                    status, headers, body = proxy._pool.get(
                        self.path, {"User-Agent": proxy._user_agent})
                except (OSError, http.client.HTTPException) as exc:
                    log.debug("tile %s: upstream unavailable (%s)", self.path, exc)
                    self._reply(502, {}, b"")  # offline: Qt keeps using its disk cache
                    return
                self._reply(status, headers, body)

            def _reply(self, status: int, headers: dict[str, str], body: bytes) -> None:
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                log.debug("tile proxy: " + format, *args)

        self._server = _Server(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="tile-proxy", daemon=True)
        self._thread.start()
        log.info("tile proxy %s -> upstream", self.url)
        return self.url

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
