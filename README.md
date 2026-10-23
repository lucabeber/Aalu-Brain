# AALU — on-board computer

Drive and camper dashboards for a Mercedes-Benz G 280 camper conversion, running on a
Raspberry Pi 5. The plan and its rules are in [`AALU_Roadmap_Sviluppo.md`](AALU_Roadmap_Sviluppo.md).

**Status: simulated version.** Every device (GPS, Victron battery/solar/DC-DC, phone,
I/O controller) is simulated and clearly labelled **SIMULATED**; the UI runs the same on a
Linux PC and on the Pi with an HDMI touchscreen. No hardware integration yet.

## What you get

**Drive view** (Android Auto style): a dock on the left (bottom on portrait screens) and a
moving map that follows the car, in three layouts — the choice is remembered:

| Dock button | Layout |
|---|---|
| Map | full-screen map with speed |
| Music | ¾ map + ¼ music player (track, controls, volume) |
| Energy | ¾ map + ¼ battery %, solar, engine charging, consumption, time to full/empty |

plus Camera (rear/front, opens automatically on reverse), Navigate (starts Pure Maps full
screen, when configured) and Camper (single-screen mode).

**Offline maps**: build a map pack once at home, then map, search and routing work with
no Internet ([ADR 0007](docs/decisions/0007-offline-maps-without-pure-maps.md)):

```bash
.venv/bin/pip install -e ".[maps]"        # routing (Valhalla), OSM reader, map file reader
scripts/build_map_pack.py trentino-alto-adige    # ≈ 3 min and 500 MB; also: italy, alps, ...
```

Packs go to `data/maps/` (`[map] maps_dir`; on the Pi e.g. the SSD). With a pack the drive view
shows the offline vector map (needs a GPU with WebGL2); without one it falls back to the
online map.

**Navigation** (tap *Where to?* on the map; offline with a map pack):
- **Route**: *From* (current location by default, or a searched place) and *To*; or
  long-press the map → *Go here* / *Set as start*. Options: no motorways / tolls / ferries /
  unpaved. Turn-by-turn instructions, recalculation when you leave the route, arrival time.
  A route from another start is a *planned* route: *Start* (from here) or *Save trip*.
- **Trips**: every navigation is saved in `data/trips/<date>_<time>_<from>-<to>/` with the
  planned route (`route.gpx`), the driven track (`track.gpx`) and the metadata (`trip.json`:
  places, options, planned and driven distance/time, speeds, status). *Drive from here* or
  *Show* reopens one.
