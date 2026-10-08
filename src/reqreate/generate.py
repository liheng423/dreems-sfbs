"""Generate raw REQreate demand within a saved service area.

REQreate samples request locations inside the GeoJSON and routes them on its
adjacent OSM graphs. No corridor feasibility filter or scenario selection runs.
"""

import json
from pathlib import Path
import random
import tomllib

import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import uniform
from REQreate.passenger_requests import _generate_single_data_impl

from reqreate.maps.area_network import build_area_net
from filters.filters import REQUEST_FILTERS, passes_filters
from reqreate.maps.pois import load_pois, set_poi_zones
from reqreate.adapters.pool_output import write_pool


ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "src/reqreate/config_550.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"


def load_config():
    """Load generation, filter, and Route 550 stop settings."""
    cfg = tomllib.loads(CFG_PATH.read_text())
    filter_cfg = tomllib.loads(FILTERS_PATH.read_text())
    cfg["max_walking_distance_m"] = filter_cfg["max_walking_distance_m"]
    cfg["parameters"].extend(filter_cfg["parameters"])
    cfg["places"] = json.loads((ROOT / cfg["stops_path"]).read_text())
    return cfg


def generate(cfg, area_path, poi_path):
    """Generate candidates, then apply the registered request filters."""
    net = build_area_net(area_path, cfg["places"], cfg["max_walking_distance_m"])
    pois = load_pois(cfg, net, area_path, poi_path)
    set_poi_zones(net, pois, cfg["method_pois"]["rows"], cfg["method_pois"]["columns"])
    params = {param["name"]: dict(param) for param in cfg["parameters"]}
    method = cfg["method_pois"]
    pdf = method["pdf"]
    graph = nx.DiGraph()
    for attr in cfg["attributes"]:
        graph.add_node(attr["name"], **attr)
    # REQreate enables polygon sampling through subset_zones=False.
    graph.nodes["origin"]["subset_zones"] = False
    graph.nodes["destination"]["subset_zones"] = False
    graph.nodes["time_stamp"]["static_probability"] = 0

    np.random.seed(cfg["seed"])
    random.seed(cfg["seed"])
    names = [attr["name"] for attr in cfg["attributes"]]
    reqs = {}
    for req_idx in range(cfg["requests"]):
        distance = uniform.rvs(loc=pdf["loc"], scale=pdf["scale"])
        reqs[str(req_idx)] = _generate_single_data_impl(
            graph, net, names.copy(), params, req_idx, True, distance,
            *method["locations"], pdf["type"], pdf["loc"], pdf["scale"], None,
            [], 0, [], cfg["requests"], pd.DataFrame(),
        )
    reqs = {
        req_id: req for req_id, req in reqs.items()
        if passes_filters(req, REQUEST_FILTERS, net, cfg)
    }
    return {"num_data:": len(reqs), "requests": reqs}


def main():
    cfg = load_config()
    area_path = ROOT / cfg["service_area_path"]
    out_dir = ROOT / cfg["output_dir"]
    poi_path = out_dir / cfg["poi_cache_file"]
    pool = generate(cfg, area_path, poi_path)
    pool_path = write_pool(cfg, area_path, poi_path, out_dir, pool)
    print(f"Wrote {len(pool['requests'])} raw REQreate requests to {pool_path}")


if __name__ == "__main__":
    main()
