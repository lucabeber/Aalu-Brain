"""Dashboard side of the dashcam: polls the video service over its UNIX socket.

If the service is not running, nothing is published and the ``video`` source
goes stale and then disconnected (REC indicator grey), as for any device.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aalu.adapters.base import PolledAdapter
from aalu.core.models import DataQuality, VideoReading
from aalu.video.service import request

log = logging.getLogger(__name__)


class VideoServiceAdapter(PolledAdapter):
    sources = ("video",)
    interval_s = 1.0

    def __init__(self, socket_path: Path, simulated: bool) -> None:
        super().__init__()
        self._socket = socket_path
        self.simulated = simulated  # simulated cameras: data labelled SIMULATED

    def read(self) -> VideoReading | None:
        try:
            reply = request(self._socket, "status")
        except OSError:
            return None
        st = reply.get("status") or {}
        error = any(c.get("state") in ("restarting", "error") for c in st.get("cameras", []))
        quality = DataQuality.ERROR if error else (
            DataQuality.SIMULATED if self.simulated else DataQuality.VALID)
        fields = {k: st.get(k) for k in (
            "recording", "disk_free_gb", "disk_free_pct", "used_gb", "segments",
            "oldest_age_h", "retention_h", "protected_segments", "protected_gb",
            "protected_max_gb", "protecting")}
        return VideoReading(quality=quality, cameras=st.get("cameras", []), **fields)

    # VideoController
    def protect(self) -> bool:
        try:
            return bool(request(self._socket, "protect").get("ok"))
        except OSError:
            log.warning("save clip: video service not reachable")
            return False
