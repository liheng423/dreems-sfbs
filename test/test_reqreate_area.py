"""Check saved area demand: geometry, directed road distances, time and provenance.

Run with .venv/bin/python test/test_reqreate_area.py.
"""

import hashlib
import json
from pathlib import Path
import tomllib

import networkx as nx
import osmnx as ox
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]


def main():
    cfg = tomllib.loads((ROOT / "src/reqreate/config_550.toml").read_text())
    out_dir = ROOT / cfg["output_dir"]
    pool_path = out_dir / cfg["pool_file"]
    pool = json.loads(pool_path.read_text())
    meta = json.loads((out_dir / cfg["metadata_file"]).read_text())
    paths = [ROOT / path for path in meta["inputs_sha256"]]
    area_path = next(path for path in paths if path.suffix == ".geojson")
    polygon = shape(json.loads(area_path.read_text())["geometry"])
    graph = ox.load_graphml(area_path.with_name("drive.graphml"))
    walk = ox.load_graphml(area_path.with_name("walk.graphml"))
    filter_cfg = tomllib.loads((ROOT / "src/reqreate/filters/filters.toml").read_text())
    stops = json.loads((ROOT / cfg["stops_path"]).read_text())
    walk_routes = walk.to_undirected()
    source = "Route 550 stops"
    for stop in stops:
        node = ox.nearest_nodes(walk, stop["lon"], stop["lat"])
        walk_node = walk.nodes[node]
        connector = ox.distance.great_circle(stop["lat"], stop["lon"],
                                             walk_node["y"], walk_node["x"])
        walk_routes.add_edge(source, node, length=connector)
    walk_distances = nx.single_source_dijkstra_path_length(walk_routes, source,
                                                            weight="length")
    assert hashlib.sha256(pool_path.read_bytes()).hexdigest() == meta["pool_sha256"]
    for path, digest in meta["inputs_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    reqs = pool["requests"]
    assert len(reqs) == pool["num_data:"] == meta["request_count"]
    assert meta["request_count"] <= meta["candidate_count"]
    if "poi_count" in meta:
        poi_path = out_dir / cfg["poi_cache_file"]
        pois = json.loads(poi_path.read_text())["features"]
        assert len(pois) == meta["poi_count"]
        assert "method_pois" in meta["spatial_sampling"]
    for idx, req in reqs.items():
        assert req["reqid"] == int(idx)
        for name in ("origin", "destination"):
            lat, lon = req[name]
            assert polygon.contains(Point(lon, lat))
            assert req[name + "node_drive"] in graph
            node = req[name + "node_walk"]
            assert node in walk
            walk_node = walk.nodes[node]
            connector = ox.distance.great_circle(lat, lon, walk_node["y"], walk_node["x"])
            assert walk_distances[node] + connector < filter_cfg["max_walking_distance_m"]
        assert req["direct_distance"] >= filter_cfg["parameters"][0]["value"]
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
