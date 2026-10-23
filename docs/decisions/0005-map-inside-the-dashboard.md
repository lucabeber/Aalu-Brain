# ADR 0005 — Moving map inside the dashboard, Pure Maps for turn-by-turn

**Status:** accepted · **Date:** 2026-10-23

## Context
The drive screen should behave like Android Auto / CarPlay: full-screen map, or ¾ map with
music or energy beside it. Pure Maps is a separate application; on Wayland (labwc on
Raspberry Pi OS) one client cannot embed another client's window, and window positioning
is up to the compositor. Placing Pure Maps inside a ¾ region of our window is therefore not
possible in a robust way.

## Decision
- The dashboard renders its own moving map with Qt Location (`MapView`, `osm` plugin) and a
  configurable raster tile URL (`[map]`). It follows the GNSS position, draws the vehicle
  heading and track, and stops following when the user pans (re-centre button).
- Turn-by-turn routing stays in Pure Maps + OSM Scout Server, launched full screen from the
  dock (`[navigation] command`). Returning to the dashboard is done with the app switcher /
  closing Pure Maps; a compositor rule for this is to be set up on the Pi.

## Consequences
- **Offline**: the default OSM tile server needs Internet. Tiles already viewed are kept in
  a disk cache (`cache_size_mb`), and `offline_dir` accepts pre-rendered tiles. Bulk
  downloading from tile.openstreetmap.org is not allowed by its usage policy, so true
  offline maps need a local source. Preferred path: OSM Scout Server (already planned for
  Pure Maps) serving tiles on localhost, set as `tile_url`; alternative: an MBTiles/vector
  renderer (MapLibre) inside the dashboard, to evaluate on the Pi for CPU/GPU cost.
- Routing inside the dashboard map (e.g. Valhalla from OSM Scout Server) would allow
  turn-by-turn in the split layouts later without changing the layout code.
- Night mode dims the light raster tiles; a dark tile style can be configured later.
