import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from aalu.services.tile_proxy import TileProxy


@pytest.fixture
def upstream():
    seen: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802
            seen.append((self.path, self.headers.get("User-Agent")))
            body = b"PNGDATA"
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/tiles/", seen
    server.shutdown()
    server.server_close()


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read()


def test_forwards_tiles_with_user_agent_and_reuses_connections(upstream):
    base, seen = upstream
    proxy = TileProxy(base, "AALU-test/1.0", pool_size=2)
    url = proxy.start()
    try:
        for x in range(5):
            assert fetch(f"{url}15/{17395 + x}/11648.png") == (200, "image/png", b"PNGDATA")
    finally:
        proxy.stop()
    assert seen[0] == ("/tiles/15/17395/11648.png", "AALU-test/1.0")
    assert len(seen) == 5


def test_rejects_non_tile_paths(upstream):
    base, seen = upstream
    proxy = TileProxy(base, "AALU-test/1.0")
    url = proxy.start()
    try:
        for bad in ("etc/passwd", "15/1/2.jpg", "../15/1/2.png"):
            with pytest.raises(urllib.error.HTTPError) as err:
                fetch(url + bad)
            assert err.value.code == 404
    finally:
        proxy.stop()
    assert seen == []


def test_upstream_down_gives_502():
    proxy = TileProxy("http://127.0.0.1:9/", "AALU-test/1.0", timeout_s=1)
    url = proxy.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as err:
            fetch(url + "1/0/0.png")
        assert err.value.code == 502
    finally:
        proxy.stop()


def test_invalid_upstream_rejected():
    with pytest.raises(ValueError):
        TileProxy("ftp://example.org/", "x")
