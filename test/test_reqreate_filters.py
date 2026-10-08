"""Check the shared filter interface and each request retention rule."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/reqreate"))
from filters.filters import POI_FILTERS, REQUEST_FILTERS, passes_filters


def main():
    walking_distance = SimpleNamespace(within_limit=Mock(return_value=True))
    net = SimpleNamespace(polygon=box(0, 0, 2, 2), walking_distance=walking_distance)
    cfg = {"parameters": [{"name": "min_distance", "value": 100}]}
    req = {"origin": [0.5, 0.5], "destination": [1.5, 1.5],
           "direct_distance": 100, "direct_travel_time": 1}
    assert passes_filters(req, REQUEST_FILTERS, net, cfg)

    for change in ({"origin": [3, 3]}, {"direct_distance": 99},
                   {"direct_travel_time": 0}):
        assert not passes_filters(req | change, REQUEST_FILTERS, net, cfg)
    walking_distance.within_limit.return_value = False
    assert not passes_filters(req, REQUEST_FILTERS, net, cfg)

    assert passes_filters(SimpleNamespace(geometry=Point(1, 1)), POI_FILTERS, net, cfg)
    assert not passes_filters(SimpleNamespace(geometry=Point(3, 3)), POI_FILTERS, net, cfg)
    assert not passes_filters(req, REQUEST_FILTERS + (lambda candidate, net, cfg: False,),
                              net, cfg)
    print("Validated REQreate filter predicates and extension point")


if __name__ == "__main__":
    main()
