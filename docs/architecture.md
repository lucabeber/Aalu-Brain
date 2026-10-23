# Architecture

One modular Python backend in the dashboard process, plus separate processes only where
isolation matters (video service, navigation app, future hardware supervisor). See
[ADR 0001](decisions/0001-stack-qt-python-single-backend.md).

```text
 adapter threads                     GUI thread
 ───────────────                     ──────────────────────────────────────────────
 FakeGnss / NmeaSerialAdapter ─┐
 FakeVictron (battery, solar) ─┤  publish()   Backend._reading     VehicleCore.ingest()
 FakePhone, FakeAudioOutput ───┼──(any thread)──► (queued Qt ──►  ├─ StateStore.update()
 FakeMcu (inputs,tanks,loads) ─┤               signal)            ├─ ModeMachine (ACC)
 SystemHealthAdapter ──────────┘                                  ├─ AlarmEngine
                                                                  └─ listeners(topics)
                                     QTimer 1 Hz ──► VehicleCore.tick()      │
                                                     (ageing, timeouts)      ▼
                                                              Backend → QQmlPropertyMap "Vehicle"
                                                                         │
                                     QML Drive window ◄──────────────────┤
                                     QML Camper window ◄─────────────────┘
                                     touch ──► Backend slots ──► MediaController /
                                                                 AudioOutputController /
                                                                 LoadController (MCU)
```

## Data contracts (`src/aalu/core/models.py`)

Each reading is a frozen dataclass with the envelope `schema_version`, `source`,
`ts_utc`, `quality`, plus measured fields that are `None` when unknown.
`Reading.to_dict()` produces the JSON shape in roadmap §3.

| Source id | Reading | Producer today |
|---|---|---|
| `gnss` | `GnssReading` (fix, satellites, lat/lon, alt, speed, heading, hdop, receiver time) | fake, NMEA serial, NMEA replay |
| `house_battery` | `BatteryReading` (V, A, W, SOC, Ah, time-to-go from the monitor) | fake |
| `solar` | `SolarReading` (PV W/V, charge A, yield, state) | fake |
| `dcdc` | `DcDcReading` (engine → house battery charger: output A, state) | fake |
| `fresh_water`, `grey_water` | `TankReading` (level %, capacity) | fake MCU |
| `media` | `MediaReading` (link, device, status, metadata, position) | fake phone |
| `audio_output` | `AudioOutputReading` (volume, mute, EQ preset) | fake |
| `vehicle_inputs` | `VehicleInputsReading` (ACC, reverse) | fake MCU |
| `loads` | `LoadsReading` (output → confirmed bool) | fake MCU |
| `system` | `SystemReading` (CPU temp, load, RAM, disk, throttling) | real (/sys, /proc, vcgencmd) |

## Data quality ([ADR 0002](decisions/0002-data-quality-and-staleness.md))

The adapter sets `valid`, `simulated` or `error`. The `StateStore` downgrades by age:
`stale` after `stale_after_s`, `disconnected` after `disconnected_after_s` (per source in
`[freshness.*]`). An adapter that loses its device simply stops publishing. Views sent to QML
keep values while `stale` (dimmed in the UI) and drop them when `disconnected`/`error`.

## Vehicle mode ([ADR 0003](decisions/0003-vehicle-mode-state-machine.md))

`ModeMachine` is a transition table over DRIVE, CAMP, STANDBY, SHUTDOWN, FAULT. ACC edges
come from the `vehicle_inputs` source. At boot the first input reading decides: ACC on →
DRIVE, ACC off → CAMP. Reverse is not a mode: it is an overlay on the drive screen and is
trusted only while `vehicle_inputs` is live.

## UI

- `Main.qml` is instantiated twice (`screenName` = drive/camper), each window on the screen
  index from config; a missing monitor falls back to screen 0 and is logged.
- Each window lays out on a logical canvas of at least 1100×680 and is scaled down
  uniformly on smaller panels (800×480 works); larger panels reflow.
- `Theme` singleton holds day/night tokens; `Card`, `QualityBadge`, `MetricTile`,
  `StatusIndicator`, `MediaMiniPlayer`, `ToggleTile`, `LevelBar`, `AlarmList`,
  `ReverseOverlay`, `MapPanel`, `DockBar`, `EnergyPanel`, `FlowTile` are the shared components.
- `main.py` resolves `[ui] layout`: `auto` opens one window per screen (drive on screen 0,
  camper on screen 1) or, with a single screen, one window containing both views with a
  Drive/Camper switch. Windows are full screen on the Pi and take the screen's resolution;
  portrait screens move the dock/rail to the bottom.
- The drive view has three layouts (full map, ¾ map + music, ¾ map + energy), remembered
  in `~/.config/aalu/aalu-dashboard.conf`.
- Complex settings (EQ) are locked in DRIVE unless GNSS shows the vehicle parked.

## Energy balance (`src/aalu/services/energy.py`)

The shunt measures the net battery current; chargers report their output. Consumption is
derived (`solar + engine − net`) and shown only when all three are live. Time to full
(net > 0.5 A) or to the reserve SOC (net < −0.5 A) uses the net current smoothed over
about a minute, so fridge cycling does not make the estimate jump.

## Map and navigation ([ADR 0004](decisions/0004-navigation-as-external-app.md), [ADR 0005](decisions/0005-map-inside-the-dashboard.md))

The drive view draws its own map (Qt Location, raster tiles, disk cache) so it can share the
screen with music or energy. Turn-by-turn navigation stays in Pure Maps, started full screen
from the dock.

## Extending: adding a real adapter

1. Implement the same `sources`, `simulated`, `start(publish)`, `stop()` as the fake
   (`PolledAdapter` for polled devices, a thread with reconnect/backoff for streams).
2. Publish readings with `quality=VALID` (or `ERROR`); on device loss, publish nothing.
3. Add a config value in `[adapters.<name>]` and the branch in `VehicleCore._build_adapters`.
4. Tests: parser/unit tests on recorded data in `tests/fixtures/`, and a hardware test in
   `tests/hardware/` marked `@pytest.mark.hardware`.
