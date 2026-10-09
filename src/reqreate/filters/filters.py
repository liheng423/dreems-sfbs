"""Shared filter contract and predicates for POIs and generated requests."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable
from math import ceil
from typing import TYPE_CHECKING, Protocol

from shapely.geometry import Point

if TYPE_CHECKING:
    from maps.area_network import AreaNetwork


class CandidateFilter[Candidate](Protocol):
    """Return True to retain a candidate; do not mutate the candidate or context."""

    def __call__(self, candidate: Candidate, net: AreaNetwork, cfg: dict) -> bool:
        """Return True when the candidate should be retained."""
        ...


def passes_filters[Candidate](candidate: Candidate, filters: Iterable[CandidateFilter[Candidate]],
                              net: AreaNetwork, cfg: dict) -> bool:
    """Return True if every filter accepts the candidate, in order."""
    return all(predicate(candidate, net, cfg) for predicate in filters)


def request_within_area(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Accept a request when both endpoints lie inside the service area."""
    return all(net.polygon.contains(Point(req[name][1], req[name][0]))
               for name in ("origin", "destination"))


def request_has_min_driving_distance(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Accept a request meeting the configured minimum driving distance."""
    min_distance_m = next(param["value"] for param in cfg["parameters"]
                          if param["name"] == "min_distance")
    return req["direct_distance"] >= min_distance_m


def request_has_positive_travel_time(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Accept a request with a positive estimated driving time."""
    return req["direct_travel_time"] > 0


def request_within_walking_distance(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Accept a request when both endpoints can walk to a bus stop."""
    return all(net.walking_distance.within_limit(Point(req[name][1], req[name][0]))
               for name in ("origin", "destination"))


def request_not_walk_dominated(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Accept a trip only if its direct walk exceeds its combined stop access walks."""
    origin = Point(req["origin"][1], req["origin"][0])
    destination = Point(req["destination"][1], req["destination"][0])
    access_distance = (net.walking_distance.distance_to_nearest_stop(origin)
                       + net.walking_distance.distance_to_nearest_stop(destination))
    return not net.walking_distance.direct_distance_within(
        origin, destination, access_distance
    )


def select_scheduled_bus_stops(req: dict, net: AreaNetwork, cfg: dict) -> dict | None:
    """Return the feasible stop pair with least walking, then earliest arrival."""
    origin = Point(req["origin"][1], req["origin"][0])
    destination = Point(req["destination"][1], req["destination"][0])
    origin_stops = net.walking_distance.accessible_stops(origin)
    destination_stops = net.walking_distance.accessible_stops(destination)
    walking_speed = cfg["walking_speed_mps"]
    best_key = None
    selected_stops = None
    for origin_stop_id, origin_distance in origin_stops.items():
        earliest_boarding = ceil(req["earliest_departure"] + origin_distance / walking_speed)
        for destination_stop_id, destination_distance in destination_stops.items():
            latest_alighting = req["latest_arrival"] - destination_distance / walking_speed
            departures = net.route_departures.get((origin_stop_id, destination_stop_id), ())
            for departure, arrival in departures[bisect_left(departures, (earliest_boarding, -1)):]:
                if departure > latest_alighting:
                    break
                if arrival <= latest_alighting:
                    key = (origin_distance + destination_distance, arrival, departure,
                           origin_stop_id, destination_stop_id)
                    if best_key is None or key < best_key:
                        best_key = key
                        selected_stops = {
                            "boarding_stop_id": origin_stop_id,
                            "alighting_stop_id": destination_stop_id,
                            "boarding_walk_distance_m": origin_distance,
                            "alighting_walk_distance_m": destination_distance,
                        }
    return selected_stops


def request_has_feasible_scheduled_bus(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Accept a request with a bus trip meeting its boarding and arrival times."""
    return select_scheduled_bus_stops(req, net, cfg) is not None


BASE_REQUEST_FILTERS = (
    request_within_area,
    request_has_min_driving_distance,
    request_has_positive_travel_time,
)
BUS_REQUEST_FILTERS = (
    request_within_walking_distance,
    request_not_walk_dominated,
    request_has_feasible_scheduled_bus,
)
REQUEST_FILTERS = BASE_REQUEST_FILTERS + BUS_REQUEST_FILTERS
