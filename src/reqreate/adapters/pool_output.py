"""Write the generated request pool and its reproducibility metadata."""

import hashlib
from importlib import metadata
import json
import platform
from pathlib import Path

from src.output_adapters import busline_path, graph_path, request_path, write_json


ROOT = Path(__file__).resolve().parents[3]
CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"


def sha256(path):
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_pool(cfg, busline_name, graph_name, route_dir, area_dir,
               instance_dir, pool):
    """Write the request pool and provenance metadata; return the pool path."""
    poi_path = graph_path("pois", area_dir)
    in_paths = [CFG_PATH, MAPS_CFG_PATH, FILTERS_PATH]
    if busline_name is not None:
        in_paths.extend(busline_path(name, route_dir) for name in ("stops", "businfo"))
    in_paths.extend(graph_path(name, area_dir) for name in ("area", "drive_graph", "walk_graph", "pois"))
    pool_path = write_json(request_path("pool", instance_dir), pool, compact=True)
    meta = {
        "busline": busline_name,
        "graph": graph_name,
        "generator": "REQreate._generate_single_data_impl",
        "python_version": platform.python_version(),
        "package_versions": {
            name: metadata.version(name)
            for name in ("reqreate", "numpy", "pandas", "scipy", "osmnx", "networkx")
        },
        "seed": cfg["seed"],
        "candidate_count": cfg["requests"],
        "request_count": pool["num_data:"],
        "network_input": "GeoJSON service area and saved OSM drive/walk graphs",
        "travel_time_method": "REQreate 20 km/h distance fallback",
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
    }
    write_json(request_path("metadata", instance_dir), meta)
    return pool_path
