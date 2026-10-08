"""Check the saved REQreate pool against Route 550's source inputs."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "src/reqreate/config_550.json"
POOL_PATH = ROOT / "data/reqreate/550_raw_requests.json"
META_PATH = ROOT / "data/reqreate/550_raw_requests_metadata.json"
DIST_PATH = ROOT / "data/distance_matrix_550.json"


def read_json(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cfg = read_json(CFG_PATH)
    pool = read_json(POOL_PATH)
    meta = read_json(META_PATH)
    dist_mat = read_json(DIST_PATH)
    places = {int(place["name"].removeprefix("Stop_")): place for place in cfg["places"]}
    dist_idx = {int(stop_id): idx for idx, stop_id in enumerate(dist_mat["stop_ids"])}
    params = {param["name"]: param["value"] for param in cfg["parameters"] if "value" in param}
    reqs = pool["requests"]

    assert len(reqs) == pool["num_data:"] == cfg["requests"]
    assert meta["pool_sha256"] == sha256(POOL_PATH)
    for path, digest in meta["inputs_sha256"].items():
        assert sha256(ROOT / path) == digest
    for idx, req in reqs.items():
        assert req["reqid"] == int(idx)
        org_id = req["originnode_drive"]
        dst_id = req["destinationnode_drive"]
        assert req["origin"] == [places[org_id]["lat"], places[org_id]["lon"]]
        assert req["destination"] == [places[dst_id]["lat"], places[dst_id]["lon"]]
        dist = dist_mat["distances_m"][dist_idx[org_id]][dist_idx[dst_id]]
        assert req["direct_distance"] == dist >= params["min_distance"]
        assert req["direct_travel_time"] == int(dist / 5.56) > 0
        assert params["min_early_departure"] <= req["earliest_departure"] <= params["max_early_departure"]
        assert req["is_prebooked"] in (0, 1)
        assert req["lead_time"] == req["lt_prebooked" if req["is_prebooked"] else "lt_dynamic"]
        assert req["time_stamp"] == req["earliest_departure"] - req["lead_time"]
        assert req["latest_arrival"] == req["earliest_departure"] + req["direct_travel_time"] + 600
    print(f"Validated {len(reqs)} raw REQreate requests")


if __name__ == "__main__":
    main()
