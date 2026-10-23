"""Typed application configuration loaded from TOML (config/*.toml)."""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aalu.core.alarms import Severity, ThresholdRule
from aalu.core.state_store import Freshness

SCREEN_LAYOUTS = ("auto", "single", "dual")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class WindowConfig:
    """``fullscreen`` takes whatever resolution the screen has; width/height are used
    only for windowed development."""

    screen: int = 0
    fullscreen: bool = True
    width: int = 1280
    height: int = 720
    x: int | None = None
    y: int | None = None


@dataclass(frozen=True)
class MapConfig:
    # Raster tiles in z/x/y.png layout. The default is the public OSM server: fine for
    # light personal use with a real User-Agent, never for bulk/offline pre-download.
    tile_url: str = "https://tile.openstreetmap.org/"
    user_agent: str = "AALU-dashboard/0.1 (private camper project)"
    cache_dir: str = ""  # "" = Qt default cache location
    cache_size_mb: int = 500
    offline_dir: str = ""  # pre-rendered tiles usable without network
    attribution: str = "© OpenStreetMap contributors"
    # Fetch tiles through the local HTTP/1.1 proxy (works around Qt HTTP/2 tile drops).
    proxy: bool = True


@dataclass(frozen=True)
class CameraConfig:
    name: str
    source: str = "test"  # test (simulated) | v4l2-h264 (camera encodes H.264 itself)
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    bitrate_kbps: int = 4000  # used by the software encoder of the test source only
    audio: bool = False  # record the cabin microphone into this camera's files
    audio_source: str = "test"  # test | pulse (PipeWire/PulseAudio default microphone)


@dataclass(frozen=True)
class VideoConfig:
    enabled: bool = True
    root_dir: str = "data/dashcam"
    segment_s: int = 60
    retention_h: float = 5.0  # normal segments older than this are deleted
    min_free_pct: float = 10.0  # also delete the oldest segments below this free space
    protected_max_gb: float = 20.0  # protected clips are never deleted; beyond this, no new ones
    protect_before_s: int = 60  # "Save clip" keeps this much before ...
    protect_after_s: int = 60  # ... and after the request
    long_protect_before_s: int = 300  # "Save 15 min": the last 5 minutes ...
    long_protect_after_s: int = 600  # ... and the next 10
    socket: str = ""  # "" = $XDG_RUNTIME_DIR/aalu/video.sock
    cameras: tuple[CameraConfig, ...] = ()

    @property
    def simulated(self) -> bool:
        return any(c.source == "test" for c in self.cameras)


@dataclass(frozen=True)
class AppConfig:
    gnss: dict[str, Any] = field(default_factory=lambda: {"adapter": "fake"})
    victron: dict[str, Any] = field(default_factory=lambda: {"adapter": "fake"})
    media: dict[str, Any] = field(default_factory=lambda: {"adapter": "fake"})
    mcu: dict[str, Any] = field(default_factory=lambda: {"adapter": "fake"})
    system: dict[str, Any] = field(default_factory=lambda: {"adapter": "real", "data_dir": "/"})
    battery_capacity_ah: float = 200.0
    navigation_command: list[str] = field(default_factory=list)
    camp_idle_timeout_s: float = 0.0  # 0 = never go to STANDBY automatically
    freshness: dict[str, Freshness] = field(default_factory=dict)
    alarm_rules: list[ThresholdRule] = field(default_factory=list)
    battery_reserve_soc_pct: float = 10.0
    sim_time_scale: float = 1.0
    map: MapConfig = MapConfig()
    video: VideoConfig = VideoConfig()
    screen_layout: str = "auto"  # auto | single | dual
    drive_window: WindowConfig = WindowConfig(fullscreen=True)
    camper_window: WindowConfig = WindowConfig(screen=1, fullscreen=True)
    night_mode: bool = True
    # Relative paths in the config (e.g. the fake GNSS route) are resolved against this.
    base_dir: Path = Path(".")

    def resolve(self, path: str) -> Path:
        p = Path(path).expanduser()
        return p if p.is_absolute() else self.base_dir / p


def load_config(path: str | Path, base_dir: str | Path | None = None) -> AppConfig:
    """``base_dir``: where relative paths point (default: the parent of the config's folder,
    i.e. the repository root for files in config/)."""
    try:
        raw = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    base = Path(base_dir) if base_dir is not None else Path(path).resolve().parent.parent
    return dataclasses.replace(parse_config(raw), base_dir=base)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    try:
        adapters = raw.get("adapters", {})
        ui = raw.get("ui", {})
        return AppConfig(
            gnss=adapters.get("gnss", {"adapter": "fake"}),
            victron=adapters.get("victron", {"adapter": "fake"}),
            media=adapters.get("media", {"adapter": "fake"}),
            mcu=adapters.get("mcu", {"adapter": "fake"}),
            system=adapters.get("system", {"adapter": "real", "data_dir": "/"}),
            battery_capacity_ah=float(raw.get("battery", {}).get("capacity_ah", 200.0)),
            battery_reserve_soc_pct=float(raw.get("battery", {}).get("reserve_soc_pct", 10.0)),
            sim_time_scale=float(raw.get("simulation", {}).get("time_scale", 1.0)),
            map=MapConfig(**raw.get("map", {})),
            video=_video(raw.get("video", {})),
            navigation_command=list(raw.get("navigation", {}).get("command", [])),
            camp_idle_timeout_s=float(raw.get("modes", {}).get("camp_idle_timeout_s", 0.0)),
            freshness={
                name: Freshness(float(v["stale_after_s"]), float(v["disconnected_after_s"]))
                for name, v in raw.get("freshness", {}).items()
            },
            alarm_rules=[
                ThresholdRule(
                    id=r["id"], source=r["source"], field=r["field"],
                    direction=r["direction"], set_at=float(r["set_at"]),
                    clear_at=float(r["clear_at"]), severity=Severity(r["severity"]),
                    message=r["message"],
                )
                for r in raw.get("alarms", [])
            ],
            screen_layout=_choice(ui.get("layout", "auto"), SCREEN_LAYOUTS, "ui.layout"),
            drive_window=WindowConfig(**ui.get("drive", {})),
            camper_window=WindowConfig(**{"screen": 1, **ui.get("camper", {})}),
            night_mode=bool(ui.get("night_mode", True)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"invalid configuration: {exc!r}") from exc


def _choice(value: str, allowed: tuple[str, ...], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}, not {value!r}")
    return value


def _video(raw: dict[str, Any]) -> VideoConfig:
    cams = tuple(CameraConfig(**c) for c in raw.get("cameras", []))
    names = [c.name for c in cams]
    if len(set(names)) != len(names) or not all(n.isidentifier() for n in names):
        raise ValueError("video.cameras: names must be unique identifiers")
    for c in cams:
        _choice(c.source, ("test", "v4l2-h264"), f"video.cameras.{c.name}.source")
        _choice(c.audio_source, ("test", "pulse"), f"video.cameras.{c.name}.audio_source")
    if sum(c.audio for c in cams) > 1:
        raise ValueError("video.cameras: only one camera can record the microphone")
    rest = {k: v for k, v in raw.items() if k != "cameras"}
    video = VideoConfig(**rest, cameras=cams)
    longest_before = max(video.protect_before_s, video.long_protect_before_s)
    if video.retention_h * 3600 <= longest_before + video.segment_s:
        # The segments a save reaches back to must still exist when it is requested.
        raise ValueError("video.retention_h must be longer than the protect windows")
    return video
