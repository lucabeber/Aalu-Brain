# ADR 0007 — Offline maps, search and routing inside the dashboard (no Pure Maps)

**Status:** accepted · **Date:** 2026-10-23 · supersedes the Pure Maps / OSM Scout Server
plan of ADR 0004 and the online-only parts of ADR 0005

## Context
The Pi is offline on the road. The owner wants navigation (start/destination), saved trips,
GPX tracks (road-snapped where possible, raw off-road) — without a separate map app.

## Decision
Region **map packs**, built at home with `scripts/build_map_pack.py <region>`, contain:

| Part | File | Engine at runtime | Source |
|---|---|---|---|
| Map picture | `map.pmtiles` (vector, Protomaps schema, z0–15) | MapLibre GL JS in a Qt WebEngine view | Protomaps daily build, cut to the region with `pmtiles extract` |
| Routing + GPX map matching | `valhalla/` | Valhalla via `pyvalhalla` (in-process) | OSM extract (openstreetmap.fr / Geofabrik) |
| Search | `places.sqlite` (FTS5) | own `LocalGeocoder` | same OSM extract, read with `osmium` |
| Fonts, sprites | `_assets/` (shared) | MapLibre | protomaps/basemaps-assets |

- A localhost HTTP server (`aalu.maps.server`) serves the map page, vendored JS (MapLibre
  6.15, @protomaps/basemaps 5.7 — pinned in `apps/dashboard/web/vendor`), assets and tiles.
- Search and routing go through `FallbackGeocoder` / `FallbackRouter`: offline engines
  first; online Nominatim/OSRM/OSM tiles only where no pack covers the area and only if
  `[map] online_fallback = true`. Inside a pack the online raster layer is hidden, so no
  data is downloaded.
- QtLocation stays as the fallback map when no pack is installed or WebEngine is missing.

## Navigation features on top
- Start / destination (current location by default, search or long press), route options,
  turn-by-turn maneuvers, off-route recalculation, arrival.
- Trips (`aalu.services.trips`): one folder per trip with route.gpx, track.gpx, trip.json;
  a trip left "driving" by a power cut is marked "interrupted" at the next start.
- GPX (`aalu.maps.hybrid`): Valhalla `trace_attributes` labels each (resampled, 25 m) point
  road/off-road; short runs are merged; road runs are re-routed with `trace_route` unless
  that makes a detour > 1.5× the GPX stretch; off-road runs keep the original points. The
  vehicle is routed to the track and, when off it, back to the nearest point ahead.

## Measured (Trentino-Alto Adige, PC)
Build 197 s; pack 500 MB (map 351, routing 104, search 48); search 0–50 ms; route
Trento → Lago di Tovel (52 km) 151 ms with English turn instructions.

## Consequences / open
- Needs WebGL2: fine on the Pi 5 GPU (to verify), not available in headless CI (tests use a
  synthetic graph and the Qt Location map).
- Larger regions: Italy ≈ several GB per pack; building on the PC and copying to the SSD
  is recommended.
- One Valhalla graph per pack: a route must start and end inside the same pack (a combined
  multi-region pack can be built from several extracts later).
