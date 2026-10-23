"""Typed data contracts exchanged between adapters, core and UI.

Every reading carries ``schema_version``, ``source``, ``ts_utc`` and ``quality``
(see roadmap §3 "Contratti minimi dei dati"). Measured fields are ``None`` when
unknown: never substitute an old or invented value.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

SCHEMA_VERSION = 1


class DataQuality(StrEnum):
    VALID = "valid"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    SIMULATED = "simulated"

    @property
    def is_live(self) -> bool:
        """True when values are current measurements (real or simulated)."""
        return self in (DataQuality.VALID, DataQuality.SIMULATED)


class GnssFix(StrEnum):
    NO_FIX = "no_fix"
    FIX_2D = "2d"
    FIX_3D = "3d"


class PhoneLink(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"


class PlaybackStatus(StrEnum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class Reading:
    """Base envelope. Subclasses add the measured fields."""

    schema_version: ClassVar[int] = SCHEMA_VERSION
    source: str
    quality: DataQuality
    ts_utc: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema_version": self.schema_version}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, datetime):
                value = value.isoformat().replace("+00:00", "Z")
            elif isinstance(value, StrEnum):
                value = value.value
            elif isinstance(value, dict):
                value = dict(value)
            elif isinstance(value, list):
                value = list(value)
            out[f.name] = value
        return out

    def measured_fields(self) -> dict[str, Any]:
        """Fields other than the envelope, as plain JSON-friendly values."""
        d = self.to_dict()
        for key in ("schema_version", "source", "quality", "ts_utc"):
            d.pop(key, None)
        return d


@dataclass(frozen=True, kw_only=True)
class GnssReading(Reading):
    source: str = "gnss"
    fix: GnssFix = GnssFix.NO_FIX
    satellites: int | None = None
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    speed_kmh: float | None = None
    heading_deg: float | None = None
    hdop: float | None = None
    # Time reported by the receiver, only when it has a valid fix.
    gnss_time_utc: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class BatteryReading(Reading):
    source: str = "house_battery"
    voltage_v: float | None = None
    current_a: float | None = None  # positive = charging
    power_w: float | None = None
    soc_pct: float | None = None
    consumed_ah: float | None = None
    # Only what the monitor itself reports (e.g. SmartShunt TTG); never extrapolated here.
    time_to_go_min: float | None = None


@dataclass(frozen=True, kw_only=True)
class SolarReading(Reading):
    source: str = "solar"
    pv_power_w: float | None = None
    pv_voltage_v: float | None = None
    battery_current_a: float | None = None
    yield_today_kwh: float | None = None
    charge_state: str | None = None


@dataclass(frozen=True, kw_only=True)
class DcDcReading(Reading):
    """Alternator -> house battery DC-DC charger (e.g. Victron Orion XS)."""

    source: str = "dcdc"
    input_voltage_v: float | None = None  # starter battery / alternator side
    output_voltage_v: float | None = None
    output_current_a: float | None = None
    charge_state: str | None = None  # "off", "bulk", "absorption", "float"


@dataclass(frozen=True, kw_only=True)
class TankReading(Reading):
    source: str = "fresh_water"
    level_pct: float | None = None
    capacity_l: float | None = None


@dataclass(frozen=True, kw_only=True)
class MediaReading(Reading):
    source: str = "media"
    link: PhoneLink = PhoneLink.DISCONNECTED
    device_name: str | None = None
    status: PlaybackStatus = PlaybackStatus.STOPPED
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    position_ms: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, kw_only=True)
class AudioOutputReading(Reading):
    source: str = "audio_output"
    volume_pct: int | None = None
    muted: bool | None = None
    eq_preset: str | None = None


@dataclass(frozen=True, kw_only=True)
class VehicleInputsReading(Reading):
    """Protected/isolated vehicle inputs, read by the I/O MCU."""

    source: str = "vehicle_inputs"
    acc_on: bool | None = None
    reverse: bool | None = None


@dataclass(frozen=True, kw_only=True)
class LoadsReading(Reading):
    """Output states *as confirmed by the MCU* (not what the UI requested)."""

    source: str = "loads"
    outputs: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SystemReading(Reading):
    source: str = "system"
    cpu_temp_c: float | None = None
    load_1m: float | None = None
    mem_used_pct: float | None = None
    disk_free_gb: float | None = None
    throttled: bool | None = None


@dataclass(frozen=True, kw_only=True)
class VideoReading(Reading):
    """Status of the separate dashcam service."""

    source: str = "video"
    recording: bool | None = None
    cameras: list[dict] = field(default_factory=list)  # name, state, audio, last_error...
    disk_free_gb: float | None = None
    disk_free_pct: float | None = None
    used_gb: float | None = None
    segments: int | None = None
    oldest_age_h: float | None = None
    retention_h: float | None = None
    protected_segments: int | None = None
    protected_gb: float | None = None
    protected_max_gb: float | None = None
    protecting: bool | None = None
    protect_remaining_s: int | None = None  # seconds still being added to the saved clip