- **GPX**: your files in `data/gpx/` (subfolders too) are listed and searchable by name,
  place or date. Loading one snaps it to the roads where it follows them (turn instructions)
  and keeps the original track where it goes off-road (orange on the map, "follow the GPX
  track" guidance); you are routed to its start and back to it if you leave it.
- Typing is disabled while the vehicle moves (switch *Ignition* off on the Simulation page to
  try it). On the Pi an on-screen keyboard appears (`[ui] virtual_keyboard`; PC: `--keyboard on`).

**Camper view**: Energy, Water, Lights, Audio, Alarms, Diagnostics and Simulation pages.
The Energy page shows the battery %, what the solar panels and the engine (alternator via
DC-DC) put in, what is being consumed, the net sum, and how long until full (net positive)
or until the reserve level (net negative).

**Dashcam**: a separate recording service (started by `run_demo.sh`) records every camera
with sound from the cabin microphone into 1-minute MKV files and keeps the last **5 hours**.
Two buttons (dock and Dashcam page) save footage that is never deleted automatically:
**Save clip** = last minute + next minute, **Save 15 min** = last 5 minutes + next 10. With
simulated cameras it records a GStreamer test picture. Files are in `data/dashcam/` on the
PC (`~/aalu-data/dashcam` on the Pi); see [ADR 0006](docs/decisions/0006-dashcam-storage.md).

**Screens**: windows go full screen and adapt to the resolution and orientation of the
attached display (scaled down below 1100×680, e.g. 800×480 panels). One screen → one
window with a Drive/Camper switch; two screens → drive on HDMI 0, camper on HDMI 1.

## Run on a Linux PC

```bash
scripts/check_environment.sh    # what this machine has / lacks
scripts/run_demo.sh             # creates .venv on first run, then starts
```

Requirements: Python ≥ 3.12 and `python3-venv` (or [`uv`](https://docs.astral.sh/uv/));
GStreamer (`gstreamer1.0-tools` + good/bad/ugly plugins) for the dashcam. Without it the
dashboard still runs and the dashcam shows "not running".
The map needs Internet the first time an area is shown; viewed tiles are cached on disk.

## Run on the Raspberry Pi 5 (Raspberry Pi OS Desktop)

```bash
sudo apt install -y git python3-venv gstreamer1.0-tools gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
git clone <this repo> ~/aalu && cd ~/aalu
cp config/pi.toml.example config/pi.toml
AALU_CONFIG=config/pi.toml scripts/run_demo.sh
scripts/install_autostart.sh    # optional: start the dashboard at login
```

Connect the touchscreen to HDMI 0 (next to USB-C power) and its USB cable for touch.
`Ctrl+Q` quits, `F11` toggles full screen (keyboard only). To use a portrait screen, rotate
it in *Screen Configuration*: the layout follows.

## Options

| Option | Effect |
|---|---|
| `--layout single\|dual\|auto` | one window with switch / two windows / by number of screens |
| `--view camper` | start the single window on the camper view |
| `--page dashcam` | camper page shown first |
| `--search "Riva del Garda" [--go]` | search at startup (and route to the first result) |
| `--gpx bondone-mixed.gpx [--go]` | load a GPX from the library (sample in `assets/sample-data/gpx`) |
| `--panel route\|trips\|gpx` | open the navigation panel on a tab |
| `--map-engine qtlocation` | use the online Qt map instead of the offline vector map |
| `--keyboard on\|off` | on-screen keyboard |
| `AALU_NO_VIDEO=1` | (environment) do not start the dashcam service |
| `--only drive` / `--only camper` | open only one view |
| `--sim gnss_fix=false` | start with a fault injected (repeatable; keys below) |
| `--config FILE` | another configuration |
| `--quit-after 5 --screenshot-dir out/` | headless run with PNGs (`QT_QPA_PLATFORM=offscreen`) |

Simulation keys, also switchable live on the camper **Simulation** page: `acc_on`,
`engine_running`, `sunny`, `reverse`, `gnss_connected`, `gnss_fix`, `victron_connected`,
`low_soc`, `phone_connected`, `mcu_connected`. Switching lights or the water pump on adds
their current to the simulated consumption. `[simulation] time_scale` speeds up the battery.

## Tests

```bash
unset PYTHONPATH                     # e.g. ROS on the path breaks pytest plugins
.venv/bin/ruff check src apps tests
.venv/bin/pytest                     # unit + simulated scenarios + QML smoke runs
```

CI (`.github/workflows/ci.yml`) runs the same on Python 3.12 and 3.13 (Trixie's version).

## Layout

```text
apps/dashboard/        main.py (windows/screens) + QML (screens/, components/, js/)
apps/video/            main.py: dashcam recording service (separate process)
src/aalu/video/        GStreamer pipelines, recorder supervisor, segment store, service
src/aalu/core/         data contracts, quality/staleness store, mode state machine, alarms
src/aalu/adapters/     one folder per device: fake.py (simulated) + real adapters
src/aalu/services/     configuration, energy balance, VehicleCore (Qt-free)
src/aalu/ui/bridge.py  Qt bridge: state to QML, touch commands back
config/                dev.toml (PC), pi.toml.example (Pi)
assets/sample-data/    road loop driven by the simulated GPS
docs/                  requirements, architecture, hardware inventory, acceptance tests, ADRs
tests/                 unit/, simulated/, integration/
```

## Rules the code enforces

- Unknown values are `None` and shown as `—`; no stale number is presented as current.
- Every source is `valid`, `simulated`, `stale`, `disconnected` or `error`; ageing uses a
  monotonic clock, so a wrong wall clock (no RTC battery, offline) cannot make data look fresh.
- Simulated data is always labelled **SIMULATED**.
- GNSS without a fix reports no position, speed, heading or receiver time.
- Consumption and time estimates are shown only when the inputs they need are live.
- Load commands show the state *confirmed by the I/O controller*, not the one requested.
- Each hardware integration has a fake and a real adapter behind the same interface.

See [`docs/architecture.md`](docs/architecture.md) for details.
