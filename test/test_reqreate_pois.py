"""Check that OSM POIs guide REQreate's zone-density request sampler."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/reqreate"))
from src.reqreate import generate
from src.output_adapters import graph_dir, graph_path, write_json
from utils.walking_distance import WalkingDistance


def main():
    cfg = generate.load_config("550")
    cfg["requests"] = 5
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
        generate.set_poi_zones(net, pois, cfg["method_pois"]["rows"],
                               cfg["method_pois"]["columns"])
        assert net.zones["number_pois"].sum() == len(pois)
        assert abs(net.zones["density_pois"].sum() - 1) < 1e-12
        assert len(pool["requests"]) <= cfg["requests"]
        assert all(call.args[5] is True for call in sample.call_args_list)
        snapshot = json.loads(poi_path.read_text())
        assert [poi["name"] for poi in snapshot["features"]] == ["School", "Cafe", "Museum"]
        assert snapshot["features"][0]["tags"] == {"amenity": "school"}
        with patch.object(WalkingDistance, "within_limit", return_value=False) as walkable:
            rejected = generate.generate(cfg, area_path, poi_path)
        assert rejected == {"num_data:": 0, "requests": {}}
        assert walkable.call_count == cfg["requests"]
    print("Validated saved-map POIs and REQreate zone-density sampling")


if __name__ == "__main__":
    main()
