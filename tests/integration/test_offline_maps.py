"""Offline engines on a tiny synthetic OSM extract written with osmium.

A 2 x 2 km grid of roads near Trento with a few places: builds a real search
index and a real Valhalla graph, so routing/search are tested without downloads.
"""

import json
import urllib.request

import pytest

osmium = pytest.importorskip("osmium")
pytest.importorskip("valhalla")

from aalu.maps.build import build_routing  # noqa: E402
from aalu.maps.pack import find_packs, write_pack_meta  # noqa: E402
from aalu.maps.places import LocalGeocoder, build_index  # noqa: E402
from aalu.maps.routing import ValhallaRouter  # noqa: E402
from aalu.services.navigation import NavError, RouteOptions  # noqa: E402

LAT0, LON0 = 46.06, 11.11
STEP = 0.004  # ~450 m / ~310 m


def write_grid(path):
    """5 x 5 nodes, horizontal streets 'Via Nord N', vertical 'Via Est N', plus places."""
    w = osmium.SimpleWriter(str(path))
    nid = 1

    def node_id(i, j):
        return 1 + i * 5 + j

    for i in range(5):
        for j in range(5):
            w.add_node(osmium.osm.mutable.Node(
                id=node_id(i, j), location=(LON0 + j * STEP, LAT0 + i * STEP), version=1))
    nid = 100
    w.add_node(osmium.osm.mutable.Node(id=nid, location=(LON0 + 2 * STEP, LAT0 + 2 * STEP),
                                       tags={"place": "town", "name": "Testville"}, version=1))
    w.add_node(osmium.osm.mutable.Node(id=nid + 1, location=(LON0 + 4 * STEP, LAT0 + 4 * STEP),
                                       tags={"tourism": "camp_site", "name": "Camping Lago Blu"},
                                       version=1))
    w.add_node(osmium.osm.mutable.Node(id=nid + 2, location=(LON0 + 0.5 * STEP, LAT0),
                                       tags={"addr:street": "Via Nord 0", "addr:housenumber": "12"},
                                       version=1))
    wid = 1
    for i in range(5):
        w.add_way(osmium.osm.mutable.Way(id=wid, nodes=[node_id(i, j) for j in range(5)],
                                         tags={"highway": "residential", "name": f"Via Nord {i}"},
                                         version=1))
        wid += 1
    for j in range(5):
        w.add_way(osmium.osm.mutable.Way(id=wid, nodes=[node_id(i, j) for i in range(5)],
                                         tags={"highway": "residential", "name": f"Via Est {j}"},
                                         version=1))
        wid += 1
    w.close()


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    root = tmp_path_factory.mktemp("maps")
    pbf = root / "grid.osm.pbf"
    write_grid(pbf)
    p = root / "grid"
    p.mkdir()
    rows, (x0, y0, x1, y1) = build_index(pbf, p / "places.sqlite")
    build_routing(pbf, p / "valhalla")
    write_pack_meta(p, {"name": "grid", "bbox": [x0 - 0.01, y0 - 0.01, x1 + 0.01, y1 + 0.01],
                        "places": rows})
    (packs,) = [find_packs(root)]
    return packs[0]


def test_search_index_finds_places_streets_and_addresses(pack):
    g = LocalGeocoder([pack.places_db])
    near = (LAT0, LON0)
    assert g.search("testville", near)[0].name == "Testville"
    assert g.search("camping lago", near)[0].name == "Camping Lago Blu"
    first = g.search("via nord 0 12", near)[0]
    assert first.name == "Via Nord 0 12" and "Testville" in first.detail
    assert g.search("via nord 3 testville", near)[0].name == "Via Nord 3"
    assert g.reverse(LAT0 + 0.001, LON0 + 0.001) == "Testville"


def test_offline_route_with_maneuvers(pack):
    router = ValhallaRouter([pack])
    assert router.available
    route = router.route((LAT0, LON0), (LAT0 + 4 * STEP, LON0 + 4 * STEP))
    assert 2000 < route.distance_m < 3500  # Manhattan distance across the grid
    assert route.maneuvers[0].kind == "start" and route.maneuvers[-1].kind == "destination"
    assert any(m.kind in ("left", "right") for m in route.maneuvers)
    assert all("Via" in m.instruction or m.kind in ("start", "destination")
               for m in route.maneuvers[:-1])


def test_route_options_are_accepted(pack):
    route = ValhallaRouter([pack]).route((LAT0, LON0), (LAT0 + 4 * STEP, LON0),
                                         RouteOptions(avoid_motorways=True, avoid_unpaved=True))
    assert route.distance_m > 1500


def test_outside_the_packs_is_a_clear_error(pack):
    with pytest.raises(NavError, match="Outside the downloaded maps"):
        ValhallaRouter([pack]).route((45.0, 9.0), (LAT0, LON0))


def test_map_matching_marks_offroad_points(pack):
    router = ValhallaRouter([pack])
    on_road = [(LAT0, LON0 + k * STEP / 4) for k in range(9)]  # along Via Nord 0
    # Between two streets, far from both:
    off_road = [(LAT0 + STEP / 2, LON0 + 2.2 * STEP + k * 0.0003) for k in range(4)]
    result = router.trace(on_road + off_road)
    types = [m["type"] for m in result["matched_points"]]
    assert types[:9].count("matched") >= 8


