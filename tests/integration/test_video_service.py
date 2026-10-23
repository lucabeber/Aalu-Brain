"""Recorder + service with a fake pipeline (a Python script writing segment files),
and, when GStreamer is installed, a real simulated recording."""

import shutil
import sys
import time
from pathlib import Path

import pytest

from aalu.services.config import CameraConfig, VideoConfig
from aalu.video.pipeline import build_pipeline
from aalu.video.service import VideoService, request

FAKE_PIPELINE = r"""
import sys, time, pathlib
d = pathlib.Path(sys.argv[1])
for i in range(1000):
    (d / f"seg_{i:05d}.mkv").write_bytes(b"x" * 100)
    time.sleep(float(sys.argv[2]))
"""


def fake_argv(cam, incoming: Path, segment_s: int):
    return [sys.executable, "-c", FAKE_PIPELINE, str(incoming), "0.3"]


def wait_for(cond, timeout=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def short_tmp():
    # UNIX socket paths are limited to ~107 bytes: keep the temp dir short.
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="aalu", dir="/tmp"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def make_service(root: Path, **cfg):
    from aalu.video.recorder import CameraRecorder

    config = VideoConfig(cameras=(CameraConfig("front", audio=True), CameraConfig("rear")),
                         segment_s=1, **cfg)

    def factory(cam, store, segment_s, on_segment, wall_clock):
        return CameraRecorder(cam, store, segment_s, on_segment, argv_factory=fake_argv,
                              wall_clock=wall_clock)

    return VideoService(config, root / "dc", socket_path=root / "v.sock",
                        recorder_factory=factory)


def test_service_records_reports_and_protects(short_tmp):
    svc = make_service(short_tmp, protect_before_s=60, protect_after_s=1)
    svc.start()
    try:
        assert wait_for(lambda: svc.status()["segments"] >= 4)
        st = request(svc.socket_path, "status")["status"]
        assert st["recording"] is True and {c["name"] for c in st["cameras"]} == {"front", "rear"}
        assert next(c for c in st["cameras"] if c["name"] == "front")["audio"] is True

        reply = request(svc.socket_path, "protect")
        assert reply["ok"] and reply["protected"] >= 4
        # Segments finishing within protect_after_s are protected too.
        n = reply["protected"]
        assert wait_for(lambda: svc.status()["protected_segments"] > n)
        assert request(svc.socket_path, "bogus")["ok"] is False
    finally:
        svc.stop()
    assert not svc.socket_path.exists()
    assert not list((short_tmp / "dc" / "front" / "incoming").iterdir())  # all finalized


def test_protect_refused_when_protected_quota_full(short_tmp):
    svc = make_service(short_tmp, protected_max_gb=0.0)
    svc.start()
    try:
        assert request(svc.socket_path, "protect") == {"ok": False, "protected": -1}
    finally:
        svc.stop()


def test_recorder_restarts_crashed_pipeline(short_tmp):
    from aalu.video.recorder import CameraRecorder
    from aalu.video.segments import SegmentStore

    argv = [sys.executable, "-c", "import sys; sys.exit(3)"]
    rec = CameraRecorder(CameraConfig("front"), SegmentStore(short_tmp), 1,
                         on_segment=lambda *a: None, argv_factory=lambda *a: argv)
    rec.start()
    try:
        assert wait_for(lambda: rec.restarts >= 2, timeout=8)
        assert "exited (3)" in rec.last_error
    finally:
        rec.stop()


def test_leftover_segments_finalized_on_start(short_tmp):
    from aalu.video.recorder import CameraRecorder
    from aalu.video.segments import SegmentStore

    store = SegmentStore(short_tmp)
    (store.incoming("front") / "seg_00000.mkv").write_bytes(b"x" * 10)  # power loss leftover
    rec = CameraRecorder(CameraConfig("front"), store, 60, on_segment=lambda *a: None,
                         argv_factory=fake_argv)
    rec.start()
    try:
        assert wait_for(lambda: rec.segments_written >= 1)
    finally:
        rec.stop()
    assert len(store.segments()) >= 1


@pytest.mark.skipif(shutil.which("gst-launch-1.0") is None, reason="GStreamer not installed")
def test_real_gstreamer_test_source_records_playable_mkv_with_audio(short_tmp):
    cam = CameraConfig("front", width=320, height=180, fps=10, bitrate_kbps=200, audio=True)
    try:
        build_pipeline(cam, short_tmp, 2)
    except RuntimeError as exc:
        pytest.skip(str(exc))
    svc = VideoService(VideoConfig(cameras=(cam,), segment_s=2), short_tmp / "dc",
                       socket_path=short_tmp / "v.sock")
    svc.start()
    try:
        assert wait_for(lambda: svc.status()["segments"] >= 2, timeout=20)
    finally:
        svc.stop()
    seg = svc.store.segments()[0].path
    if shutil.which("gst-discoverer-1.0"):
        import subprocess
        out = subprocess.run(["gst-discoverer-1.0", str(seg)], capture_output=True,
                             text=True, timeout=20).stdout
        assert "H.264" in out and "Opus" in out
