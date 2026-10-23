"""AALU dashcam service: records every configured camera, independent of the dashboard.

    python apps/video/main.py --config config/dev.toml
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))  # run from a checkout without installing

from aalu.services.config import load_config  # noqa: E402
from aalu.video.pipeline import gst_available  # noqa: E402
from aalu.video.service import VideoService  # noqa: E402

log = logging.getLogger("aalu.video")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AALU dashcam recording service")
    p.add_argument("--config", default=str(ROOT / "config" / "dev.toml"))
    p.add_argument("--log-level", default=os.environ.get("AALU_LOG_LEVEL", "INFO"))
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config(args.config, base_dir=ROOT)
    video = config.video
    if not video.enabled or not video.cameras:
        log.info("video disabled in %s", args.config)
        return 0
    if not gst_available():
        log.error("gst-launch-1.0 not found: sudo apt install gstreamer1.0-tools "
                  "gstreamer1.0-plugins-good gstreamer1.0-plugins-bad")
        return 1

    service = VideoService(video, config.resolve(video.root_dir))
    done = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: done.set())
    service.start()
    done.wait()
    log.info("stopping: closing current segments")
    service.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
