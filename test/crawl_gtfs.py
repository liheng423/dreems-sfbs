"""Run with: python3 test/crawl_gtfs.py"""

import runpy
from pathlib import Path


stop_event = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "src/crawler/python/crawl_gtfs.py")
)["stop_event"]
row = {
    "stop_id": "S",
    "stop_sequence": "0",
    "arrival_time": "04:45:00",
    "departure_time": "04:45:00",
}
assert stop_event(row)["departure_seconds"] == 17100
assert "arrival_seconds" not in stop_event(row)

row["departure_time"] = "04:46:00"
try:
    stop_event(row)
except ValueError:
    pass
else:
    raise AssertionError("A nonzero dwell time was silently discarded")

print("GTFS stop normalization passed.")
