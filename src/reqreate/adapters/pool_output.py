"""Write the generated request pool and its reproducibility metadata."""

import hashlib
from importlib import metadata
import json
import platform
from pathlib import Path
import tomllib

from src.output_adapters import busline_path, graph_path, request_path, write_json


ROOT = Path(__file__).resolve().parents[3]
CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"
OPERATIONS_PATH = ROOT / "src/reqreate/operation/operation_profile.toml"
VEHICLES_PATH = ROOT / "src/reqreate/operation/veh_profile.toml"


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
    operations = {}
    for mode in ("darp", "sfbs"):
        attributes = config[mode]["attribute"]
        timing = config[mode]["operation"]
        operations[mode] = {
            "start_time": timing["start"],
            "end_time": timing["end"],
            "average_speed_mps": attributes["vehicle_speed"],
            "vehicle_count": attributes["num_of_vehicles"],
            "vehicle_type": attributes["profile"],
            "temperature_case": attributes["temperature_case"],
            "vehicle": profiles[attributes["profile"]],
        }
    operations["darp"]["detour_factor"] = config["darp"]["attribute"]["detour_factor"]
    pool_path = write_json(request_path("pool", instance_dir), pool, compact=True)
    operations_path = write_json(request_path("operations", instance_dir), operations)
    meta = {
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
        "travel_time_method": "Directed road distance / DARP vehicle_speed",
        "spatial_sampling": (
            "REQreate method_pois: POI-density zones and radial trip distances, "
            "followed by area, minimum-distance, and positive-travel-time filters"
            + (", plus walking-access, walking-dominance, and scheduled-bus feasibility filters"
               if busline_name is not None else "")
        ),
        "bus_filters_enabled": busline_name is not None,
        "poi_count": len(json.loads(poi_path.read_text())["features"]),
        "distance_method": "Directed OSM shortest path weighted by length in metres",
        "inputs_sha256": {
            str(path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT)
                else path.resolve()): sha256(path)
            for path in in_paths
        },
        "pool_sha256": sha256(pool_path),
        "operations_sha256": sha256(operations_path),
    }
    write_json(request_path("metadata", instance_dir), meta)
    return pool_path
