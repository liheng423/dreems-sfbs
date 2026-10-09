"""Check paper-configured energy on a tiny directed road graph."""

import math
import sys
import tomllib
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/busline"))
from energy import estimate_busline_energy


def test_paper_rate_and_same_node_distance():
    with (ROOT / "src/busline/energy.toml").open("rb") as file:
        config = tomllib.load(file)
    graph = nx.MultiDiGraph(crs="epsg:4326")
    graph.add_node(1, x=6.0, y=49.0)
    graph.add_node(2, x=6.01, y=49.0)
    graph.add_edge(1, 2, length=1000, highway="residential")
    network = {
        "coordinates": {"1": [6.0, 49.0], "2": [6.01, 49.0], "3": [6.0101, 49.0]},
        "stop_names": {"1": "First", "2": "Second", "3": "Third"},
        "patterns": [{"route_id": "out", "pattern_id": "a", "stops": [1, 2, 3]}],
    }
    first, second = estimate_busline_energy(graph, network, config)
    assert first["distance_m"] == 1000
    assert math.isclose(first["energy_kwh"], 0.87)
    assert second["distance_source"] == "straight_line_same_node"
    assert second["distance_m"] > 0
    assert math.isclose(second["energy_kwh"], second["distance_m"] / 1000 * 0.87)

    config["scenario"]["temperature_case"] = "at_9_c"
    warmer, _ = estimate_busline_energy(graph, network, config)
    assert math.isclose(warmer["energy_kwh"], 0.87 * 1.29)


if __name__ == "__main__":
    test_paper_rate_and_same_node_distance()
