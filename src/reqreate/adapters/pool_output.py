"""Write the generated request pool and its reproducibility metadata."""

import hashlib
import csv
from importlib import metadata
import json
import platform
from pathlib import Path
import tomllib

from src.output_adapters import (DARP_OUTPUT_FIELDS, SFBS_OUTPUT_FIELDS, busline_path,
                                 graph_path, request_path, write_json)


ROOT = Path(__file__).resolve().parents[3]
CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"
OPERATIONS_PATH = ROOT / "src/reqreate/operation/operation_profile.toml"
VEHICLES_PATH = ROOT / "src/reqreate/operation/veh_profile.toml"


def write_requests_csv(path, requests, task):
    """Write one request per row, preserving array values as JSON text."""
    base_fields = SFBS_OUTPUT_FIELDS if task == "SFBS" else DARP_OUTPUT_FIELDS
    fields = [*base_fields, *sorted(set().union(*(req.keys() for req in requests.values()))
                                    - set(base_fields))]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for req in requests.values():
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, tuple, dict))
                             else value for key, value in req.items()})
    return path


def sha256(path):
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_pool(cfg, busline_name, graph_name, route_dir, area_dir,
               instance_dir, pool):
    """Write the request pool and provenance metadata; return the pool path."""
    poi_path = graph_path("pois", area_dir)
    in_paths = [CFG_PATH, MAPS_CFG_PATH, FILTERS_PATH, OPERATIONS_PATH, VEHICLES_PATH]
    if busline_name is not None:
        in_paths.extend(busline_path(name, route_dir) for name in ("stops", "businfo"))
    in_paths.extend(graph_path(name, area_dir) for name in ("area", "drive_graph", "walk_graph", "pois", "depot"))
    config = tomllib.loads(OPERATIONS_PATH.read_text())
    profiles = tomllib.loads(VEHICLES_PATH.read_text())["profiles"]
    mode = cfg["task"].lower()
    attributes = config[mode]["attribute"]
    timing = config[mode]["operation"]
    operations = {mode: {
        "start_time": timing["start"],
        "end_time": timing["end"],
        "average_speed_mps": attributes["vehicle_speed"],
        "vehicle_count": attributes["num_of_vehicles"],
        "vehicle_type": attributes["profile"],
        "temperature_case": attributes["temperature_case"],
        "vehicle": profiles[attributes["profile"]],
        "detour_factor": attributes["detour_factor"],
    }}
    pool_path = write_json(request_path("pool", instance_dir), pool, compact=True)
    csv_path = write_requests_csv(request_path("csv", instance_dir), pool["requests"], cfg["task"])
    operations_path = write_json(request_path("operations", instance_dir), operations)
    meta = {
        "task": cfg["task"],
        "busline": busline_name,
        "graph": graph_name,
        "generator": "REQreate._generate_single_data_impl + configured time sampler",
        "python_version": platform.python_version(),
        "package_versions": {
            name: metadata.version(name)
            for name in ("reqreate", "numpy", "pandas", "scipy", "osmnx", "networkx")
        },
        "seed": cfg["seed"],
        "candidate_count": cfg.get("generated_candidate_count", cfg["requests"]),
        "mean_candidate_count": cfg["requests"],
        "prebooked_probability": cfg["prebooked_probability"],
        "dynamic_time_stamp_distribution": cfg["distributions"]["dynamic_time_stamp"],
        "prebooked_earliest_departure_distribution": cfg["distributions"]["prebooked_earliest_departure"],
        "request_count": pool["num_data:"],
        "simulation_start_s": cfg["simulation_start_s"],
        "simulation_end_s": cfg["simulation_end_s"],
        "demand_start_s": cfg["demand_start_s"],
        "network_input": "GeoJSON service area and saved OSM drive/walk graphs",
        "vehicle_speed_mps": cfg["vehicle_speed_mps"],
        "detour_factor": cfg["detour_factor"],
        "travel_time_method": f"Directed road distance / {cfg['task']} vehicle_speed",
        "spatial_sampling": (
            "REQreate method_pois: POI-density zones and radial trip distances, "
            "followed by area, minimum-distance, and positive-travel-time filters"
            + (", plus walking-access, walking-dominance, and scheduled-bus feasibility filters"
               if cfg["task"] == "SFBS" else "")
        ),
        "bus_filters_enabled": cfg["task"] == "SFBS",
        "poi_count": len(json.loads(poi_path.read_text())["features"]),
        "distance_method": "Directed OSM shortest path weighted by length in metres",
        "inputs_sha256": {
            str(path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT)
                else path.resolve()): sha256(path)
            for path in in_paths
        },
        "pool_sha256": sha256(pool_path),
        "csv_sha256": sha256(csv_path),
        "operations_sha256": sha256(operations_path),
    }
    write_json(request_path("metadata", instance_dir), meta)
    return pool_path
