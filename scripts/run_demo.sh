#!/usr/bin/env bash
# Run the AALU dashboards with simulated data on a Linux PC.
#   scripts/run_demo.sh [extra args for main.py, e.g. --only drive --sim gnss_fix=false]
set -euo pipefail
cd "$(dirname "$0")/.."

# Foreign Python paths (e.g. ROS) can break imports and pytest plugins.
unset PYTHONPATH

if [[ ! -x .venv/bin/python ]]; then
    echo "Creating .venv ..."
    if python3 -m venv .venv 2>/dev/null; then
        .venv/bin/pip install -q -e ".[dev,maps]"
    elif command -v uv >/dev/null; then
        rm -rf .venv && uv venv -q .venv && uv pip install -q --python .venv/bin/python -e ".[dev,maps]"
    else
        echo "Need python3-venv (sudo apt install python3-venv) or uv." >&2
        exit 1
    fi
fi

config="${AALU_CONFIG:-config/dev.toml}"

# Dashcam recording runs as its own process, so a dashboard crash never stops it.
# AALU_NO_VIDEO=1 skips it (e.g. when it already runs as a service).
if [[ -z "${AALU_NO_VIDEO:-}" ]] && command -v gst-launch-1.0 >/dev/null; then
    .venv/bin/python apps/video/main.py --config "$config" &
    video_pid=$!
    trap 'kill -TERM $video_pid 2>/dev/null; wait $video_pid 2>/dev/null' EXIT
elif [[ -z "${AALU_NO_VIDEO:-}" ]]; then
    echo "GStreamer not installed: dashcam disabled (sudo apt install gstreamer1.0-tools" \
         "gstreamer1.0-plugins-good gstreamer1.0-plugins-bad)" >&2
fi

.venv/bin/python apps/dashboard/main.py --config "$config" "$@"
