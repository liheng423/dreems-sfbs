"""Check that OSM POIs guide REQreate's zone-density request sampler."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys

import osmnx as ox
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/reqreate"))
from src.reqreate import generate
from src.output_adapters import graph_dir, graph_path, write_json
from utils.walking_distance import WalkingDistance


def check_meter_grid():
    net = SimpleNamespace(polygon=box(6.0, 49.5, 6.1, 49.6))
    generate.set_poi_zones(net, [[49.55, 6.05], [49.55, 6.051], [49.55, 6.06]], 500)
    assert sorted(net.zones["number_pois"]) == [1, 2]
    assert abs(net.zones["density_pois"].sum() - 1) < 1e-12
    for zone in net.zones["polygon"]:
        projected, _ = ox.projection.project_geometry(zone)
        min_x, min_y, max_x, max_y = projected.bounds
        assert abs(max_x - min_x - 500) < 1
        assert abs(max_y - min_y - 500) < 1


def main():
    check_meter_grid()
    cfg = generate.load_config("SFBS", "550")
    cfg["distributions"]["dynamic_order_place_time"]["rate_per_hour"] = 0.625
    cfg["distributions"]["prebooked_earliest_departure"]["rate_per_hour"] = 0.625
    area_path = graph_path("area", graph_dir("550"))
    with TemporaryDirectory() as directory:
        poi_path = graph_path("pois", Path(directory))
        net = generate.build_area_net(area_path, cfg["places"], cfg["max_walking_distance_m"])
        write_json(poi_path, {"features": [
            {"lat": point.y, "lon": point.x, "name": name, "tags": tags}
            for seed, name, tags in ((1, "School", {"amenity": "school"}),
                                     (2, "Cafe", {"amenity": "cafe"}),
                                     (3, "Museum", {"tourism": "museum"}))
            for point in [net._get_random_coord(net.polygon, seed)]
        ]})
        with patch.object(
            generate, "_generate_single_data_impl", wraps=generate._generate_single_data_impl
        ) as sample:
            pois = generate.load_pois(poi_path)
            pool = generate.generate(cfg, area_path, poi_path)
        assert len(pois) == 3
        generate.set_poi_zones(net, pois, cfg["method_pois"]["cell_size_m"])
        assert net.zones["number_pois"].sum() == len(pois)
        assert abs(net.zones["density_pois"].sum() - 1) < 1e-12
        assert len(pool["requests"]) <= cfg["generated_candidate_count"]
        assert all(call.args[5] is True for call in sample.call_args_list)
        snapshot = json.loads(poi_path.read_text(encoding="utf-8"))
        assert [poi["name"] for poi in snapshot["features"]] == ["School", "Cafe", "Museum"]
        assert snapshot["features"][0]["tags"] == {"amenity": "school"}
        with patch.object(WalkingDistance, "within_limit", return_value=False) as walkable:
            rejected = generate.generate(cfg, area_path, poi_path)
        assert rejected == {"num_data:": 0, "requests": {}}
        assert 0 < walkable.call_count <= cfg["generated_candidate_count"]
    print("Validated saved-map POIs and REQreate zone-density sampling")


if __name__ == "__main__":
    main()
