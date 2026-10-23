"""Supervises one camera's GStreamer process and hands finished segments over.

A segment is finished when GStreamer has started the next one, or when the
process has exited. The process is restarted with backoff when it dies (camera
unplugged, encoder error), so one failing camera never stops the others.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aalu.services.config import CameraConfig
from aalu.video.pipeline import build_pipeline
from aalu.video.segments import Segment, SegmentStore

log = logging.getLogger(__name__)

POLL_S = 0.5


class CameraRecorder:
    def __init__(
        self,
        camera: CameraConfig,
        store: SegmentStore,
        segment_s: int,
        on_segment: Callable[[Segment, float], None],
        argv_factory: Callable[[CameraConfig, Path, int], list[str]] = build_pipeline,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.camera = camera
        self._store = store
        self._segment_s = segment_s
        self._on_segment = on_segment  # (segment, started_at)
        self._argv_factory = argv_factory
        self._wall = wall_clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._first_seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self.state = "stopped"  # stopped | starting | recording | restarting | error
        self.last_error: str | None = None
        self.segments_written = 0
        self.restarts = 0
        self.current_since: float | None = None

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"rec-{self.camera.name}",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 8.0) -> None:
        self._stop.set()
        self._terminate(timeout)
        if self._thread:
            self._thread.join(timeout=timeout)
        self._finalize(keep_newest=False)
        self.state = "stopped"

    def status(self) -> dict[str, Any]:
        return {
            "name": self.camera.name,
            "state": self.state,
            "audio": self.camera.audio,
            "simulated": self.camera.source == "test",
            "segments_written": self.segments_written,
            "restarts": self.restarts,
            "last_error": self.last_error,
            "current_since": self.current_since,
        }

    # --- supervision loop -------------------------------------------------
    def _run(self) -> None:
        backoff = 1.0
        incoming = self._store.incoming(self.camera.name)
        while not self._stop.is_set():
            self._finalize(keep_newest=False)  # leftovers from a crash or power loss
            try:
                argv = self._argv_factory(self.camera, incoming, self._segment_s)
                self.state = "starting"
                # stderr to a file, never a pipe: an unread pipe would block GStreamer.
                with open(self._log_path(), "wb") as log_file:
                    self._proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                                  stderr=log_file, start_new_session=True)
            except (OSError, RuntimeError, ValueError) as exc:
                self._fail(f"cannot start pipeline: {exc}")
            else:
                started = time.monotonic()
                while not self._stop.is_set() and self._proc.poll() is None:
                    self._finalize(keep_newest=True)
                    if self._first_seen:
                        self.state = "recording"
                    self._stop.wait(POLL_S)
                if self._stop.is_set():
                    return
                err = self._log_path().read_text(errors="replace").strip().splitlines()
                self._fail(f"pipeline exited ({self._proc.returncode}): "
                           f"{err[-1] if err else 'no message'}")
                if time.monotonic() - started > 60:
                    backoff = 1.0  # it had been running fine: restart quickly
            self.restarts += 1
            self.state = "restarting"
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30.0)

    def _log_path(self) -> Path:
        return self._store.root / self.camera.name / "gstreamer.log"

    def _fail(self, message: str) -> None:
        self.last_error = message
        self.current_since = None
        log.warning("camera %s: %s", self.camera.name, message)

    def _terminate(self, timeout: float) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        proc.send_signal(signal.SIGINT)  # gst-launch -e: EOS closes the last segment cleanly
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def _finalize(self, keep_newest: bool) -> None:
        """Move finished segments out of incoming/. The newest one is still being written."""
        with self._lock:
            incoming = self._store.incoming(self.camera.name)
            files = sorted(incoming.glob("seg_*.mkv"))
            now = self._wall()
            if keep_newest:  # live polling: first sight of a file = start of that segment
                for f in files:
                    self._first_seen.setdefault(f.name, now)
            done = files[:-1] if keep_newest else files
            for f in done:
                started = self._first_seen.pop(f.name, None)
                if started is None:  # left over from a crash: estimate from the file itself
                    try:
                        started = f.stat().st_mtime - self._segment_s
                    except FileNotFoundError:
                        continue
                seg = self._store.finalize(self.camera.name, f, started)
                if seg is not None:
                    self.segments_written += 1
                    self._on_segment(seg, started)
            if keep_newest and files:
                self.current_since = self._first_seen.get(files[-1].name)
