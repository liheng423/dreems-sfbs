"""Check configurable radial bearings used by the request sampler."""

import math
from pathlib import Path
import sys
import tomllib

from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/reqreate"))

from maps.area_network import AreaNetwork


def test_direction_sampling():
    direction = tomllib.loads((ROOT / "src/reqreate/request_gen.toml").read_text())[
        "distributions"]["radial_direction"]
    assert direction == {"type": "uniform", "loc": 0, "scale": 360}
    net = object.__new__(AreaNetwork)
    area = box(-1, -1, 1, 1)

    net.radial_direction = 90, 0
    east = net._get_random_coord_radius(0, 0, 1000, area, 7)
    assert east.x > 0 and abs(east.y) < 1e-12

    net.radial_direction = 350, 20  # clockwise range crossing north
    point = net._get_random_coord_radius(0, 0, 1000, area, 7)
    bearing = math.degrees(math.atan2(point.x, point.y)) % 360
    assert bearing >= 350 or bearing <= 10


if __name__ == "__main__":
    test_direction_sampling()
