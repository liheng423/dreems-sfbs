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
from scipy.stats import norm, uniform
from REQreate.passenger_requests import _generate_single_data_impl

from maps.area_network import build_area_net
from filters.filters import (BASE_REQUEST_FILTERS, REQUEST_FILTERS, passes_filters,
                             select_scheduled_bus_stops)
from filters.route_schedule import index_route_departures
from maps.pois import load_pois, set_poi_zones
from adapters.pool_output import write_pool
from src.output_adapters import (GRAPH_FILES, available_buslines, available_graphs, busline_dir,
                                 busline_path, create_request_dir, graph_dir, graph_path)
from src.reqreate.utils.graph_utils import nearest_graph_point


CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"
OPERATION_CFG_PATH = ROOT / "src/reqreate/operation/operation_profile.toml"
DAY_END_S = 86399


def clock_seconds(value):
    """Parse a same-day HH:MM[:SS] clock time."""
    if not isinstance(value, str):
        raise ValueError("time must be HH:MM or HH:MM:SS")
    parts = value.split(":")
    if len(parts) not in (2, 3) or any(len(part) != 2 or not part.isascii()
                                     or not part.isdigit() for part in parts):
        raise ValueError("time must be HH:MM or HH:MM:SS")
    hour, minute = map(int, parts[:2])
    second = int(parts[2]) if len(parts) == 3 else 0
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("time must be within one day (00:00–23:59:59)")
    return hour * 3600 + minute * 60 + second


def request_attributes(cfg, prebooked=False):
    """Build REQreate fields for the sampled request type and trip."""
    distributions = cfg["distributions"]
    return {
        "is_prebooked": {"type": "integer", "output_csv": True,
                         "pdf": [{"type": "uniform", "loc": int(prebooked), "scale": 0}]},
        "lt_dynamic": {"type": "integer", "time_unit": "s", "output_csv": False,
                       "pdf": [dict(distributions["lt_dynamic"])]},
        "lt_prebooked": {"type": "integer", "time_unit": "s", "output_csv": False,
                         "pdf": [dict(distributions["lt_prebooked"])]},
        "lead_time": {"type": "integer", "time_unit": "s",
                      "expression": "lt_prebooked if is_prebooked >= 0.5 else lt_dynamic"},
        "origin": {"type": "location"},
        "destination": {"type": "location"},
        "direct_distance": {"type": "integer", "length_unit": "m",
                            "expression": "dist_drive(origin,destination)",
                            "constraints": ["direct_distance >= min_distance"],
                            "output_csv": True},
        "direct_travel_time": {"type": "integer", "time_unit": "s",
                               "expression": "dtt(origin,destination)",
                               "constraints": ["direct_travel_time > 0"]},
    }


def expected_events(distribution, start_s, end_s):
    """Return the mean count for a configured event process."""
    if distribution["type"] != "poisson":
        raise ValueError("event-time distribution must be poisson")
    rate = distribution["rate_per_hour"]
    if rate < 0:
        raise ValueError("Poisson rate_per_hour must be nonnegative")
    return rate * (end_s - start_s) / 3600


def sample_arrivals(cfg):
    """Sample the configured dynamic arrivals and prebooked departures."""
    rng = np.random.default_rng(cfg["seed"])
    distributions = cfg["distributions"]
    prebooked_count = int(rng.poisson(expected_events(
        distributions["prebooked_earliest_departure"],
        cfg["demand_start_s"], cfg["simulation_end_s"])))
    dynamic_count = int(rng.poisson(expected_events(
        distributions["dynamic_time_stamp"],
        cfg["simulation_start_s"], cfg["simulation_end_s"])))
    prebooked = np.array([True] * prebooked_count + [False] * dynamic_count, dtype=bool)
    rng.shuffle(prebooked)
    count = len(prebooked)
    dynamic_ids = np.flatnonzero(~prebooked)
    prebooked_ids = np.flatnonzero(prebooked)
    times = np.zeros(count, dtype=int)
    times[dynamic_ids] = np.sort(rng.uniform(
        cfg["simulation_start_s"], cfg["simulation_end_s"], len(dynamic_ids)
    )).astype(int)
    times[prebooked_ids] = np.sort(rng.uniform(
        cfg["demand_start_s"], cfg["simulation_end_s"], len(prebooked_ids)
    )).astype(int)
    return prebooked, times


