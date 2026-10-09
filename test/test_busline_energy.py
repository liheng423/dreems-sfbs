"""Check paper-configured energy and route selection on tiny road graphs."""

import json
import math
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/busline"))
import energy
from energy import estimate_busline_energy


def test_paper_rate_and_same_node_distance():
    with (ROOT / "src/busline/energy.toml").open("rb") as file:
        config = tomllib.load(file)
    graph = nx.MultiDiGraph(crs="epsg:4326")
    graph.add_node(1, x=6.0, y=49.0)
    graph.add_node(2, x=6.01, y=49.0)
    graph.add_edge(1, 2, length=1000, highway="residential")
    businfo = {
        "route": {"route_id": "out"},
        "stops": [
            {"stop_id": "1", "stop_name": "First", "stop_lon": 6.0, "stop_lat": 49.0},
            {"stop_id": "2", "stop_name": "Second", "stop_lon": 6.01, "stop_lat": 49.0},
            {"stop_id": "3", "stop_name": "Third", "stop_lon": 6.0101, "stop_lat": 49.0},
        ],
        "patterns": [{"pattern_id": "a", "stop_ids": ["1", "2", "3"]}],
    }
    first, second = estimate_busline_energy(graph, businfo, config)
    assert (first["origin"], first["destination"]) == ("1", "2")
    assert first["distance_m"] == 1000
    assert math.isclose(first["energy_kwh"], 0.87)
    assert second["distance_source"] == "straight_line_same_node"
    assert second["distance_m"] > 0
    assert math.isclose(second["energy_kwh"], second["distance_m"] / 1000 * 0.87)

    config["scenario"]["temperature_case"] = "at_9_c"
    warmer, _ = estimate_busline_energy(graph, businfo, config)
    assert math.isclose(warmer["energy_kwh"], 0.87 * 1.29)


def test_command_selects_route():
    """A non-550 route uses its GTFS data, graph, and output directory."""
    with TemporaryDirectory(dir=ROOT) as directory:
        route_dir = Path(directory) / "buslines/605"
        road_graph_dir = Path(directory) / "graphs/605"
        route_dir.mkdir(parents=True)
        road_graph_dir.mkdir(parents=True)
        (route_dir / "businfo.json").write_text(json.dumps({
            "route": {"route_id": "605"},
            "stops": [
                {"stop_id": "A", "stop_name": "First", "stop_lon": 6.0, "stop_lat": 49.0},
                {"stop_id": "B", "stop_name": "Second", "stop_lon": 6.01, "stop_lat": 49.0},
            ],
            "patterns": [{"pattern_id": "out", "stop_ids": ["A", "B"]}],
        }))
        graph = nx.MultiDiGraph(crs="epsg:4326")
        graph.add_node(1, x=6.0, y=49.0)
        graph.add_node(2, x=6.01, y=49.0)
        graph.add_edge(1, 2, length=1000)
        ox.save_graphml(graph, filepath=road_graph_dir / "drive.graphml")

        with patch.object(sys, "argv", ["energy.py", "--route", "605"]), patch.object(
            energy, "busline_dir", return_value=route_dir
        ) as selected_route, patch.object(
            energy, "graph_dir", return_value=road_graph_dir
        ) as selected_graph:
            energy.main()

        selected_route.assert_called_once_with("605")
        selected_graph.assert_called_once_with("605")
        result = json.loads((route_dir / "energy.json").read_text())
        assert result["segments"][0]["energy_kwh"] == 0.87
        assert (result["segments"][0]["origin"], result["segments"][0]["destination"]) == ("A", "B")
        assert "Route 605" in result["status"]
        assert result["sources"]["businfo"].endswith("/buslines/605/businfo.json")
        assert result["sources"]["road_graph"].endswith("/graphs/605/drive.graphml")


if __name__ == "__main__":
    test_paper_rate_and_same_node_distance()
    test_command_selects_route()
