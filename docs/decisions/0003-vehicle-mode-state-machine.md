# ADR 0003 — Vehicle mode state machine

**Status:** accepted for simulation; power policy provisional until phase 9 · **Date:** 2026-10-23

## Decision
Explicit transition table (`src/aalu/core/modes.py`); unlisted (mode, event) pairs are ignored.

| From | Event | To |
|---|---|---|
| STANDBY | ACC_ON | DRIVE |
| STANDBY | USER_WAKE | CAMP |
| CAMP | ACC_ON | DRIVE |
| CAMP | IDLE_TIMEOUT (if configured) | STANDBY |
| DRIVE | ACC_OFF | CAMP |
| STANDBY, CAMP | SHUTDOWN_REQUEST | SHUTDOWN |
| any but SHUTDOWN | POWER_FAIL | SHUTDOWN |
| any but SHUTDOWN | FAULT | FAULT |
| FAULT | FAULT_CLEARED | DRIVE if ACC else CAMP |

- SHUTDOWN is terminal until reboot. No SHUTDOWN_REQUEST from DRIVE.
- Boot: initial STANDBY; the first `vehicle_inputs` reading moves to DRIVE (ACC on) or CAMP
  (ACC off). If the MCU never reports, the system stays in STANDBY and a touch wakes to CAMP.
- ACC off never switches off camper functions automatically (roadmap §7).

## Open
Which conditions raise FAULT; STANDBY consumption and wake sources; PARKED / LOW BATTERY
states from roadmap phase 9 (may become CAMP sub-states rather than new modes).
