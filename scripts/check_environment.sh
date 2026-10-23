#!/usr/bin/env bash
# Report whether this machine can run/develop AALU. Exits non-zero on blocking problems.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
ok()   { printf '  \e[32mOK\e[0m    %s\n' "$*"; }
warn() { printf '  \e[33mWARN\e[0m  %s\n' "$*"; }
bad()  { printf '  \e[31mFAIL\e[0m  %s\n' "$*"; fail=1; }

echo "System"
ok "$(uname -srm)"
[[ -r /etc/os-release ]] && ok "$(. /etc/os-release; echo "$PRETTY_NAME")"
if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    ok "board: $(tr -d '\0' < /proc/device-tree/model)"
    if command -v vcgencmd >/dev/null; then
        ok "temp $(vcgencmd measure_temp | cut -d= -f2), throttled=$(vcgencmd get_throttled | cut -d= -f2)"
    fi
fi

echo "Python"
if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"
else
    bad "python3 >= 3.11 required"
fi
[[ -n "${PYTHONPATH:-}" ]] && warn "PYTHONPATH is set ($PYTHONPATH); scripts unset it"
if [[ -x .venv/bin/python ]]; then
    ok ".venv present"
    if env -u PYTHONPATH .venv/bin/python -c 'import PySide6' 2>/dev/null; then
        ok "PySide6 $(env -u PYTHONPATH .venv/bin/python -c 'import PySide6; print(PySide6.__version__)')"
    else
        bad "PySide6 missing in .venv (run scripts/run_demo.sh once)"
    fi
    env -u PYTHONPATH .venv/bin/python -c 'import serial' 2>/dev/null \
        && ok "pyserial installed" || warn "pyserial missing (only needed for a real GNSS: pip install -e .[serial])"
else
    warn ".venv missing (scripts/run_demo.sh creates it)"
fi

echo "Display"
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then ok "Wayland session ($WAYLAND_DISPLAY)"
elif [[ -n "${DISPLAY:-}" ]]; then ok "X11 session ($DISPLAY)"
else warn "no graphical session (use QT_QPA_PLATFORM=offscreen for tests)"; fi
for status in /sys/class/drm/card*-HDMI-A-*/status; do
    [[ -r "$status" ]] && ok "$(basename "$(dirname "$status")"): $(cat "$status")"
done

echo "Serial devices (GNSS / VE.Direct / MCU)"
found=0
for dev in /dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA0; do
    [[ -e "$dev" ]] && { ok "$dev"; found=1; }
done
[[ $found == 0 ]] && warn "none found"
id -nG | grep -qw dialout && ok "user in group dialout" || warn "user not in group dialout (serial access)"

echo "Bluetooth / audio"
command -v bluetoothctl >/dev/null && ok "bluetoothctl" || warn "bluez not installed"
command -v wpctl >/dev/null && ok "wpctl (PipeWire/WirePlumber)" || warn "wpctl not found"

exit $fail
