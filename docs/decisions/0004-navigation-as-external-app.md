# ADR 0004 — Navigation as a separate application

**Status:** accepted, amended by ADR 0005 (map inside the dashboard) · **Date:** 2026-10-23

## Decision
Offline navigation is not rewritten. The drive screen launches the configured command
(`[navigation] command`, e.g. Pure Maps via Flatpak with OSM Scout Server) as a separate
process with its own session. The dashboard keeps its own map, position and status bar
independently (ADR 0005).

## Consequences
- Window placement of the navigation app on the drive screen must be handled by the
  compositor (labwc window rules) — to be verified on the Pi (NAV-01).
- Embedding a map inside the Qt window is evaluated only after benchmarks and a licence
  review (roadmap phase 4).