def test_map_server_serves_packs_assets_and_refuses_escapes(pack, tmp_path):
    from aalu.maps.server import MapServer

    web = tmp_path / "web"
    web.mkdir()
    (web / "map.html").write_text("<html>ok</html>")
    srv = MapServer(web, pack.path.parent, [pack], osm_upstream=None, user_agent="t")
    url = srv.start()
    try:
        with urllib.request.urlopen(url + "web/map.html", timeout=5) as r:
            assert r.read() == b"<html>ok</html>"
        with urllib.request.urlopen(url + "packs.json", timeout=5) as r:
            assert json.load(r) == []  # this test pack has no map.pmtiles
        for bad in ("web/../../etc/passwd", "web/%2e%2e/%2e%2e/etc/passwd", "osm/1/0/0.png"):
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(url + bad, timeout=5)
            assert err.value.code == 404
    finally:
        srv.stop()


def _cross_country_track():
    """Along Via Nord 0, straight across the block (no road), then along Via Nord 2."""
    along0 = [(LAT0, LON0 + k * STEP / 8) for k in range(0, 17)]           # 0 -> 2 STEP east
    across = [(LAT0 + k * STEP / 10, LON0 + 2.5 * STEP) for k in range(1, 20)]  # mid-block
    along2 = [(LAT0 + 2 * STEP, LON0 + 2.5 * STEP + k * STEP / 8) for k in range(1, 13)]
    return along0 + [(LAT0, LON0 + 2.5 * STEP)] + across + along2


def test_gpx_track_becomes_road_and_offroad_parts(pack):
    from aalu.maps.hybrid import HybridTrack

    track = HybridTrack(ValhallaRouter([pack]), _cross_country_track(), "Cross country")
    route = track.base
    kinds = route.kinds
    assert "road" in kinds and "offroad" in kinds
    assert kinds[0] == "road" and kinds[-1] == "road"
    assert route.offroad_m > 300 and route.road_m > 300
    assert any(m.kind == "offroad" for m in route.maneuvers)
    assert route.maneuvers[-1].kind == "destination"
    # Off-road points are the original track points, not snapped to a street.
    off = [p for p, k in zip(route.points, kinds, strict=True) if k == "offroad"]
    assert any(abs(lon - (LON0 + 2.5 * STEP)) < 1e-6 for _, lon in off)


def test_gpx_route_from_far_away_adds_an_approach(pack):
    from aalu.maps.hybrid import HybridTrack

    router = ValhallaRouter([pack])
    track = HybridTrack(router, _cross_country_track(), "Cross country")
    far = (LAT0 + 4 * STEP, LON0 + 4 * STEP)
    route = track.route_from(far, 0, router)
    assert route.points[0] != track.base.points[0]
    assert any("Join the GPX track" in m.instruction for m in route.maneuvers)
    assert route.distance_m > track.base.distance_m
    # Re-joining later on the track skips what is behind.
    later = track.route_from(None, track.nearest_index((LAT0 + 2 * STEP, LON0 + 3 * STEP)))
    assert later.distance_m < track.base.distance_m


def test_gpx_without_routing_data_keeps_the_whole_track():
    from aalu.maps.hybrid import HybridTrack

    track = HybridTrack(None, _cross_country_track(), "No maps")
    assert set(track.base.kinds) == {"offroad"}


def test_gpx_library_scan_search_and_load(tmp_path):
    from aalu.maps.gpx import GpxPoint, write_gpx
    from aalu.services.gpx_library import GpxLibrary

    (tmp_path / "hikes").mkdir()
    write_gpx(tmp_path / "hikes" / "pordoi.gpx", "Passo Pordoi loop",
              [[GpxPoint(46.48, 11.81), GpxPoint(46.49, 11.82), GpxPoint(46.4801, 11.8101)]])
    write_gpx(tmp_path / "garda.gpx", "Lago di Garda", [[GpxPoint(45.88, 10.84),
                                                          GpxPoint(45.90, 10.86)]])
    (tmp_path / "broken.gpx").write_text("<gpx><trk>")
    lib = GpxLibrary(tmp_path, namer=lambda lat, lon: "Canazei" if lat > 46 else "Riva")
    entries = {e["id"]: e for e in lib.refresh()}
    assert entries["hikes/pordoi.gpx"]["loop"] is True
    assert entries["hikes/pordoi.gpx"]["start_name"] == "Canazei"
    assert "error" in entries["broken.gpx"]
    assert [e["id"] for e in lib.search("canazei", None)] == ["hikes/pordoi.gpx"]
    near_riva = lib.search("", (45.88, 10.84))
    assert near_riva[0]["id"] == "garda.gpx" and near_riva[0]["distance_m"] < 10
    data, points, _ = lib.load("hikes/pordoi.gpx")
    assert data.name == "Passo Pordoi loop" and len(points) == 3
    with pytest.raises(ValueError):
        lib.load("../outside.gpx")
    # Second scan uses the cache (index file written in the folder).
    assert (tmp_path / ".aalu-gpx-index.json").exists()
