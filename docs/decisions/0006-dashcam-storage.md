# ADR 0006 — Dashcam recording and storage

**Status:** accepted (simulated cameras) · **Date:** 2026-10-23

## Decision
- **Separate process** `apps/video/main.py` (roadmap phase 6): a dashboard crash never stops
  recording. One supervised `gst-launch-1.0` per camera, restarted with backoff (1 → 30 s)
  when it exits, so an unplugged camera never affects the other one.
- **Container: Matroska (MKV), 60 s segments** (`splitmuxsink`, keyframe every 2 s so cuts
  are exact). Measured: after a hard kill mid-segment the file stays playable and only the
  last ~3 s before the cut are lost; earlier segments are untouched. An MP4 cut the same way
  would be unreadable.
- **Codecs:** H.264 video, Opus audio. Real cameras must output H.264 themselves (Pi 5 has
  no hardware encoder); only the simulated test source is encoded in software.
- **Audio:** the cabin microphone is recorded with one camera (front). Passengers must be
  told; footage with identifiable people or plates should not be published (GDPR).
- **Layout:**
  ```text
  <root>/<camera>/incoming/seg_NNNNN.mkv          being written
  <root>/<camera>/YYYY-MM-DD/<camera>_YYYYMMDD-HHMMSS.mkv
  <root>/<camera>/noclock/...                     no valid wall clock (no RTC battery)
  <root>/protected/<camera>/...                   "Save clip": never auto-deleted
  ```
- **Retention: 24 h.** Segments whose end is older than `retention_h` are deleted; if free
  space is still below `min_free_pct`, the oldest go first. Protected clips are never
  deleted automatically; when they exceed `protected_max_gb`, new "Save clip" requests are
  refused (and reported) instead.
- **Save clip** keeps `protect_before_s` (60 s) before and `protect_after_s` (60 s) after
  the request, for all cameras. Triggered from the dock or the Dashcam page; later also from
  an IMU shock detection.
- **Control:** UNIX socket in `$XDG_RUNTIME_DIR/aalu/video.sock` (mode 600), JSON lines
  `status` / `protect`. The dashboard polls it as the `video` source; if the service is
  down the REC indicator goes grey like any disconnected device.

## Sizing
Two cameras at 4 Mbit/s + audio ≈ 3.6 GB/h. One day of continuous recording ≈ 86 GB; in
practice the car records only while the Pi is on. A 256 GB SSD leaves room for the system,
maps and protected clips; size it when cameras and bitrates are chosen.

## Open
Live preview in the dashboard (the service will publish a low-latency local stream; latency
target < 2 s for reverse), camera selection, SSD mount and filesystem options, IMU trigger.
