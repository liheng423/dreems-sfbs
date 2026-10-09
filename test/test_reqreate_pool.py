"""Check the saved REQreate pool against Route 550's source inputs."""

import hashlib
import json
import tomllib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.output_adapters import request_path


ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
INSTANCE_DIR = sorted((ROOT / "data/requests").glob("550_550_[0-9]*"))[-1]
POOL_PATH = request_path("pool", INSTANCE_DIR)
META_PATH = request_path("metadata", INSTANCE_DIR)


def read_json(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cfg = tomllib.loads(CFG_PATH.read_text())
    filter_cfg = tomllib.loads((ROOT / "src/reqreate/filters/filters.toml").read_text())
    pool = read_json(POOL_PATH)
    meta = read_json(META_PATH)
    params = {param["name"]: param["value"]
              for param in cfg["parameters"] + filter_cfg["parameters"] if "value" in param}
    reqs = pool["requests"]

    assert len(reqs) == pool["num_data:"] == meta["request_count"] <= cfg["requests"]
    assert meta["pool_sha256"] == sha256(POOL_PATH)
    for path, digest in meta["inputs_sha256"].items():
        assert sha256(ROOT / path) == digest
    for idx, req in reqs.items():
        assert req["reqid"] == int(idx)
        assert req["direct_distance"] >= params["min_distance"]
        assert req["direct_travel_time"] == int(req["direct_distance"] / 5.56) > 0
        assert params["min_early_departure"] <= req["earliest_departure"] <= params["max_early_departure"]
        assert req["is_prebooked"] in (0, 1)
        assert req["lead_time"] == req["lt_prebooked" if req["is_prebooked"] else "lt_dynamic"]
        assert req["time_stamp"] == req["earliest_departure"] - req["lead_time"]
        assert req["latest_arrival"] == req["earliest_departure"] + req["direct_travel_time"] + 600
    print(f"Validated {len(reqs)} raw REQreate requests")


if __name__ == "__main__":
    main()
