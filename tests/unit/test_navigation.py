from concurrent.futures import Executor, Future

import pytest

from aalu.core.geo import Polyline, haversine_m
from aalu.services.navigation import (
    NavError,
    NavigationController,
    NominatimGeocoder,
    OsrmRouter,
    PlannedRoute,
)

TRENTO = (46.0679, 11.1211)


class SyncExecutor(Executor):
    def submit(self, fn, *args, **kwargs):
        f = Future()
        f.set_result(fn(*args, **kwargs))
        return f


def nominatim_reply(url, headers, timeout):
    assert "q=Riva" in url and "viewbox=" in url and headers["User-Agent"]
    return [
        {"name": "Riva del Garda",
         "display_name": "Riva del Garda, Comunità Alto Garda, Trento, Italy",
         "lat": "45.8857", "lon": "10.8418", "type": "town"},
        {"name": "Riva del Garda", "display_name": "Riva del Garda, Trento, Italy",
         "lat": "45.8900", "lon": "10.8500", "type": "administrative"},  # same place, dropped
        {"display_name": "Riva Ligure, Imperia, Italy", "lat": "43.84", "lon": "7.88"},
        {"name": "broken"},  # missing coordinates: skipped
    ]


def osrm_reply(url, headers, timeout):
    assert "/route/v1/driving/11.121100,46.067900;10.841800,45.885700" in url
    return {"code": "Ok", "routes": [{"distance": 42300.0, "duration": 2940.0, "geometry": {
        "coordinates": [[11.1211, 46.0679], [11.0, 46.0], [10.8418, 45.8857]]}}]}


def test_geocoder_parses_dedupes_and_biases_near_vehicle(monkeypatch):
    monkeypatch.setattr(NominatimGeocoder, "MIN_INTERVAL_S", 0)
    places = NominatimGeocoder("https://n.example", "ua", fetch=nominatim_reply).search(
        "Riva", TRENTO, 8)
    assert [p.name for p in places] == ["Riva del Garda", "Riva Ligure"]
    assert places[0].detail.startswith("Comunità Alto Garda")


def test_router_parses_route_and_reports_no_route():
    r = OsrmRouter("https://o.example", "ua", fetch=osrm_reply).route(TRENTO, (45.8857, 10.8418))
    assert r.distance_m == 42300 and r.points[0] == (46.0679, 11.1211)
    with pytest.raises(NavError):
        OsrmRouter("x", "ua", fetch=lambda *a: {"code": "NoRoute", "routes": []}).route(
            TRENTO, (0, 0))


class FakeGeocoder:
    def __init__(self, places=None, error=None):
        self.places, self.error, self.calls = places or [], error, []

    def search(self, query, near, limit):
        self.calls.append((query, near))
        if self.error:
            raise NavError(self.error)
        return self.places


class FakeRouter:
    def __init__(self, points):
        self.points, self.calls = points, []

    def route(self, start, end):
        self.calls.append(start)
        return PlannedRoute(self.points, Polyline(self.points).length, 600.0)


LINE = [(46.0, 11.0), (46.01, 11.0), (46.02, 11.0)]  # straight north, ~2.2 km


def controller(places=None, error=None):
    from aalu.services.navigation import Place

    places = places or [Place("Dest", "Somewhere", 46.02, 11.0)]
    followed = []
    nav = NavigationController(FakeGeocoder(places, error), FakeRouter(LINE),
                               executor=SyncExecutor(), on_route=followed.append)
    return nav, followed


def test_search_choose_progress_and_arrival():
    nav, followed = controller()
    nav.search("dest", (46.0, 11.0))
    v = nav.view()["search"]
    assert v["state"] == "done" and v["results"][0]["distance_m"] == pytest.approx(2224, abs=5)

    nav.choose(0, (46.0, 11.0))
    route = nav.view()["route"]
    assert route["state"] == "active" and route["remaining_m"] == pytest.approx(2224, abs=5)
    assert followed[-1] == LINE and len(nav.path()) == 3

    nav.update_position((46.01, 11.0))  # half way
    assert nav.view()["route"]["remaining_m"] == pytest.approx(1112, abs=5)
    assert nav.view()["route"]["remaining_s"] == pytest.approx(300, abs=2)

    nav.update_position((46.0199, 11.0))
    assert nav.view()["route"]["state"] == "arrived"

    nav.cancel()
    assert nav.view()["route"]["state"] == "none" and followed[-1] is None


def test_off_route_triggers_recalculation_after_three_fixes():
    nav, _ = controller()
    nav.search("dest", (46.0, 11.0))
    nav.choose(0, (46.0, 11.0))
    router = nav._router
    far = (46.005, 11.01)  # ~770 m east of the line
    nav.update_position(far)
    nav.update_position(far)
    assert len(router.calls) == 1 and nav.view()["route"]["off_route"] is True
    nav.update_position(far)
    assert router.calls[-1] == far  # re-planned from where the car is


def test_errors_and_empty_results_are_reported():
    nav, _ = controller(error="No Internet connection: search and routing need it for now")
    nav.search("x", None)
    assert nav.view()["search"]["state"] == "error"
    assert "Internet" in nav.view()["search"]["error"]

    nav2, _ = controller(places=[])
    nav2._geocoder.places = []
    nav2.search("nothing", None)
    assert nav2.view()["search"]["state"] == "empty"


def test_choose_without_position_is_an_error():
    nav, _ = controller()
    nav.search("dest", None)
    nav.choose(0, None)
    assert nav.view()["route"]["state"] == "error"


def test_late_result_of_a_superseded_search_is_ignored():
    pending = []
    nav = NavigationController(FakeGeocoder([]), FakeRouter(LINE), executor=SyncExecutor(),
                               post=pending.append)
    nav.search("first", None)
    nav.search("second", None)
    for fn in pending:  # results arrive after both searches were issued
        fn()
    assert nav.view()["search"]["query"] == "second"


def test_polyline_locate_projects_onto_segments():
    line = Polyline(LINE)
    along, off, idx = line.locate((46.015, 11.001))
    assert along == pytest.approx(haversine_m(LINE[0], (46.015, 11.0)), abs=3)
    assert off == pytest.approx(77, abs=3) and idx == 1