def set_request_times(req, prebooked, time, detour_factor):
    """Turn a request arrival or prebooked departure into all trip times."""
    if prebooked:
        req["earliest_departure"] = int(time)
        req["time_stamp"] = req["earliest_departure"] - req["lead_time"]
    else:
        req["time_stamp"] = int(time)
        req["earliest_departure"] = req["time_stamp"] + req["lead_time"]
    req["latest_arrival"] = int(req["earliest_departure"]
                                + req["direct_travel_time"] * detour_factor)


def load_config(busline_name):
    """Load demand settings and optional route stop data."""
    cfg = tomllib.loads(CFG_PATH.read_text())
    cfg.update(tomllib.loads(MAPS_CFG_PATH.read_text()))
    operation_cfg = tomllib.loads(OPERATION_CFG_PATH.read_text())["darp"]["attribute"]
    cfg["vehicle_speed_mps"] = operation_cfg["vehicle_speed"]
    cfg["detour_factor"] = operation_cfg["detour_factor"]
    filter_cfg = tomllib.loads(FILTERS_PATH.read_text())
    cfg["max_walking_distance_m"] = filter_cfg["max_walking_distance_m"]
    cfg["walking_speed_mps"] = filter_cfg["walking_speed_mps"]
    cfg["parameters"] = list(filter_cfg["parameters"])
    cfg["busline_name"] = busline_name
    cfg["places"] = []
    if busline_name is not None:
        route_dir = busline_dir(busline_name)
        cfg["places"] = json.loads(busline_path("stops", route_dir).read_text())
    times = cfg["simulation"]
    start_s = clock_seconds(times["start"])
    end_s = clock_seconds(times["end"])
    demand_start_s = clock_seconds(times["demand_start"])
    if not 0 <= start_s < end_s <= DAY_END_S:
        raise ValueError("simulation start and end must be ordered within 00:00–23:59:59")
    if not start_s <= demand_start_s < end_s:
        raise ValueError("demand start must be within the simulation window before its end")
    cfg["simulation_start_s"] = start_s
    cfg["simulation_end_s"] = end_s
    cfg["demand_start_s"] = demand_start_s
    distributions = cfg["distributions"]
    expected_dynamic = expected_events(distributions["dynamic_time_stamp"], start_s, end_s)
    expected_prebooked = expected_events(distributions["prebooked_earliest_departure"],
                                         demand_start_s, end_s)
    cfg["requests"] = expected_dynamic + expected_prebooked
    cfg["prebooked_probability"] = (expected_prebooked / cfg["requests"]
                                    if cfg["requests"] else 0)
    cfg["attributes"] = request_attributes(cfg)
    cfg["prebooked_attributes"] = request_attributes(cfg, prebooked=True)
    return cfg


def set_expected_requests(cfg, count):
    """Scale both configured event rates for the --requests override."""
    if count < 0 or (count and not cfg["requests"]):
        raise ValueError("--requests requires a nonnegative count and nonzero configured rates")
    scale = count / cfg["requests"] if cfg["requests"] else 1
    for name in ("dynamic_time_stamp", "prebooked_earliest_departure"):
        cfg["distributions"][name]["rate_per_hour"] *= scale
    cfg["requests"] = count


def prepare_network(cfg, area_path, poi_path):
    """Load the service area, route timetable, and POI sampling zones."""
    direction = cfg["distributions"]["radial_direction"]
    start, span = direction["loc"], direction["scale"]
    if direction["type"] != "uniform" or not (0 <= start < 360 and 0 <= span <= 360):
        raise ValueError("radial_direction must be uniform with 0 <= loc < 360 and 0 <= scale <= 360")
    net = build_area_net(area_path, cfg["places"], cfg["max_walking_distance_m"])
    net.vehicle_speed_mps = cfg["vehicle_speed_mps"]
    net.radial_direction = start, span
    if cfg["busline_name"] is not None:
        net.route_departures = index_route_departures(
            json.loads(busline_path("businfo", busline_dir(cfg["busline_name"])).read_text())
        )
    pois = load_pois(poi_path)
    set_poi_zones(net, pois, cfg["method_pois"]["rows"], cfg["method_pois"]["columns"])
    return net


