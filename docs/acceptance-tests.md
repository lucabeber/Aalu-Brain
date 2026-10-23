# Acceptance tests

Automated (A) tests run in CI; manual (M) tests are run and recorded on the bench or vehicle.

| ID | Type | Procedure | Pass criterion | Gate |
|---|---|---|---|---|
| AT-UI-01 | A | `pytest tests/integration/test_dashboard_smoke.py` | both windows start at 800×480, 1024×600, 1280×800, 1920×1080 with zero QML warnings | G1, G2 |
| AT-UI-02 | M | demo: open every camper page, toggle every simulation key | no freeze; every degraded source shows `—` or a badge, never a frozen value | G2 |
| AT-UI-03 | M | `--sim reverse=true`, then toggle reverse on the Simulazione page | overlay appears/disappears; navigation area intact afterwards | G2 |
| AT-UI-04 | M | two monitors, unplug one during operation | other window keeps updating | G3 |
| AT-GNSS-01 | A | `pytest tests/unit/test_nmea.py` | no position without fix; correct epoch grouping; checksums enforced | G4 |
| AT-GNSS-02 | M | Pi + receiver indoors, `adapters.gnss = serial` | "GPS searching", no coordinates | G4 |
| AT-GNSS-03 | M | outdoors, cold start | fix obtained; coordinates match a phone within ~10 m; time to first fix recorded | G4 |
| AT-GNSS-04 | M | unplug receiver while running | `stale` after 3 s, `disconnected` after 10 s; recovers on re-plug | G4 |
| AT-NAV-01 | M | Pure Maps + OSM Scout Server on Pi, Wi-Fi off | route computed and displayed on the test route | G4 |
| AT-NAV-02 | M | parked, search "Riva del Garda", pick result, then drive (simulated) | route drawn, ETA plausible, remaining distance decreases, "Arrived" at the end; typing locked while moving | G4 |
| AT-NAV-03 | M | navigate to a destination, arrive; reopen the trip from the Trips tab | folder with route.gpx, track.gpx, trip.json (status completed); *Drive from here* plans it again | G4 |
| AT-NAV-04 | M | load `bondone-mixed.gpx`, start, drive (simulated) | road parts blue with turn instructions, off-road parts orange with "follow the GPX track", end announced | G4 |
| AT-NAV-05 | M | Pi offline (Wi-Fi off), pack installed | map, search, routing and GPX work; no online requests inside the pack area | G4 |
| AT-BT-01 | M | pair 2 different phones, play, pause, next, prev 20× | commands work; reconnect after phone BT off/on | G5 |
| AT-EN-01 | M | compare battery card with VictronConnect | values match within the device resolution | G7 |
| AT-VID-01 | A | `pytest tests/integration/test_video_service.py tests/unit/test_video_segments.py` | segments finalized, 5 h retention, both save windows, protected never deleted, crash restart | G6 |
| AT-VID-02 | M | real cameras, 4 h recording, random clips | all segments play; no gaps > 1 s between segments | G6 |
| AT-VID-03 | M | unplug one camera for 1 min | other camera keeps recording; unplugged one resumes | G6 |
| AT-VID-04 | M | cut power while recording | earlier segments intact; last one playable up to a few s before the cut | G6/G9 |
| AT-PWR-01 | M | 20 power cycles | GUI visible < 30 s (target to measure) | G3/G9 |
