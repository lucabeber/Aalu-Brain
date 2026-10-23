# Requirements — release v0.1 (milestones M0–M2)

Derived from the roadmap (§2, §7, §11). IDs match the roadmap. Status: **draft, to approve (gate G0)**.

## In scope for v0.1

| ID | Requirement | Acceptance (see acceptance-tests.md) | State |
|---|---|---|---|
| D-01 | Drive dashboard, Android Auto style: dock + moving map; layouts full map, ¾ map + music, ¾ map + energy; speed, one-touch cameras, no electrical controls | AT-UI-* | done (simulated) |
| D-02 | Camper dashboard: battery, solar, water, lights, audio, alarms, diagnostics | AT-UI-* | M0 done (simulated) |
| D-03 | Offline navigation and GNSS position | AT-GNSS-*, AT-NAV-* | parser done; nav app TBD on Pi |
| D-04 | Navigation fully offline from map packs: start (current location by default) and destination by search or long press, route options, turn-by-turn, recalculation, arrival; typing blocked while driving; on-screen keyboard | AT-NAV-02 | done (simulated GNSS; Trentino-Alto Adige pack) |
| D-05 | Trips saved per folder (date, time, places) with planned route, driven track and metadata; reopen and drive again | AT-NAV-03 | done |
| D-06 | GPX library: search, load; road-snapped where the track follows roads, original track off-road; routed to and back to the track | AT-NAV-04 | done |
| A-01 | Phone as Bluetooth A2DP source, Pi as sink | AT-BT-* | fake only |
| A-02 | Play/pause/next/previous, metadata when exposed | AT-BT-* | fake only |
| E-01 | House battery SOC/V/A; solar and engine (DC-DC) charging; consumption; net; time to full (net > 0) or to reserve SOC (net < 0) | AT-EN-* | done (simulated) |
| UI-S | Adapts to the attached HDMI touchscreen: full screen, any resolution and orientation; one screen = one window with Drive/Camper switch, two screens = one view each | AT-UI-* | done (offscreen tests; verify on Pi) |
| V-02 | Dashcam: continuous recording of every camera with cabin audio, 1-min MKV segments, 5 h retention, "Save clip" (−1/+1 min) and "Save 15 min" (−5/+10 min) kept until deleted, independent of the dashboard | AT-VID-* | done (simulated cameras) |
| P-01 | ACC handling, boot and shutdown | AT-PWR-* | mode machine done; hardware TBD |

## Behaviour on failure (roadmap §7), all implemented in simulation

| Case | Required behaviour | Covered by |
|---|---|---|
| GNSS without fix | dashes / "Searching for satellites"; no position or speed | `test_nmea.py`, `test_vehicle_core.py` |
| Victron disconnected | `stale` then `disconnected`; non-invasive notice | `test_vehicle_core.py` |
| Phone disconnected | player disabled, no exception | `test_vehicle_core.py` |
| MCU disconnected | load commands disabled; reverse not trusted | `test_vehicle_core.py` |
| Display missing | other window and acquisition continue | `main.py` fallback (manual test on Pi) |
| Source missing since boot | notice after its disconnect timeout | `test_vehicle_core.py` |

## Modes

DRIVE, CAMP, STANDBY, SHUTDOWN, FAULT, as specified in ADR 0003. Open: STANDBY wake
policy and consumption budget (phase 9), which events raise FAULT.

## Non-functional

- Offline-first: no network needed for any function above.
- Touch-only operation; targets ≥ 64 logical px; key values ≥ 28 px.
- Day/night theme; night is the default.
- Restart-safe: no persistent state is required to show correct data after a restart.
- Performance targets of roadmap §8 are to be measured on the Pi (M1).

## Out of scope for v0.1

Roadmap §2 "out of scope" list plus: dashcam recording (M3), Victron real adapter (M4),
load control on real hardware (M5), OTA/rollback (M6).

## Open decisions (TBD)

See `hardware-inventory.md`. None of the PCB decisions depend on assumptions made here.
