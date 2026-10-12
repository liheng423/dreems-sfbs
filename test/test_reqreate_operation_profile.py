"""Check that DARP operation settings control request travel and arrival times."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import networkx as nx
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/reqreate"))

from src.reqreate import generate
from maps.area_network import AreaNetwork


def main():
    """A changed profile must change road travel and derived arrival times."""
    with TemporaryDirectory() as directory:
        profile_path = Path(directory) / "operation_profile.toml"
        profile_path.write_text("[darp.attribute]\nvehicle_speed = 10.0\ndetour_factor = 2.0\n")
        with patch.object(generate, "OPERATION_CFG_PATH", profile_path):
            cfg = generate.load_config(None)

    assert cfg["vehicle_speed_mps"] == 10.0
    req = {"lead_time": 300, "direct_travel_time": 12}
    generate.set_request_times(req, False, 30000, cfg)
    assert (req["time_stamp"], req["earliest_departure"], req["latest_arrival"]) == (
        30000, 30300, 31254)
    assert (req["pickup_from"], req["pickup_to"], req["dropoff_from"], req["dropoff_to"], req["service_time"]) == (
        30300, 31200, 30354, 31254, 30)
    cfg["distributions"]["pickup_timewindow"]["loc"] = 600
    cfg["distributions"]["dropoff_timewindow"]["loc"] = 300
    cfg["distributions"]["service_time"]["loc"] = 45
    changed = {"lead_time": 300, "direct_travel_time": 12}
    generate.set_request_times(changed, False, 30000, cfg)
    assert (changed["pickup_to"] - changed["pickup_from"],
            changed["dropoff_to"] - changed["dropoff_from"], changed["service_time"]) == (600, 300, 45)
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, length=120)
    net = AreaNetwork("test", graph, graph, box(0, 0, 1, 1), pd.DataFrame())
    net.vehicle_speed_mps = cfg["vehicle_speed_mps"]
    assert net._return_estimated_travel_time_drive(1, 2) == 12
    print("Validated DARP operation profile demand settings")


if __name__ == "__main__":
    main()
