"""Dashcam service: one recorder per camera, retention, "save clip", control socket.

Runs as its own process (apps/video/main.py) so a dashboard crash never stops
recording. The dashboard talks to it over a local UNIX socket with one JSON
object per line:

    {"cmd": "status"}   -> {"ok": true, "status": {...}}
    {"cmd": "protect"}  -> {"ok": true, "protected": <n segments so far>}
"""

from __future__ import annotations

import json
import logging
import os
import socketserver
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aalu.services.config import VideoConfig
from aalu.video.recorder import CameraRecorder
from aalu.video.segments import Segment, SegmentStore

log = logging.getLogger(__name__)

HOUSEKEEPING_S = 10.0


def default_socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/aalu-{os.getuid()}"
    return Path(runtime) / "aalu" / "video.sock"


@dataclass
class _ProtectWindow:
    start: float  # wall clock
    end: float


class VideoService:
    def __init__(self, config: VideoConfig, root: Path, socket_path: Path | None = None,
                 recorder_factory: Callable[..., CameraRecorder] = CameraRecorder,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.store = SegmentStore(root, wall_clock=wall_clock)
        self.socket_path = socket_path or (Path(config.socket) if config.socket
                                           else default_socket_path())
        self._wall = wall_clock
        self._lock = threading.Lock()
        self._windows: list[_ProtectWindow] = []
        self._protected_count = 0
        self._last_retention: list[str] = []
        self._stop = threading.Event()
        self._server: socketserver.ThreadingUnixStreamServer | None = None
        self.recorders = [
            recorder_factory(cam, self.store, config.segment_s, self._on_segment,
                             wall_clock=wall_clock)
            for cam in config.cameras
        ]

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        for rec in self.recorders:
            rec.start()
        try:
            self._start_control()
        except OSError:
            # Recording must not depend on the dashboard link: keep going without it.
            log.exception("video service: control socket %s unavailable", self.socket_path)
        threading.Thread(target=self._housekeeping, name="video-housekeeping",
                         daemon=True).start()
        log.info("video service: %d camera(s), storage %s, socket %s",
                 len(self.recorders), self.store.root, self.socket_path)

    def stop(self) -> None:
        self._stop.set()
        for rec in self.recorders:
            rec.stop()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        self.socket_path.unlink(missing_ok=True)

    # --- protection ("save clip") ----------------------------------------
    def protect(self) -> int:
        """Keep the last ``protect_before_s`` and the next ``protect_after_s`` seconds."""
        now = self._wall()
        limit = self.config.protected_max_gb * 1e9
        if self.store.protected_bytes() >= limit:
            log.warning("protect refused: protected clips exceed %.0f GB",
                        self.config.protected_max_gb)
            return -1
        window = _ProtectWindow(now - self.config.protect_before_s,
                                now + self.config.protect_after_s)
        with self._lock:
            self._windows.append(window)
            for seg in self.store.segments():
                # Finished segment ending inside the window (it ends at its mtime).
                if seg.mtime >= window.start:
                    self.store.protect(seg)
                    self._protected_count += 1
        return self._protected_count

    def _on_segment(self, seg: Segment, started_at: float) -> None:
        with self._lock:
            now = self._wall()
            self._windows = [w for w in self._windows if w.end + self.config.segment_s > now]
            if any(started_at <= w.end and seg.mtime >= w.start for w in self._windows):
                self.store.protect(seg)
                self._protected_count += 1

    # --- status -----------------------------------------------------------
    def status(self) -> dict[str, Any]:
        free_gb, free_pct = self.store.disk_usage()
        normal = self.store.segments()
        protected = self.store.segments(protected=True)
        with self._lock:
            protecting = any(w.end > self._wall() for w in self._windows)
        return {
            "recording": any(r.state == "recording" for r in self.recorders),
            "cameras": [r.status() for r in self.recorders],
            "simulated": self.config.simulated,
            "disk_free_gb": round(free_gb, 1),
            "disk_free_pct": round(free_pct, 1),
            "used_gb": round(sum(s.size for s in normal) / 1e9, 2),
            "segments": len(normal),
            "oldest_age_h": round((self._wall() - normal[0].mtime) / 3600, 1) if normal else None,
            "retention_h": self.config.retention_h,
            "protected_segments": len(protected),
            "protected_gb": round(sum(s.size for s in protected) / 1e9, 2),
            "protected_max_gb": self.config.protected_max_gb,
            "protecting": protecting,
        }

    # --- internals ----------------------------------------------------------
    def _housekeeping(self) -> None:
        while not self._stop.wait(HOUSEKEEPING_S):
            try:
                self.store.enforce_retention(self.config.retention_h, self.config.min_free_pct)
            except OSError:
                log.exception("retention failed")

    def _start_control(self) -> None:
        service = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                for raw in self.rfile:
                    try:
                        cmd = json.loads(raw).get("cmd")
                        if cmd == "status":
                            reply: dict[str, Any] = {"ok": True, "status": service.status()}
                        elif cmd == "protect":
                            n = service.protect()
                            reply = {"ok": n >= 0, "protected": n}
                        else:
                            reply = {"ok": False, "error": f"unknown command {cmd!r}"}
                    except (ValueError, AttributeError) as exc:
                        reply = {"ok": False, "error": str(exc)}
                    self.wfile.write((json.dumps(reply) + "\n").encode())

        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.socket_path.unlink(missing_ok=True)
        self._server = socketserver.ThreadingUnixStreamServer(str(self.socket_path), Handler)
        self._server.daemon_threads = True
        os.chmod(self.socket_path, 0o600)
        threading.Thread(target=self._server.serve_forever, name="video-control",
                         daemon=True).start()


def request(socket_path: Path, cmd: str, timeout: float = 1.0) -> dict[str, Any]:
    """Client side: one command, one reply. Raises OSError if the service is not running."""
    import socket

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(socket_path))
        sock.sendall((json.dumps({"cmd": cmd}) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    try:
        return json.loads(data)
    except ValueError as exc:
        raise OSError(f"bad reply from video service: {exc}") from exc
