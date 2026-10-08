"""Generate raw REQreate demand within a saved service area.

REQreate samples request locations inside the GeoJSON and routes them on its
adjacent OSM graphs. No corridor feasibility filter or scenario selection runs.
"""

import argparse
import hashlib
from importlib import metadata
from functools import lru_cache
import json
import platform
import random
import subprocess
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import osmnx as ox
from shapely.geometry import shape
from REQreate.network_class import Network
from REQreate.passenger_requests import _generate_single_data_impl


ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "src/demand_busline/config_550.json"
AREA_PATH = ROOT / "data/reqreate/service_area_550/service_area.geojson"
OUT_DIR = ROOT / "data/reqreate/area_550"


class AreaNetwork(Network):
    """Route sampled OSM nodes directly on the saved directed drive graph."""

    @lru_cache(maxsize=1)
    def _return_estimated_distance_drive(self, org, dst):
        """Reuse the latest OD distance for its travel-time attribute.

        REQreate rejects unreachable pairs through its minimum-distance constraint.
        """
        try:
            return nx.shortest_path_length(self.G_drive, org, dst, weight="length")
        except nx.NetworkXNoPath:
            return -1

    def _return_estimated_travel_time_drive(self, org, dst):
        """Match REQreate's 20 km/h (5.56 m/s) distance-based estimate."""
        return int(self._return_estimated_distance_drive(org, dst) / 5.56)


def build_area_net(area_path):
    """Read the drawn GeoJSON Feature and its adjacent OSMnx GraphML files."""
    polygon = shape(json.loads(area_path.read_text())["geometry"])
    return AreaNetwork(
        "Route 550 service area",
        ox.load_graphml(area_path.with_name("drive.graphml")),
        ox.load_graphml(area_path.with_name("walk.graphml")),
        polygon, pd.DataFrame(),
    )


def sha256(path):
    """Fingerprint each input recorded beside the generated pool."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(cfg, area_path):
    """Run REQreate's seeded attribute sampler over every raw candidate."""
    net = build_area_net(area_path)
    params = {param["name"]: dict(param) for param in cfg["parameters"]
              if param["name"] != "all_stops"}
    params["set_geographic_dispersion"] = {"value": False}
    graph = nx.DiGraph()
    for attr in cfg["attributes"]:
        graph.add_node(attr["name"], **attr)
    # REQreate enables polygon sampling through subset_zones=False.
    for name in ("origin", "destination"):
        del graph.nodes[name]["subset_locations"]
        graph.nodes[name]["subset_zones"] = False
    graph.nodes["time_stamp"]["static_probability"] = 0

    np.random.seed(cfg["seed"])
    random.seed(cfg["seed"])
    names = [attr["name"] for attr in cfg["attributes"]]
    reqs = {}
    for req_idx in range(cfg["requests"]):
        reqs[str(req_idx)] = _generate_single_data_impl(
            graph, net, names, params, req_idx, False, 0, None, None, None,
            None, None, None, [], 0, [], cfg["requests"], pd.DataFrame(),
        )
    return {"num_data:": len(reqs), "requests": reqs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, help="Override the configured candidate count for a smoke run")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--service-area", type=Path, default=AREA_PATH,
                        help="GeoJSON Feature with drive.graphml and walk.graphml beside it")
    args = parser.parse_args()

    cfg = json.loads(CFG_PATH.read_text())
    if args.requests is not None:
        cfg["requests"] = args.requests
    in_paths = (CFG_PATH, args.service_area,
                args.service_area.with_name("drive.graphml"),
                args.service_area.with_name("walk.graphml"))
    pool = generate(cfg, args.service_area)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pool_path = args.out_dir / "550_raw_requests.json"
    pool_path.write_text(json.dumps(pool, ensure_ascii=False, separators=(",", ":")) + "\n")
    version = subprocess.check_output(
        ["git", "-C", str(ROOT / ".instance-generator"), "rev-parse", "HEAD"], text=True
    ).strip()
    meta = {
        "generator": "REQreate._generate_single_data_impl",
        "instance_generator_commit": version,
        "local_patch": "src/reqreate/instance_generator.patch",
        "local_patch_sha256": sha256(Path(__file__).with_name("instance_generator.patch")),
        "python_version": platform.python_version(),
        "package_versions": {
            name: metadata.version(name)
            for name in ("reqreate", "numpy", "pandas", "scipy", "osmnx", "networkx")
        },
        "seed": cfg["seed"],
        "request_count": cfg["requests"],
        "network_input": "GeoJSON service area and saved OSM drive/walk graphs",
        "travel_time_method": "REQreate 20 km/h distance fallback",
        "spatial_sampling": "REQreate polygon sampling within 500 m of a drive node",
        "distance_method": "Directed OSM shortest path weighted by length in metres",
        "inputs_sha256": {
            str(path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT)
                else path.resolve()): sha256(path)
            for path in in_paths
        },
        "pool_sha256": sha256(pool_path),
    }
    (args.out_dir / "550_raw_requests_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Wrote {len(pool['requests'])} raw REQreate requests to {pool_path}")


if __name__ == "__main__":
    main()
