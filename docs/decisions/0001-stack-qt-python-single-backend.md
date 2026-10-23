# ADR 0001 — Qt 6/QML with PySide6 and a single Python backend

**Status:** accepted (M0) · **Date:** 2026-10-23

## Context
Two touchscreens, offline operation, a Raspberry Pi 5, and a maintainer who should be able
to change things without a large toolchain. The roadmap (§3) proposes Qt/QML + Python.

## Decision
- UI in QML (Qt Quick), backend in Python 3.11+ via PySide6 (pinned, 6.8.1).
- One process for UI + Vehicle Core. Device I/O in adapter threads; all state changes on
  the GUI thread (queued signal), so core code is single-threaded and Qt-free.
- Separate processes only for: video recording (must survive UI crashes), the navigation
  app, and later a hardware/power supervisor.
- No Docker, no MQTT broker between local components.

## Consequences
- A crash of the UI process also stops acquisition in this process. Acceptable for M0–M2
  because nothing safety-relevant depends on it; recording (M3) is out of process by
  design. Revisit if the MCU link needs to stay up across UI restarts (M5): the core can be
  moved to its own process behind the same adapter interfaces.
- QML context properties (`Vehicle`, `Backend`) are used for simplicity; qmllint reports
  them as unqualified. Can be migrated to registered singletons later.
