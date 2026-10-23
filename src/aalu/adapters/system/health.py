"""Host health from /sys and /proc. Real on both a Linux PC and the Pi."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from aalu.adapters.base import PolledAdapter
from aalu.core.models import DataQuality, SystemReading

_THERMAL = Path("/sys/class/thermal")


def _cpu_temp_c() -> float | None:
    zones = sorted(_THERMAL.glob("thermal_zone*"))
    # Prefer the SoC zone on the Pi ("cpu-thermal"), otherwise the first readable one.
    zones.sort(key=lambda z: 0 if "cpu" in _read(z / "type") else 1)
    for zone in zones:
        raw = _read(zone / "temp")
        if raw.strip().lstrip("-").isdigit():
            return round(int(raw) / 1000.0, 1)
    return None


def _mem_used_pct() -> float | None:
    info: dict[str, int] = {}
    for line in _read(Path("/proc/meminfo")).splitlines():
        key, _, rest = line.partition(":")
        if rest.split():
            info[key] = int(rest.split()[0])
    total, avail = info.get("MemTotal"), info.get("MemAvailable")
    if not total or avail is None:
        return None
    return round(100.0 * (total - avail) / total, 1)


def _throttled() -> bool | None:
    """Pi only: any current under-voltage / throttling / frequency cap flag."""
    if not shutil.which("vcgencmd"):
        return None
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=1, check=True
        ).stdout
        return int(out.strip().split("=")[1], 16) & 0xF != 0
    except (subprocess.SubprocessError, IndexError, ValueError):
        return None


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


class SystemHealthAdapter(PolledAdapter):
    sources = ("system",)
    simulated = False
    interval_s = 5.0

    def __init__(self, data_dir: str = "/") -> None:
        super().__init__()
        self._data_dir = data_dir

    def read(self) -> SystemReading:
        try:
            free_gb = round(shutil.disk_usage(self._data_dir).free / 1e9, 1)
        except OSError:
            free_gb = None
        return SystemReading(
            quality=DataQuality.VALID,
            cpu_temp_c=_cpu_temp_c(),
            load_1m=round(os.getloadavg()[0], 2),
            mem_used_pct=_mem_used_pct(),
            disk_free_gb=free_gb,
            throttled=_throttled(),
        )
