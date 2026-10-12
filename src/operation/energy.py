"""Estimate stop-to-stop electric bus energy from measured fleet rates.

The rates come from Jablonski et al., NEIS 2023, Table 1. See README.md for
the fleet and temperature conditions under which those rates were measured.
"""

import argparse
import json
import sys
import tomllib
from pathlib import Path

import networkx as nx
import osmnx as ox

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.output_adapters import busline_dir, busline_path, graph_dir, graph_path, write_json


def estimate_busline_energy(graph: nx.MultiDiGraph, businfo: dict, config: dict) -> list[dict]:
    """Return energy for each consecutive pair in every directed bus pattern.

    ``businfo`` is the selected route's GTFS timetable; ``config`` is parsed
    ``energy.toml``. Energy is road distance in km times the selected
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

    stops = {stop["stop_id"]: stop for stop in businfo["stops"]}
    stop_nodes = {
        stop_id: ox.distance.nearest_nodes(graph, stop["stop_lon"], stop["stop_lat"])
        for stop_id, stop in stops.items()
    }
    segments = []
    for pattern in businfo["patterns"]:
        for origin, destination in zip(pattern["stop_ids"], pattern["stop_ids"][1:]):
            path = nx.shortest_path(graph, stop_nodes[origin], stop_nodes[destination], weight="length")
            distance_m = sum(min(edge["length"] for edge in graph[start][end].values())
                             for start, end in zip(path, path[1:]))
            distance_source = "road_graph"
            if len(path) == 1:
                origin_stop = stops[origin]
                destination_stop = stops[destination]
                distance_m = ox.distance.great_circle(
                    origin_stop["stop_lat"], origin_stop["stop_lon"],
                    destination_stop["stop_lat"], destination_stop["stop_lon"])
                distance_source = "straight_line_same_node"
            segments.append({
                "route_id": businfo["route"]["route_id"],
                "pattern_id": pattern["pattern_id"],
                "origin": origin,
                "destination": destination,
                "origin_name": stops[origin]["stop_name"],
                "destination_name": stops[destination]["stop_name"],
                "distance_m": distance_m,
                "distance_source": distance_source,
                "energy_kwh": distance_m / 1000 * consumption_kwh_per_km,
            })
    return segments


def main():
    """Write segment energy for the route selected on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config_path = Path(__file__).with_name("energy.toml")
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    route_dir = busline_dir(args.route)
    drive_path = graph_path("drive_graph", graph_dir(args.route))
    businfo = json.loads(busline_path("businfo", route_dir).read_text())
    graph = ox.load_graphml(drive_path)
    segments = estimate_busline_energy(graph, businfo, config)
    result = {
        "schema_version": 2,
        "sources": {
            "businfo": str(busline_path("businfo", route_dir).relative_to(root)),
            "road_graph": str(drive_path.relative_to(root)),
            "energy_config": "src/busline/energy.toml",
            "paper": ".ref/papers/Analysis_and_Characterization_of_the_Energy_Consumption_in_an_Electric_Bus_Fleet.pdf",
            "paper_location": "Table 1, printed page 256",
        },
        "scenario": config["scenario"],
        "profile": config["profiles"][config["scenario"]["profile"]],
        "status": f"Illustrative paper profile; actual Route {args.route} bus model and ambient temperature are unverified.",
        "method": "Directed shortest road path distance times measured profile kWh/km at selected paper temperature case. Same-node stop pairs use marked straight-line lower bounds.",
        "segments": segments,
    }
    write_json(busline_path("energy", route_dir), result)


if __name__ == "__main__":
    main()
