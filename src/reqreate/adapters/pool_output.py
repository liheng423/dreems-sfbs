"""Write the generated request pool and its reproducibility metadata."""

import hashlib
from importlib import metadata
import json
import platform
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"


def sha256(path):
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_pool(cfg, area_path, poi_path, out_dir, pool):
    """Write the request pool and provenance metadata; return the pool path."""
    in_paths = (CFG_PATH, MAPS_CFG_PATH, FILTERS_PATH, ROOT / cfg["stops_path"],
                ROOT / cfg["schedule_path"], area_path,
                area_path.with_name("drive.graphml"),
                area_path.with_name("walk.graphml"), poi_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    pool_path = out_dir / cfg["pool_file"]
    pool_path.write_text(json.dumps(pool, ensure_ascii=False, separators=(",", ":")) + "\n")
    version = subprocess.check_output(
        ["git", "-C", str(ROOT / ".instance-generator"), "rev-parse", "HEAD"], text=True
    ).strip()
    meta = {
        "generator": "REQreate._generate_single_data_impl",
        "instance_generator_commit": version,
        "local_patch": "src/reqreate/instance_generator.patch",
        "local_patch_sha256": sha256(ROOT / "src/reqreate/instance_generator.patch"),
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
        "spatial_sampling": "REQreate method_pois: POI-density zones and radial trip distances, followed by walking-access, walking-dominance, and scheduled Route 550 feasibility filters",
        "poi_count": len(json.loads(poi_path.read_text())["features"]),
        "distance_method": "Directed OSM shortest path weighted by length in metres",
        "inputs_sha256": {
            str(path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT)
                else path.resolve()): sha256(path)
            for path in in_paths
        },
        "pool_sha256": sha256(pool_path),
    }
    (out_dir / cfg["metadata_file"]).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    )
    return pool_path