def request_graph(attributes):
    """Give REQreate the fields and polygon location sampling it expects."""
    graph = nx.DiGraph()
    for name, attr in attributes.items():
        graph.add_node(name, **attr)
    graph.nodes["origin"]["subset_zones"] = False
    graph.nodes["destination"]["subset_zones"] = False
    return graph


def generate_candidates(cfg, net):
    """Sample request times and let REQreate fill in each trip."""
    params = {param["name"]: dict(param) for param in cfg["parameters"]}
    pdf = cfg["distributions"]["radial_distance"]
    distance_sampler = {"uniform": uniform, "normal": norm}.get(pdf["type"])
    if distance_sampler is None:
        raise ValueError("radial_distance distribution must be uniform or normal")
    graphs = {False: request_graph(cfg["attributes"]),
              True: request_graph(cfg["prebooked_attributes"])}

    np.random.seed(cfg["seed"])
    random.seed(cfg["seed"])
    prebooked_flags, times = sample_arrivals(cfg)
    count = len(prebooked_flags)
    cfg["generated_candidate_count"] = count
    reqs = {}
    for req_idx, prebooked in enumerate(prebooked_flags):
        graph = graphs[bool(prebooked)]
        distance = distance_sampler.rvs(loc=pdf["loc"], scale=pdf["scale"])
        req = _generate_single_data_impl(
            graph, net, list(graph.nodes), params, req_idx, True, distance,
            "origin", "destination", pdf["type"], pdf["loc"], pdf["scale"], None,
            [], 0, [], count, pd.DataFrame(),
        )
        set_request_times(req, bool(prebooked), times[req_idx], cfg["detour_factor"])
        reqs[str(req_idx)] = req
    return reqs


def filter_requests(cfg, net, reqs):
    """Keep feasible trips and attach scheduled bus stops when applicable."""
    request_filters = REQUEST_FILTERS if cfg["busline_name"] is not None else BASE_REQUEST_FILTERS
    reqs = {
        req_id: req for req_id, req in reqs.items()
        if cfg["demand_start_s"] <= req["earliest_departure"] <= cfg["simulation_end_s"]
        and req["latest_arrival"] <= cfg["simulation_end_s"]
        and (not req["is_prebooked"] or req["time_stamp"] < cfg["simulation_start_s"])
        and passes_filters(req, request_filters, net, cfg)
    }
    for req in reqs.values():
        for endpoint in ("origin", "destination"):
            req[f"{endpoint}_drive_point"] = nearest_graph_point(
                net.G_drive, node_id=req[f"{endpoint}node_drive"]
            )["point"]
    if cfg["busline_name"] is not None:
        stops = {stop["name"].removeprefix("Stop_"): stop for stop in cfg["places"]}
        for req in reqs.values():
            req.update(select_scheduled_bus_stops(req, net, cfg))
            for role in ("boarding", "alighting"):
                stop = stops[req[f"{role}_stop_id"]]
                req[f"{role}_stop_point"] = [stop["lat"], stop["lon"]]
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
    parser.add_argument("--requests", type=int, help="Override the expected candidate count")
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
    try:
        cfg = load_config(busline_name)
    except ValueError as exc:
        parser.error(str(exc))
    if args.requests is not None:
        try:
            set_expected_requests(cfg, args.requests)
        except ValueError as exc:
            parser.error(str(exc))
    route_dir = busline_dir(busline_name) if busline_name is not None else None
    area_dir = graph_dir(graph_name)
    area_path = graph_path("area", area_dir)
    poi_path = graph_path("pois", area_dir)
    pool = generate(cfg, area_path, poi_path)
    instance_dir = create_request_dir(busline_name or "no_bus", graph_name)
    pool_path = write_pool(cfg, busline_name, graph_name, route_dir, area_dir,
                           instance_dir, pool)
    print(f"Wrote {len(pool['requests'])} REQreate requests to {pool_path}")


if __name__ == "__main__":
    main()
