"""Shared filter contract and predicates for POIs and generated requests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from shapely.geometry import Point

if TYPE_CHECKING:
    import pandas as pd
    from area_network import AreaNetwork


class CandidateFilter[Candidate](Protocol):
    """Return True to retain a candidate; do not mutate the candidate or context."""

    def __call__(self, candidate: Candidate, net: AreaNetwork, cfg: dict) -> bool: ...


def passes_filters[Candidate](candidate: Candidate, filters: Iterable[CandidateFilter[Candidate]],
                              net: AreaNetwork, cfg: dict) -> bool:
    """Apply predicates in order, stopping at the first rejection."""
    return all(predicate(candidate, net, cfg) for predicate in filters)


def poi_within_area(feature: pd.Series, net: AreaNetwork, cfg: dict) -> bool:
    """Keep POIs whose representative point is inside the service area."""
    return net.polygon.contains(feature.geometry.representative_point())


def request_within_area(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Require both sampled endpoints to be inside the service area."""
    return all(net.polygon.contains(Point(req[name][1], req[name][0]))
               for name in ("origin", "destination"))


def request_has_min_driving_distance(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Require the configured minimum directed driving distance."""
    min_distance_m = next(param["value"] for param in cfg["parameters"]
                          if param["name"] == "min_distance")
    return req["direct_distance"] >= min_distance_m


def request_has_positive_travel_time(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Reject an unreachable or zero-time driving route."""
    return req["direct_travel_time"] > 0


def request_within_walking_distance(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    """Require both endpoints to be walkable from a Route 550 stop."""
    return all(net.walking_distance.within_limit(Point(req[name][1], req[name][0]))
               for name in ("origin", "destination"))


POI_FILTERS = (poi_within_area,)
REQUEST_FILTERS = (
    request_within_area,
    request_has_min_driving_distance,
    request_has_positive_travel_time,
    request_within_walking_distance,
)
