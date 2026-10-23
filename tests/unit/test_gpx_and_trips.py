import json
from datetime import UTC, datetime

from aalu.maps.gpx import GpxPoint, read_gpx, write_gpx
from aalu.services.trips import TripStore

GPX_10_ROUTE = """<?xml version="1.0"?>
<gpx version="1.0" creator="planner" xmlns="http://www.topografix.com/GPX/1/0">
  <rte><name>Passo Pordoi tour</name>
    <rtept lat="46.48" lon="11.81"><name>a</name></rtept>
    <rtept lat="46.49" lon="11.82"/>
    <rtept lat="999" lon="11.83"/>
  </rte>
</gpx>"""


def test_gpx_roundtrip_with_time_and_elevation(tmp_path):
    t = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    pts = [GpxPoint(46.0, 11.0, 200.0, t), GpxPoint(46.001, 11.001, 201.5, None)]
    write_gpx(tmp_path / "a.gpx", "Test", [pts], [(GpxPoint(46.0, 11.0), "Start")], "desc", t)
    data = read_gpx(tmp_path / "a.gpx")
    assert data.name == "Test" and data.description == "desc" and data.time == t
    assert [(p.lat, p.lon, p.ele) for p in data.tracks[0]] == [(46.0, 11.0, 200.0),
                                                               (46.001, 11.001, 201.5)]
    assert data.waypoints[0][1] == "Start"


def test_gpx_10_routes_are_read_and_bad_points_skipped(tmp_path):
    (tmp_path / "r.gpx").write_text(GPX_10_ROUTE)
    data = read_gpx(tmp_path / "r.gpx")
    assert data.name == "Passo Pordoi tour" and len(data.all_points()) == 2


def test_trip_store_marks_interrupted_trips(tmp_path):
    clock = iter(range(0, 10_000, 20)).__next__
    store = TripStore(tmp_path, clock=lambda: clock())
    start = {"name": "Trento", "lat": 46.0, "lon": 11.0}
    dest = {"name": "Lago di Tovel", "lat": 46.26, "lon": 10.95}
    folder = store.start(start, dest, {}, [(46.0, 11.0), (46.26, 10.95)], 52000, 4300)
    assert folder.name.endswith("Trento-Lago-di-Tovel")
    store.add_point(46.0, 11.0, 30)
    store.add_point(46.001, 11.0, 50)
    # Power cut: no finish(). The next start finds the trip still "driving".
    TripStore(tmp_path)
    meta = json.loads((folder / "trip.json").read_text())
    assert meta["status"] == "interrupted"
    assert read_gpx(folder / "route.gpx").waypoints[1][1] == "Lago di Tovel"
