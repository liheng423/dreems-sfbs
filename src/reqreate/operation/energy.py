"""Estimate stop-to-stop electric bus energy from selected vehicle rates."""

import argparse
import json
import sys
import tomllib
from pathlib import Path

import networkx as nx
import osmnx as ox

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.output_adapters import busline_dir, busline_path, graph_dir, graph_path, write_json
from src.reqreate.utils.graph_utils import GraphNodeIndex


def consumption_kwh_per_km(config: dict) -> float:
    """Return the selected vehicle's rate at the configured temperature."""
    scenario = config["scenario"]
    profile = config["profiles"][scenario["profile"]]
    temperature_case = scenario["temperature_case"]
    increase_pct = (0 if temperature_case == "reference_20_22_c"
                    else profile["relative_increase_pct"][temperature_case])
    return profile["reference_kwh_per_km"] * (1 + increase_pct / 100)


def estimate_busline_energy(graph: nx.MultiDiGraph, businfo: dict, config: dict) -> list[dict]:
    """Return energy for each consecutive pair in every directed bus pattern.

    ``businfo`` is the selected route's GTFS timetable; ``config`` combines
    the operation scenario and vehicle profiles. Energy is road distance in km
    times the selected profile's kWh/km, adjusted only when that profile has
    a rate for the chosen temperature case. It is not a route measurement.
    Two stops snapping to one simplified graph node use their straight-line
    distance as a marked lower bound.
    """
    rate = consumption_kwh_per_km(config)

    stops = {stop["stop_id"]: stop for stop in businfo["stops"]}
    index = GraphNodeIndex(graph)
    stop_nodes = {
        stop_id: index.nearest(stop["stop_lat"], stop["stop_lon"])["node_id"]
        for stop_id, stop in stops.items()
    }
    segments = []
    for pattern in businfo["patterns"]:
        route_stops = pattern.get("selected_stop_ids", pattern["stop_ids"])
        for origin, destination in zip(route_stops, route_stops[1:]):
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
                "energy_kwh": distance_m / 1000 * rate,
            })
    return segments


def main():
    """Write segment energy for the route selected on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    with Path(__file__).with_name("veh_profile.toml").open("rb") as file:
        config = tomllib.load(file)
    with Path(__file__).with_name("operation_profile.toml").open("rb") as file:
        config["scenario"] = tomllib.load(file)["sfbs"]["attribute"]
    route_dir = busline_dir(args.route)
    drive_path = graph_path("drive_graph", graph_dir(args.route))
    businfo = json.loads(busline_path("businfo", route_dir).read_text())
    stops_path = busline_path("stops", route_dir)
    if stops_path.is_file():
        source_ids = {source["stop_id"] for source in businfo["stops"]}
        for stop in json.loads(stops_path.read_text()):
            stop_id = stop["name"].removeprefix("Stop_")
            if stop_id not in source_ids:
                businfo["stops"].append({"stop_id": stop_id, "stop_name": stop["name"],
                                         "stop_lat": stop["lat"], "stop_lon": stop["lon"]})
    graph = ox.load_graphml(drive_path)
    segments = estimate_busline_energy(graph, businfo, config)
    result = {
        "schema_version": 2,
        "sources": {
            "businfo": str(busline_path("businfo", route_dir).relative_to(root)),
            "road_graph": str(drive_path.relative_to(root)),
            "vehicle_profiles": "src/reqreate/operation/veh_profile.toml",
            "operation_profile": "src/reqreate/operation/operation_profile.toml",
        },
        "scenario": config["scenario"],
        "profile": config["profiles"][config["scenario"]["profile"]],
        "status": f"Illustrative vehicle profile; actual Route {args.route} bus model and ambient temperature are unverified.",
        "method": "Directed shortest road path distance times selected profile kWh/km. Same-node stop pairs use marked straight-line lower bounds.",
        "segments": segments,
    }
    write_json(busline_path("energy", route_dir), result)


if __name__ == "__main__":
    main()
