"""Check saved area demand: geometry, directed road distances, time and provenance.

Run with .venv/bin/python test/test_reqreate_area.py [pool_directory].
"""

import hashlib
import json
from pathlib import Path
import sys

import networkx as nx
import osmnx as ox
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/reqreate/area_550"
    pool_path = out_dir / "550_raw_requests.json"
    pool = json.loads(pool_path.read_text())
    meta = json.loads((out_dir / "550_raw_requests_metadata.json").read_text())
    paths = [ROOT / path for path in meta["inputs_sha256"]]
    area_path = next(path for path in paths if path.suffix == ".geojson")
    polygon = shape(json.loads(area_path.read_text())["geometry"])
    graph = ox.load_graphml(area_path.with_name("drive.graphml"))
    walk = ox.load_graphml(area_path.with_name("walk.graphml"))
    assert hashlib.sha256(pool_path.read_bytes()).hexdigest() == meta["pool_sha256"]
    for path, digest in meta["inputs_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    reqs = pool["requests"]
    assert len(reqs) == pool["num_data:"] == meta["request_count"]
    for idx, req in reqs.items():
        assert req["reqid"] == int(idx)
        for name in ("origin", "destination"):
            lat, lon = req[name]
            assert polygon.contains(Point(lon, lat))
            assert req[name + "node_drive"] in graph
            assert req[name + "node_walk"] in walk
        assert req["direct_distance"] >= 100
        assert req["direct_travel_time"] == int(req["direct_distance"] / 5.56) > 0
        assert 17100 <= req["earliest_departure"] <= 86510
        assert req["lead_time"] == req["lt_prebooked" if req["is_prebooked"] else "lt_dynamic"]
        assert req["time_stamp"] == req["earliest_departure"] - req["lead_time"]
        assert req["latest_arrival"] == req["earliest_departure"] + req["direct_travel_time"] + 600
    # Independently route a sample; avoid routing the entire generated pool twice.
    for req in list(reqs.values())[:20]:
        dist = nx.shortest_path_length(graph, req["originnode_drive"],
                                      req["destinationnode_drive"], weight="length")
        assert abs(dist - req["direct_distance"]) < 1e-8
    print(f"Validated {len(reqs)} area REQreate requests")


if __name__ == "__main__":
    main()
