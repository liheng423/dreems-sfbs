"""Generate raw REQreate demand within a saved service area.

REQreate samples request locations inside the GeoJSON and routes them on its
adjacent OSM graphs. Walking and scheduled-bus feasibility filters run
before the raw request pool is saved.
"""

import argparse
import json
from pathlib import Path
import random
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import uniform
from REQreate.passenger_requests import _generate_single_data_impl

from maps.area_network import build_area_net
from filters.filters import (BASE_REQUEST_FILTERS, REQUEST_FILTERS, passes_filters,
                             select_scheduled_bus_stops)
from filters.route_schedule import index_route_departures
from maps.pois import load_pois, set_poi_zones
from adapters.pool_output import write_pool
from src.output_adapters import (GRAPH_FILES, available_buslines, available_graphs, busline_dir,
                                 busline_path, create_request_dir, graph_dir, graph_path)


CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"


def load_config(busline_name):
    """Merge settings with route data when a busline was selected."""
    cfg = tomllib.loads(CFG_PATH.read_text())
    cfg.update(tomllib.loads(MAPS_CFG_PATH.read_text()))
    filter_cfg = tomllib.loads(FILTERS_PATH.read_text())
    cfg["max_walking_distance_m"] = filter_cfg["max_walking_distance_m"]
    cfg["walking_speed_mps"] = filter_cfg["walking_speed_mps"]
    cfg["parameters"].extend(filter_cfg["parameters"])
    cfg["busline_name"] = busline_name
    if busline_name is None:
        cfg["places"] = []
        return cfg
    route_dir = busline_dir(busline_name)
    cfg["places"] = json.loads(busline_path("stops", route_dir).read_text())
    businfo = json.loads(busline_path("businfo", route_dir).read_text())
    start_s = businfo["operating_hours"]["start_seconds"]
    end_s = businfo["operating_hours"]["end_seconds"]
    for param in cfg["parameters"]:
        if param["name"] == "min_early_departure":
            param["value"] = start_s
        elif param["name"] == "max_early_departure":
            param["value"] = end_s
    departure_pdf = cfg["attributes"]["earliest_departure"]["pdf"][0]
    departure_pdf["loc"] = (start_s + end_s) / 2
    departure_pdf["scale"] = (end_s - start_s) / 6
    return cfg


def generate(cfg, area_path, poi_path):
    """Apply area and trip filters, plus bus filters when a route is selected."""
    net = build_area_net(area_path, cfg["places"], cfg["max_walking_distance_m"])
    if cfg["busline_name"] is not None:
        net.route_departures = index_route_departures(
            json.loads(busline_path("businfo", busline_dir(cfg["busline_name"])).read_text())
        )
    pois = load_pois(poi_path)
    set_poi_zones(net, pois, cfg["method_pois"]["rows"], cfg["method_pois"]["columns"])
    params = {param["name"]: dict(param) for param in cfg["parameters"]}
    method = cfg["method_pois"]
    pdf = method["pdf"]
    graph = nx.DiGraph()
    for name, attr in cfg["attributes"].items():
        graph.add_node(name, **attr)
    # REQreate enables polygon sampling through subset_zones=False.
    graph.nodes["origin"]["subset_zones"] = False
    graph.nodes["destination"]["subset_zones"] = False
    graph.nodes["time_stamp"]["static_probability"] = 0

    np.random.seed(cfg["seed"])
    random.seed(cfg["seed"])
    names = list(cfg["attributes"])
    reqs = {}
    for req_idx in range(cfg["requests"]):
        distance = uniform.rvs(loc=pdf["loc"], scale=pdf["scale"])
        reqs[str(req_idx)] = _generate_single_data_impl(
            graph, net, names.copy(), params, req_idx, True, distance,
            *method["locations"], pdf["type"], pdf["loc"], pdf["scale"], None,
            [], 0, [], cfg["requests"], pd.DataFrame(),
        )
    request_filters = REQUEST_FILTERS if cfg["busline_name"] is not None else BASE_REQUEST_FILTERS
    reqs = {
        req_id: req for req_id, req in reqs.items()
        if passes_filters(req, request_filters, net, cfg)
    }
    if cfg["busline_name"] is not None:
        for req in reqs.values():
            req.update(select_scheduled_bus_stops(req, net, cfg))
    return {"num_data:": len(reqs), "requests": reqs}


def choose_source(label, names):
    """Ask which numbered busline to use, or let the user skip it."""
    if not names:
        print(f"No available {label}s.")
    else:
        print(f"Available {label}s:")
    for number, name in enumerate(names, 1):
        print(f"  {number}. {name}")
    print("  0. Skip (no busline; bus filters disabled)")
    number = int(input(f"Choose {label} number: "))
    if not 0 <= number <= len(names):
        raise ValueError(f"Invalid {label} number: {number}")
    return names[number - 1] if number else None


def main():
    """Generate a request instance on the selected map and busline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True, help="Saved service-area map name")
    parser.add_argument("--busline", help="Route to use; prompts for one when omitted")
    parser.add_argument("--requests", type=int, help="Override the candidate count")
    args = parser.parse_args()
    graph_names = available_graphs()
    if args.map not in graph_names:
        area_dir = graph_dir(args.map)
        if area_dir.is_dir():
            missing = [graph_path(name, area_dir).name for name in GRAPH_FILES
                       if not graph_path(name, area_dir).is_file()]
            parser.error(f"Map {args.map!r} is missing {', '.join(missing)}; save it with select-area")
        parser.error(f"Map {args.map!r} is unavailable; choose from: {', '.join(graph_names)}")
    busline_names = available_buslines()
    if args.busline and args.busline not in busline_names:
        parser.error(f"Busline {args.busline!r} is unavailable; choose from: {', '.join(busline_names)}")
    graph_name = args.map
    busline_name = args.busline if args.busline else choose_source("busline", busline_names)
    if busline_name is None:
        print("No busline selected; bus-related filters disabled.")
    cfg = load_config(busline_name)
    if args.requests is not None:
        cfg["requests"] = args.requests
    route_dir = busline_dir(busline_name) if busline_name is not None else None
    area_dir = graph_dir(graph_name)
    area_path = graph_path("area", area_dir)
    poi_path = graph_path("pois", area_dir)
    pool = generate(cfg, area_path, poi_path)
    instance_dir = create_request_dir(busline_name or "no_bus", graph_name)
    pool_path = write_pool(cfg, busline_name, graph_name, route_dir, area_dir,
                           instance_dir, pool)
    print(f"Wrote {len(pool['requests'])} raw REQreate requests to {pool_path}")


if __name__ == "__main__":
    main()
