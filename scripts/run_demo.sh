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
        .venv/bin/pip install -q -e ".[dev]"
    elif command -v uv >/dev/null; then
        rm -rf .venv && uv venv -q .venv && uv pip install -q --python .venv/bin/python -e ".[dev]"
    else
        echo "Need python3-venv (sudo apt install python3-venv) or uv." >&2
        exit 1
    fi
fi

exec .venv/bin/python apps/dashboard/main.py --config "${AALU_CONFIG:-config/dev.toml}" "$@"
