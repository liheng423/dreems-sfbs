"""Offline contract check: python3 test/crawl_osm_distances.py."""

import io
import json
from pathlib import Path
import runpy
from unittest.mock import patch


build_mat = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "src/crawler/busline/crawl_osm_distances.py"
))["build_mat"]
stops = [
    {"stop_id": "002", "stop_lon": 6.2, "stop_lat": 49.2},
    {"stop_id": "001", "stop_lon": 6.1, "stop_lat": 49.1},
]
crawl = {"stops": stops, "route": {"route_short_name": "550"}}
table = {
    "code": "Ok", "distances": [[0, 1234.5], [None, 0]],
    "sources": [{"location": [6.1, 49.1]}, {"location": [6.2, 49.2]}],
    "destinations": [{"location": [6.1, 49.1]}, {"location": [6.2, 49.2]}],
    "data_version": "2026-10-01T00:00:00Z",
}
with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(table).encode())) as fetch:
    mat = build_mat([crawl, crawl], "https://routing.example/", "driving")
assert mat["stop_ids"] == ["001", "002"]  # Deduplicated, stable IDs with leading zeros.
assert mat["distances_m"] == [[0, 1234.5], [None, 0]]  # No rounding, mirroring or fallback.
assert mat["snapped_sources"] == table["sources"]
assert mat["metadata"]["osm_data_version"] == table["data_version"]
assert fetch.call_args.args[0].full_url == (
    "https://routing.example/table/v1/driving/6.1,49.1;6.2,49.2"
    "?annotations=distance&generate_hints=false"
)
with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"code":"NoTable"}')):
    try:
        build_mat(crawl, "https://routing.example", "driving")
    except ValueError:
        pass
    else:
        raise AssertionError("An OSRM error was accepted as a distance matrix")
print("OSM distance matrix contract passed.")
