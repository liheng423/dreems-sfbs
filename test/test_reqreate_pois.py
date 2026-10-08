"""Check that OSM POIs guide REQreate's zone-density request sampler."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/reqreate"))
from src.reqreate import generate
import pois as poi_module
from utils.walking_distance import WalkingDistance


def main():
    cfg = generate.load_config()
    cfg["requests"] = 5
    area_path = generate.ROOT / cfg["service_area_path"]
    with TemporaryDirectory() as directory:
        poi_path = Path(directory) / cfg["poi_cache_file"]
        net = generate.build_area_net(area_path, cfg["places"], cfg["max_walking_distance_m"])
        features = pd.DataFrame({
            "geometry": [net._get_random_coord(net.polygon, seed) for seed in (1, 2, 3)],
            "name": ["School", "Cafe", "Museum"],
            "amenity": ["school", "cafe", None],
            "tourism": [None, None, "museum"],
        }, index=pd.MultiIndex.from_tuples([("node", 1), ("node", 2), ("way", 3)]))
        with patch.object(poi_module, "configure_overpass"), patch.object(
            poi_module.ox, "features_from_polygon", return_value=features
        ) as fetch, patch.object(
            generate, "_generate_single_data_impl", wraps=generate._generate_single_data_impl
        ) as sample:
            pois = generate.load_pois(cfg, net, area_path, poi_path)
            pool = generate.generate(cfg, area_path, poi_path)
        assert fetch.call_count == 1
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
    print("Validated POI retrieval, caching, and REQreate zone-density sampling")


if __name__ == "__main__":
    main()
