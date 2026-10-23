"""Dashcam storage layout, retention and protection.

    <root>/<camera>/incoming/seg_00000.mkv        being written by GStreamer
    <root>/<camera>/2026-10-23/front_20261023-164000.mkv   finished segments
    <root>/protected/<camera>/front_20261023-164000.mkv    "Save clip": never auto-deleted

Retention: a finished segment older than ``retention_h`` (by modification time,
i.e. the end of the segment) is deleted; if free space is still below
``min_free_pct``, the oldest finished segments go first. Protected segments are
never deleted automatically.

Without a valid wall clock (Pi without RTC battery, offline) names use
``noclock-<n>`` instead of an invented 1970 date.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

MIN_VALID_EPOCH = datetime(2024, 1, 1).timestamp()


@dataclass(frozen=True)
class Segment:
    path: Path
    camera: str
    size: int
    mtime: float
    protected: bool


class SegmentStore:
    def __init__(self, root: Path, wall_clock: Callable[[], float] = time.time) -> None:
        self.root = root
        self._wall = wall_clock
        self._noclock_counter = 0

    # --- layout ---------------------------------------------------------
    def incoming(self, camera: str) -> Path:
        path = self.root / camera / "incoming"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def protected_dir(self, camera: str) -> Path:
        path = self.root / "protected" / camera
        path.mkdir(parents=True, exist_ok=True)
        return path

    def finalize(self, camera: str, path: Path, started_at: float) -> Segment | None:
        """Move a finished incoming segment to its dated folder. Empty files are dropped."""
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return None
        if size == 0:
            path.unlink(missing_ok=True)
            return None
        if started_at >= MIN_VALID_EPOCH:
            start = datetime.fromtimestamp(started_at)
            folder = self.root / camera / start.strftime("%Y-%m-%d")
            stem = f"{camera}_{start.strftime('%Y%m%d-%H%M%S')}"
        else:
            self._noclock_counter += 1
            folder = self.root / camera / "noclock"
            stem = f"{camera}_noclock-{int(time.monotonic())}-{self._noclock_counter}"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{stem}.mkv"
        n = 1
        while target.exists():
            target = folder / f"{stem}_{n}.mkv"
            n += 1
        os.replace(path, target)
        st = target.stat()
        return Segment(target, camera, st.st_size, st.st_mtime, protected=False)

    # --- queries --------------------------------------------------------
    def segments(self, protected: bool = False) -> list[Segment]:
        out: list[Segment] = []
        if protected:
            base = self.root / "protected"
            files = base.glob("*/*.mkv") if base.exists() else []
        else:
            files = (p for p in self.root.glob("*/*/*.mkv")
                     if p.parent.name != "incoming" and p.parts[-3] != "protected")
        for p in files:
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            camera = p.parent.name if protected else p.parent.parent.name
            out.append(Segment(p, camera, st.st_size, st.st_mtime, protected))
        return sorted(out, key=lambda s: s.mtime)

    def disk_usage(self) -> tuple[float, float]:
        """(free GB, free %) of the filesystem holding the recordings."""
        self.root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self.root)
        return usage.free / 1e9, 100.0 * usage.free / usage.total

    # --- protection -----------------------------------------------------
    def protect(self, segment: Segment) -> Path:
        target = self.protected_dir(segment.camera) / segment.path.name
        os.replace(segment.path, target)
        log.info("protected %s", target)
        return target

    def protected_bytes(self) -> int:
        return sum(s.size for s in self.segments(protected=True))

    # --- retention ------------------------------------------------------
    def enforce_retention(self, retention_h: float, min_free_pct: float,
                          free_pct: Callable[[], float] | None = None) -> list[Path]:
        free_pct = free_pct or (lambda: self.disk_usage()[1])
        now = self._wall()
        deleted: list[Path] = []
        remaining: list[Segment] = []
        for seg in self.segments():
            # A segment "from the future" means the clock jumped back: keep it, never guess.
            if now - seg.mtime > retention_h * 3600:
                deleted.append(self._delete(seg))
            else:
                remaining.append(seg)
        while remaining and free_pct() < min_free_pct:
            deleted.append(self._delete(remaining.pop(0)))
        self._remove_empty_dirs()
        if deleted:
            log.info("retention: deleted %d segment(s)", len(deleted))
        return deleted

    def _delete(self, seg: Segment) -> Path:
        seg.path.unlink(missing_ok=True)
        return seg.path

    def _remove_empty_dirs(self) -> None:
        for d in self.root.glob("*/*"):
            if d.is_dir() and d.name != "incoming" and d.parent.name != "protected":
                with contextlib.suppress(OSError):
                    d.rmdir()  # only succeeds when empty
