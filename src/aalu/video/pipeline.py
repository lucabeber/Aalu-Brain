"""GStreamer pipelines (gst-launch-1.0 argv) for one camera, recorded as MKV segments.

MKV is used instead of MP4: a segment cut short by a power loss stays playable,
while an MP4 without its final index is not. Real cameras must deliver H.264
themselves (the Pi 5 has no hardware H.264 encoder); only the simulated test
source is encoded in software, at low resolution.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from aalu.services.config import CameraConfig

# Software encoders usable for the simulated source, in order of preference.
_ENCODERS = (
    ("x264enc", ["x264enc", "tune=zerolatency", "speed-preset=ultrafast", "bitrate={kbps}",
                 "key-int-max={gop}"]),
    ("openh264enc", ["openh264enc", "bitrate={bps}", "gop-size={gop}"]),
)


def gst_available() -> bool:
    return shutil.which("gst-launch-1.0") is not None


def _has_element(name: str) -> bool:
    return subprocess.run(["gst-inspect-1.0", "--exists", name],
                          capture_output=True).returncode == 0


def software_encoder(cam: CameraConfig) -> list[str]:
    gop = max(1, cam.fps * 2)  # keyframe every 2 s: segments can only be cut at keyframes
    for element, template in _ENCODERS:
        if _has_element(element):
            return [t.format(kbps=cam.bitrate_kbps, bps=cam.bitrate_kbps * 1000, gop=gop)
                    for t in template]
    raise RuntimeError("no H.264 software encoder (install gstreamer1.0-plugins-ugly or -bad)")


def build_pipeline(cam: CameraConfig, incoming: Path, segment_s: int) -> list[str]:
    """argv for gst-launch-1.0 writing ``incoming/seg_00000.mkv``, ``seg_00001.mkv``, ..."""
    argv = [
        "gst-launch-1.0", "-e", "-q",
        "splitmuxsink", "name=mux", "muxer=matroskamux", "send-keyframe-requests=true",
        f"max-size-time={segment_s * 1_000_000_000}",
        f"location={incoming / 'seg_%05d.mkv'}",
    ]
    caps = f"width={cam.width},height={cam.height},framerate={cam.fps}/1"
    if cam.source == "test":
        argv += [
            "videotestsrc", "is-live=true", "pattern=ball", "!", f"video/x-raw,{caps}", "!",
            "clockoverlay", "time-format=%Y-%m-%d %H:%M:%S", "halignment=left",
            "valignment=bottom", "!",
            "textoverlay", f"text=SIMULATED {cam.name.upper()}", "valignment=top", "!",
            "videoconvert", "!", *software_encoder(cam), "!",
            "h264parse", "!", "queue", "!", "mux.video",
        ]
    elif cam.source == "v4l2-h264":
        # UVC camera with on-board H.264 encoder. TBD: verify caps of the chosen camera.
        argv += [
            "v4l2src", f"device={cam.device}", "!", f"video/x-h264,{caps}", "!",
            "h264parse", "config-interval=-1", "!", "queue", "!", "mux.video",
        ]
    else:
        raise ValueError(f"unknown camera source {cam.source!r}")

    if cam.audio:
        if cam.audio_source == "test":
            src = ["audiotestsrc", "is-live=true", "wave=pink-noise", "volume=0.03"]
        else:
            src = ["pulsesrc"]  # PipeWire's PulseAudio server: default microphone
        argv += [*src, "!", "audioconvert", "!", "audioresample", "!",
                 "opusenc", "bitrate=48000", "!", "queue", "!", "mux.audio_0"]
    return argv
