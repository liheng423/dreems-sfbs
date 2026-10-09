"""Check the shared filter interface and each request retention rule."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/reqreate"))
from filters.filters import (BASE_REQUEST_FILTERS, BUS_REQUEST_FILTERS,
                             REQUEST_FILTERS, passes_filters,
                             select_scheduled_bus_stops)
from filters.route_schedule import index_route_departures


def main():
    walking_distance = SimpleNamespace(
        within_limit=Mock(return_value=True),
        distance_to_nearest_stop=Mock(return_value=100),
        direct_distance_within=Mock(return_value=False),
        accessible_stops=Mock(side_effect=lambda point: {"A": 100} if point.x == 0.5
                              else {"B": 100}),
    )
    net = SimpleNamespace(polygon=box(0, 0, 2, 2), walking_distance=walking_distance,
                          route_departures={("A", "B"): [(600, 900)]})
    cfg = {"parameters": [{"name": "min_distance", "value": 100}],
           "walking_speed_mps": 1.0}
    req = {"origin": [0.5, 0.5], "destination": [1.5, 1.5],
           "direct_distance": 100, "direct_travel_time": 1,
           "earliest_departure": 400, "latest_arrival": 1000}
    assert passes_filters(req, REQUEST_FILTERS, net, cfg)
    assert REQUEST_FILTERS == BASE_REQUEST_FILTERS + BUS_REQUEST_FILTERS
    assert select_scheduled_bus_stops(req, net, cfg) == {
        "boarding_stop_id": "A", "alighting_stop_id": "B",
        "boarding_walk_distance_m": 100, "alighting_walk_distance_m": 100,
    }

    for change in ({"origin": [3, 3]}, {"direct_distance": 99},
                   {"direct_travel_time": 0}):
        assert not passes_filters(req | change, REQUEST_FILTERS, net, cfg)
    walking_distance.within_limit.return_value = False
    assert not passes_filters(req, REQUEST_FILTERS, net, cfg)
    assert passes_filters(req, BASE_REQUEST_FILTERS, net, cfg)
    walking_distance.within_limit.return_value = True
    walking_distance.direct_distance_within.return_value = True
    assert not passes_filters(req, REQUEST_FILTERS, net, cfg)
    walking_distance.direct_distance_within.return_value = False
    net.route_departures = {("B", "A"): [(600, 900)]}
    assert not passes_filters(req, REQUEST_FILTERS, net, cfg)
    net.route_departures = {("A", "B"): [(499, 900)]}
    assert not passes_filters(req, REQUEST_FILTERS, net, cfg)
    net.route_departures = {("A", "B"): [(600, 901)]}
    assert not passes_filters(req, REQUEST_FILTERS, net, cfg)

    walking_distance.accessible_stops.side_effect = (
        lambda point: {"A": 100, "C": 50} if point.x == 0.5 else {"B": 100, "D": 50}
    )
    net.route_departures = {("A", "B"): [(600, 900)],
                            ("C", "D"): [(600, 900)]}
    assert select_scheduled_bus_stops(req, net, cfg) == {
        "boarding_stop_id": "C", "alighting_stop_id": "D",
        "boarding_walk_distance_m": 50, "alighting_walk_distance_m": 50,
    }

    schedule = {"patterns": [{"trips": [{"stop_times": [
        {"stop_id": "A", "departure_seconds": 600, "pickup_type": "0"},
        {"stop_id": "B", "arrival_time": "0:15:00", "pickup_type": "0",
         "drop_off_type": "0"},
    ]}]}]}
    assert index_route_departures(schedule) == {("A", "B"): [(600, 900)]}

    assert not passes_filters(req, REQUEST_FILTERS + (lambda candidate, net, cfg: False,),
                              net, cfg)
    print("Validated REQreate filter predicates and extension point")


if __name__ == "__main__":
    main()
