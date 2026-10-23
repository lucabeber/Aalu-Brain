#!/usr/bin/env bash
# Start the AALU dashboard when the desktop session starts (Raspberry Pi OS Desktop).
# Uses a standard XDG autostart entry; remove it with: scripts/install_autostart.sh --remove
# Not yet verified on the target Pi: check after the first reboot.
set -euo pipefail
cd "$(dirname "$0")/.."

entry="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/aalu-dashboard.desktop"

if [[ "${1:-}" == "--remove" ]]; then
    rm -f "$entry" && echo "Removed $entry"
    exit 0
fi

config="${AALU_CONFIG:-config/pi.toml}"
[[ -f "$config" ]] || { echo "Missing $config (cp config/pi.toml.example config/pi.toml)" >&2; exit 1; }

mkdir -p "$(dirname "$entry")"
cat > "$entry" <<EOF
[Desktop Entry]
Type=Application
Name=AALU dashboard
Comment=Drive and camper dashboards
Exec=/usr/bin/env AALU_CONFIG=$PWD/$config $PWD/scripts/run_demo.sh
X-GNOME-Autostart-enabled=true
EOF
echo "Installed $entry (log: journalctl --user -b or run scripts/run_demo.sh by hand)"
