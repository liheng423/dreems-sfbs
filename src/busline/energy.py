"""Estimate stop-to-stop electric bus energy from measured fleet rates.

The rates come from Jablonski et al., NEIS 2023, Table 1. See README.md for
the fleet and temperature conditions under which those rates were measured.
"""

import json
import tomllib
from pathlib import Path

import networkx as nx
import osmnx as ox


def estimate_busline_energy(graph: nx.MultiDiGraph, network: dict, config: dict) -> list[dict]:
    """Return energy for each consecutive pair in every directed bus pattern.

    ``network`` is ``data/corridor_550.json``'s network object; ``config`` is
    parsed ``energy.toml``. Energy is road distance in km times the selected
    paper profile's median kWh/km, adjusted only at temperature cases directly
    reported in Table 1. It is a fleet-rate estimate, not a route measurement.
    Two stops snapping to one simplified graph node use their straight-line
    distance as a marked lower bound.
    """
    scenario = config["scenario"]
    profile = config["profiles"][scenario["profile"]]
    temperature_case = scenario["temperature_case"]
    increase_pct = (0 if temperature_case == "reference_20_22_c"
                    else profile["relative_increase_pct"][temperature_case])
    consumption_kwh_per_km = profile["reference_kwh_per_km"] * (1 + increase_pct / 100)

    coordinates = network["coordinates"]
    stop_nodes = {
        int(stop_id): ox.distance.nearest_nodes(graph, lon, lat)
        for stop_id, (lon, lat) in coordinates.items()
    }
    segments = []
    for pattern in network["patterns"]:
        for origin, destination in zip(pattern["stops"], pattern["stops"][1:]):
            path = nx.shortest_path(graph, stop_nodes[origin], stop_nodes[destination], weight="length")
            distance_m = sum(min(edge["length"] for edge in graph[start][end].values())
                             for start, end in zip(path, path[1:]))
            distance_source = "road_graph"
            if len(path) == 1:
                origin_lon, origin_lat = coordinates[str(origin)]
                destination_lon, destination_lat = coordinates[str(destination)]
                distance_m = ox.distance.great_circle(
                    origin_lat, origin_lon, destination_lat, destination_lon)
                distance_source = "straight_line_same_node"
            segments.append({
                "route_id": pattern["route_id"],
                "pattern_id": pattern["pattern_id"],
                "origin": origin,
                "destination": destination,
                "origin_name": network["stop_names"][str(origin)],
                "destination_name": network["stop_names"][str(destination)],
                "distance_m": distance_m,
                "distance_source": distance_source,
                "energy_kwh": distance_m / 1000 * consumption_kwh_per_km,
            })
    return segments


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    config_path = Path(__file__).with_name("energy.toml")
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    network = json.loads((root / "data/corridor_550.json").read_text())["network"]
    graph = ox.load_graphml(root / "data/reqreate/service_area_550/drive.graphml")
    segments = estimate_busline_energy(graph, network, config)
    result = {
        "schema_version": 2,
        "sources": {
            "network": "data/corridor_550.json",
            "road_graph": "data/reqreate/service_area_550/drive.graphml",
            "energy_config": "src/busline/energy.toml",
            "paper": ".ref/papers/Analysis_and_Characterization_of_the_Energy_Consumption_in_an_Electric_Bus_Fleet.pdf",
            "paper_location": "Table 1, printed page 256",
        },
        "scenario": config["scenario"],
        "profile": config["profiles"][config["scenario"]["profile"]],
        "status": "Illustrative paper profile; actual Route 550 bus model and ambient temperature are unverified.",
        "method": "Directed shortest road path distance times measured profile kWh/km at selected paper temperature case. Same-node stop pairs use marked straight-line lower bounds.",
        "segments": segments,
    }
    output_path = root / "data/busline/energy_550.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
