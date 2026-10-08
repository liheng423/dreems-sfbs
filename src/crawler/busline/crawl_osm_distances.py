#!/usr/bin/env python3
"""Retrieve directed road distances between GTFS stops using OSM-backed OSRM.

Distances follow the routing server's fastest paths, not straight lines or
necessarily the scheduled bus itinerary. The server's prepared routing profile
determines vehicle access rules; the public default uses a car profile.
"""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request


def build_mat(crawl, server, profile):
    """Fetch one all-pairs table, retaining source IDs, nulls and snap locations.

    Accept the same single-route or multi-route snapshots as the Julia generator.
    Shared physical stops are queried once. Rows are origins, columns destinations;
    reverse journeys remain independent and unreachable pairs remain null.
    """
    crawls = crawl if isinstance(crawl, list) else [crawl]
    stops = {}
    for src in crawls:
        for stop in src["stops"]:
            stops[str(stop["stop_id"])] = stop
    stop_ids = sorted(stops)
    xy = ";".join(
        f"{stops[stop_id]['stop_lon']},{stops[stop_id]['stop_lat']}"
        for stop_id in stop_ids
    )
    params = urllib.parse.urlencode({"annotations": "distance", "generate_hints": "false"})
    url = f"{server.rstrip('/')}/table/v1/{profile}/{xy}?{params}"
    # ponytail: one table request; batch source/destination blocks if the network
    # grows beyond the routing server's coordinate limit (29 stops for line 550).
    req = urllib.request.Request(url, headers={"User-Agent": "dreems-osm-distance-crawler/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        table = json.load(response)
    if table["code"] != "Ok":
        raise ValueError(f"OSRM table failed: {table}")
    return {
        "schema_version": 1,
        "stop_ids": stop_ids,
        "distances_m": table["distances"],
        "stops": [stops[stop_id] for stop_id in stop_ids],
        "snapped_sources": table["sources"],
        "snapped_destinations": table["destinations"],
        "routes": [src["route"] for src in crawls],
        "metadata": {
            "source": "OpenStreetMap contributors via OSRM",
            "attribution_url": "https://www.openstreetmap.org/copyright",
            "license": "Open Database License (ODbL)",
            "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "osm_data_version": table.get("data_version"),
            "request_url": url,
            "profile": profile,
            "distance_kind": "road distance along fastest routed path",
            "units": "metres",
            "matrix_order": "rows = origins; columns = destinations; both use stop_ids",
            "unreachable": "null",
            "euclidean_fallback": False,
            "vehicle_access": "determined by server preprocessing; public default is car, not bus",
        },
    }


def main():
    """Write a separate distance matrix beside the normalized GTFS snapshot."""
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gtfs-json", type=Path, default=root / "data/crawled_550.json")
    parser.add_argument("--output", type=Path, help="Defaults to distance_matrix_<line or network>.json")
    parser.add_argument("--osrm-url", default="https://router.project-osrm.org")
    parser.add_argument("--profile", default="driving", help="URL profile; must match the server's prepared data")
    args = parser.parse_args()
    in_bytes = args.gtfs_json.read_bytes()
    crawl = json.loads(in_bytes)
    mat = build_mat(crawl, args.osrm_url, args.profile)
    mat["metadata"]["input_sha256"] = hashlib.sha256(in_bytes).hexdigest()
    lbl = "network" if isinstance(crawl, list) else crawl["route"]["route_short_name"]
    out_path = args.output or args.gtfs_json.parent / f"distance_matrix_{lbl}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(mat['stop_ids'])} × {len(mat['stop_ids'])} road distances to {out_path}")


if __name__ == "__main__":
    main()
