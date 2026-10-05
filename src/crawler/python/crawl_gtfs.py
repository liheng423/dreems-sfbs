#!/usr/bin/env python3
"""Extract one route's scheduled corridor data from a static GTFS archive.

This crawler deliberately stops at source data: it does not classify stops,
generate passenger requests, or create optimization instances. Those steps are
implemented in Julia under ``src/reqreate-gen`` and use shared helpers from
``src/tools``.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional


DEFAULT_GTFS_URL = (
    "https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/"
    "20261001-055928/gtfs-20260930-20261212.zip"
)
DEFAULT_SERVICE_DATE = "2026-10-06"
LICENSE = "Creative Commons Attribution 4.0"


def read_table(archive: zipfile.ZipFile, filename: str) -> List[dict]:
    """Read a required GTFS CSV table while preserving text fields."""
    text = archive.read(filename).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def active_services(
    calendar: Iterable[dict], calendar_dates: Iterable[dict], service_date: dt.date
) -> set[str]:
    """Return services active on the requested date, including exceptions."""
    date_text = service_date.strftime("%Y%m%d")
    weekday = service_date.strftime("%A").lower()
    active = {
        row["service_id"]
        for row in calendar
        if row["start_date"] <= date_text <= row["end_date"] and row[weekday] == "1"
    }
    for row in calendar_dates:
        if row["date"] == date_text:
            if row["exception_type"] == "1":
                active.add(row["service_id"])
            elif row["exception_type"] == "2":
                active.discard(row["service_id"])
    return active


def time_seconds(value: str) -> Optional[int]:
    """Convert a GTFS time to seconds after the service-day start.

    GTFS permits hours greater than 23 for trips continuing past midnight;
    preserving the full hour count keeps those times ordered correctly.
    """
    if not value:
        return None
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def stop_event(row: dict) -> dict:
    arrival = row.get("arrival_time", "")
    departure = row.get("departure_time", "")
    arrival_seconds = time_seconds(arrival)
    departure_seconds = time_seconds(departure)
    if arrival_seconds is None:
        arrival_seconds = departure_seconds
    if departure_seconds is None:
        departure_seconds = arrival_seconds
    return {
        "stop_sequence": int(row["stop_sequence"]),
        "stop_id": row["stop_id"],
        "arrival_time": arrival or departure,
        "departure_time": departure or arrival,
        "arrival_seconds": arrival_seconds,
        "departure_seconds": departure_seconds,
        "pickup_type": row.get("pickup_type", ""),
        "drop_off_type": row.get("drop_off_type", ""),
        "timepoint": row.get("timepoint", ""),
    }


def load_archive(path: Optional[Path], url: str) -> tuple[bytes, str]:
    if path:
        return path.read_bytes(), path.name
    request = urllib.request.Request(url, headers={"User-Agent": "bus550-corridor-crawler/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read(), url.rsplit("/", 1)[-1]


def crawl(
    archive_bytes: bytes,
    archive_name: str,
    source_url: str,
    route_short_name: str,
    service_date: dt.date,
    route_id: Optional[str] = None,
) -> dict:
    digest = hashlib.sha256(archive_bytes).hexdigest()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        routes = read_table(archive, "routes.txt")
        matches = [
            row
            for row in routes
            if row.get("route_short_name") == route_short_name
            and (route_id is None or row.get("route_id") == route_id)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one route for short name {route_short_name!r}; found {len(matches)}. "
                "Pass --route-id when the feed has multiple matching route IDs."
            )
        route = matches[0]

        calendar_rows = read_table(archive, "calendar.txt")
        calendar_date_rows = read_table(archive, "calendar_dates.txt")
        services = active_services(calendar_rows, calendar_date_rows, service_date)
        route_trips = [
            row
            for row in read_table(archive, "trips.txt")
            if row["route_id"] == route["route_id"]
        ]
        route_service_ids = {row["service_id"] for row in route_trips}
        trips = [row for row in route_trips if row["service_id"] in services]
        trip_ids = {row["trip_id"] for row in trips}
        trip_stops: Dict[str, List[dict]] = defaultdict(list)
        for row in read_table(archive, "stop_times.txt"):
            if row["trip_id"] in trip_ids:
                trip_stops[row["trip_id"]].append(row)
        stop_table = {row["stop_id"]: row for row in read_table(archive, "stops.txt")}

    if not trips:
        raise ValueError(
            f"Route {route_short_name} has no trips active on {service_date.isoformat()}"
        )

    grouped = defaultdict(list)
    for trip in trips:
        events = sorted(trip_stops[trip["trip_id"]], key=lambda row: int(row["stop_sequence"]))
        signature = tuple(row["stop_id"] for row in events)
        grouped[(trip.get("direction_id", ""), signature)].append((trip, events))

    patterns = []
    used_stop_ids = set()
    for pattern_number, ((direction_id, signature), members) in enumerate(
        sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1]))
    ):
        first_name = stop_table[signature[0]]["stop_name"]
        last_name = stop_table[signature[-1]]["stop_name"]
        pattern_trips = []
        for trip, raw_events in members:
            events = [stop_event(row) for row in sorted(raw_events, key=lambda row: int(row["stop_sequence"]))]
            used_stop_ids.update(event["stop_id"] for event in events)
            pattern_trips.append(
                {
                    "trip_id": trip["trip_id"],
                    "service_id": trip["service_id"],
                    "direction_id": direction_id,
                    "trip_headsign": trip.get("trip_headsign", ""),
                    "shape_id": trip.get("shape_id", ""),
                    "stop_times": events,
                }
            )
        pattern_trips.sort(
            key=lambda trip: (
                trip["stop_times"][0]["departure_seconds"],
                trip["trip_id"],
            )
        )
        starts = [trip["stop_times"][0]["departure_seconds"] for trip in pattern_trips]
        ends = [trip["stop_times"][-1]["arrival_seconds"] for trip in pattern_trips]
        patterns.append(
            {
                "pattern_id": f"{direction_id or 'unspecified'}-{pattern_number:02d}",
                "direction_id": direction_id,
                "label": f"{first_name} -> {last_name}",
                "stop_ids": list(signature),
                "terminal_stop_ids": [signature[0], signature[-1]],
                "service_period": {
                    "first_departure_seconds": min(starts),
                    "last_arrival_seconds": max(ends),
                },
                "trips": pattern_trips,
            }
        )

    all_stops = []
    for stop_id in sorted(used_stop_ids):
        row = stop_table[stop_id]
        all_stops.append(
            {
                "stop_id": stop_id,
                "stop_name": row["stop_name"],
                "stop_lat": float(row["stop_lat"]),
                "stop_lon": float(row["stop_lon"]),
                "parent_station": row.get("parent_station", ""),
                "location_type": row.get("location_type", ""),
                "wheelchair_boarding": row.get("wheelchair_boarding", ""),
            }
        )

    starts = [pattern["service_period"]["first_departure_seconds"] for pattern in patterns]
    ends = [pattern["service_period"]["last_arrival_seconds"] for pattern in patterns]
    feed_start = min((row["start_date"] for row in calendar_rows), default="")
    feed_end = max((row["end_date"] for row in calendar_rows), default="")
    return {
        "schema_version": 1,
        "source": {
            "producer": "Administration des transports publics, Luxembourg",
            "dataset": "Horaires et arrêts des transport publics (GTFS)",
            "license": LICENSE,
            "source_url": source_url,
            "archive_name": archive_name,
            "archive_sha256": digest,
            "feed_service_range": [feed_start, feed_end],
        },
        "service_date": service_date.isoformat(),
        "route": {
            "route_id": route["route_id"],
            "route_short_name": route_short_name,
            "route_long_name": route.get("route_long_name", ""),
            "route_type": route.get("route_type", ""),
        },
        "operating_hours": {
            "start_seconds": min(starts),
            "end_seconds": max(ends),
            "start_minute": min(starts) // 60,
            "end_minute": (max(ends) + 59) // 60,
        },
        "active_service_ids": sorted({trip["service_id"] for trip in trips}),
        "service_calendar": {
            "selected_date": service_date.isoformat(),
            "active_service_ids": sorted(services.intersection(route_service_ids)),
            "weekly_rules": [
                row for row in calendar_rows if row["service_id"] in route_service_ids
            ],
            "date_exceptions": [
                row
                for row in calendar_date_rows
                if row["service_id"] in route_service_ids
            ],
        },
        "stops": all_stops,
        "patterns": patterns,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-short-name", default="550")
    parser.add_argument("--route-id")
    parser.add_argument("--service-date", default=DEFAULT_SERVICE_DATE)
    parser.add_argument("--gtfs-url", default=DEFAULT_GTFS_URL)
    parser.add_argument("--gtfs-zip", type=Path, help="Use a previously downloaded GTFS ZIP")
    parser.add_argument("--output", type=Path, default=root / "data" / "crawled_550.json")
    args = parser.parse_args()

    service_date = dt.date.fromisoformat(args.service_date)
    archive_bytes, archive_name = load_archive(args.gtfs_zip, args.gtfs_url)
    result = crawl(
        archive_bytes,
        archive_name,
        args.gtfs_url,
        args.route_short_name,
        service_date,
        args.route_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(result['stops'])} stops and {len(result['patterns'])} patterns to {args.output}")


if __name__ == "__main__":
    main()
