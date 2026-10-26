#!/usr/bin/env python3
"""Extract one route's scheduled corridor data from a static GTFS archive.

This crawler saves the selected route's timetable and REQreate stop places.
Request generation lives in the Python modules under ``src/reqreate``.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def read_table(archive: zipfile.ZipFile, filename: str, *, optional=False) -> List[dict]:
    """Read a GTFS CSV table while preserving text fields."""
    if optional and filename not in archive.namelist():
        return []
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


def format_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def stop_event(row: dict) -> dict:
    """Preserve separate arrival and departure times when a bus dwells."""
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
        "departure_seconds": departure_seconds,
        "pickup_type": row.get("pickup_type", ""),
        "drop_off_type": row.get("drop_off_type", ""),
        "timepoint": row.get("timepoint", ""),
    }


def complete_stop_times(rows: List[dict]) -> List[dict]:
    """Interpolate untimed intermediate stops between scheduled stop times."""
    rows = [dict(row) for row in rows]
    timed = [i for i, row in enumerate(rows)
             if row.get("arrival_time") or row.get("departure_time")]
    if not timed or timed[0] != 0 or timed[-1] != len(rows) - 1:
        raise ValueError("A trip must have times at its first and last stops")
    for left, right in zip(timed, timed[1:]):
        if right == left + 1:
            continue
        start = time_seconds(rows[left].get("departure_time") or rows[left].get("arrival_time"))
        end = time_seconds(rows[right].get("arrival_time") or rows[right].get("departure_time"))
        if end < start:
            raise ValueError("Trip stop times must be ordered")
        distances = [row.get("shape_dist_traveled", "") for row in rows[left:right + 1]]
        if all(distances):
            positions = [float(value) for value in distances]
            if any(a >= b for a, b in zip(positions, positions[1:])):
                positions = list(range(right - left + 1))
        else:
            positions = list(range(right - left + 1))
        span = positions[-1] - positions[0]
        for i in range(left + 1, right):
            seconds = round(start + (end - start) * (positions[i - left] - positions[0]) / span)
            rows[i]["arrival_time"] = rows[i]["departure_time"] = format_time(seconds)
    return rows


def load_archive(path: Optional[Path], url: Optional[str]) -> tuple[bytes, str]:
    if path is not None:
        return path.read_bytes(), path.name
    if url is None:
        raise ValueError("Pass --gtfs-zip or --gtfs-url")
    request = urllib.request.Request(url, headers={"User-Agent": "dreems-busline-crawler/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read(), url.rsplit("/", 1)[-1]


def crawl(
    archive_bytes: bytes,
    archive_name: str,
    source_url: str,
    route_short_name: Optional[str],
    service_date: dt.date,
    route_id: Optional[str] = None,
    license_name: str = "",
) -> dict:
    digest = hashlib.sha256(archive_bytes).hexdigest()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        routes = read_table(archive, "routes.txt")
        matches = [
            row
            for row in routes
            if (route_short_name is None or row.get("route_short_name") == route_short_name)
            and (route_id is None or row.get("route_id") == route_id)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one route for short name {route_short_name!r} and ID {route_id!r}; "
                f"found {len(matches)}. Pass --route-id to disambiguate."
            )
        route = matches[0]

        calendar_rows = read_table(archive, "calendar.txt", optional=True)
        calendar_date_rows = read_table(archive, "calendar_dates.txt", optional=True)
        if not calendar_rows and not calendar_date_rows:
            raise ValueError("GTFS feed needs calendar.txt or calendar_dates.txt")
        agencies = read_table(archive, "agency.txt", optional=True)
        feed_info = read_table(archive, "feed_info.txt", optional=True)
        feed_info = feed_info[0] if feed_info else {}
        agency = next((row for row in agencies if row.get("agency_id") == route.get("agency_id")),
                      agencies[0] if len(agencies) == 1 else {})
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
        with archive.open("stop_times.txt") as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")):
                if row["trip_id"] in trip_ids:
                    trip_stops[row["trip_id"]].append(row)
        stop_table = {row["stop_id"]: row for row in read_table(archive, "stops.txt")}
        frequency_rows = [row for row in read_table(archive, "frequencies.txt", optional=True)
                          if row["trip_id"] in trip_ids]

    if not trips:
        raise ValueError(
            f"Route {route.get('route_short_name') or route['route_id']} has no trips active "
            f"on {service_date.isoformat()}"
        )

    frequencies = defaultdict(list)
    for row in frequency_rows:
        if row.get("exact_times", "0") != "1":
            raise ValueError("Selected route has frequency-based service without exact departures")
        frequencies[row["trip_id"]].append(row)
    grouped = defaultdict(list)
    for trip in trips:
        events = complete_stop_times(sorted(trip_stops[trip["trip_id"]],
                                            key=lambda row: int(row["stop_sequence"])))
        signature = tuple(row["stop_id"] for row in events)
        key = trip.get("direction_id", ""), signature
        if trip["trip_id"] not in frequencies:
            grouped[key].append((trip, events))
            continue
        template_start = time_seconds(events[0]["departure_time"] or events[0]["arrival_time"])
        for frequency in frequencies[trip["trip_id"]]:
            start = time_seconds(frequency["start_time"])
            end = time_seconds(frequency["end_time"])
            headway = int(frequency["headway_secs"])
            if headway <= 0 or end <= start:
                raise ValueError("Invalid frequencies.txt time range or headway")
            for departure in range(start, end, headway):
                offset = departure - template_start
                shifted = [{**event, **{
                    field: format_time(time_seconds(event[field]) + offset)
                    for field in ("arrival_time", "departure_time")
                    if event.get(field)
                }} for event in events]
                expanded_trip = {**trip, "trip_id": f"{trip['trip_id']}@{departure}"}
                grouped[key].append((expanded_trip, shifted))

    patterns = []
    used_stop_ids = set()
    for pattern_number, ((direction_id, signature), members) in enumerate(
        sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1]))
    ):
        first_name = stop_table[signature[0]]["stop_name"]
        last_name = stop_table[signature[-1]]["stop_name"]
        pattern_trips = []
        for trip, raw_events in members:
            events = [stop_event(row) for row in raw_events]
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
        ends = [trip["stop_times"][-1]["departure_seconds"] for trip in pattern_trips]
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
    feed_start = feed_info.get("feed_start_date") or min(
        [row["start_date"] for row in calendar_rows] +
        [row["date"] for row in calendar_date_rows if row["exception_type"] == "1"], default="")
    feed_end = feed_info.get("feed_end_date") or max(
        [row["end_date"] for row in calendar_rows] +
        [row["date"] for row in calendar_date_rows if row["exception_type"] == "1"], default="")
    return {
        "schema_version": 1,
        "source": {
            "producer": feed_info.get("feed_publisher_name") or agency.get("agency_name", ""),
            "dataset": "GTFS Schedule",
            "license": license_name,
            "source_url": source_url,
            "archive_name": archive_name,
            "archive_sha256": digest,
            "feed_service_range": [feed_start, feed_end],
            "agency_timezone": agency.get("agency_timezone", ""),
        },
        "service_date": service_date.isoformat(),
        "route": {
            "route_id": route["route_id"],
            "route_short_name": route.get("route_short_name", ""),
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


def build_stops(businfo, mandatory_stop_ids=()):
    """Make REQreate places; route terminals are mandatory by default."""
    mandatory_ids = set(mandatory_stop_ids)
    mandatory_ids.update(stop_id for pattern in businfo["patterns"]
                         for stop_id in pattern["terminal_stop_ids"])
    return [{
        "name": f"Stop_{stop['stop_id']}",
        "type": "location",
        "class": "mandatory" if stop["stop_id"] in mandatory_ids else "optional",
        "lon": stop["stop_lon"],
        "lat": stop["stop_lat"],
    } for stop in businfo["stops"]]


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root))
    from src.output_adapters import busline_dir, busline_path, write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", help="GTFS route_short_name")
    parser.add_argument("--route-id", help="GTFS route_id; can replace or disambiguate --route")
    parser.add_argument("--name", help="Output folder name (for example tec-12)")
    parser.add_argument("--service-date", required=True, help="GTFS service day, YYYY-MM-DD")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--gtfs-url", help="Download a GTFS Schedule ZIP")
    source.add_argument("--gtfs-zip", type=Path, help="Use a local GTFS Schedule ZIP")
    parser.add_argument("--source-url", default="", help="Original URL when using --gtfs-zip")
    parser.add_argument("--license", default="", help="Dataset license, if known")
    parser.add_argument("--mandatory-stop-id", action="append", default=[],
                        help="Mark an additional GTFS stop ID as mandatory")
    parser.add_argument("--output", type=Path, help="Override the buslines.json path")
    parser.add_argument("--stops-output", type=Path, help="Override the stops.json path")
    args = parser.parse_args()
    if not (args.route or args.route_id):
        parser.error("Pass --route or --route-id")

    service_date = dt.date.fromisoformat(args.service_date)
    archive_bytes, archive_name = load_archive(args.gtfs_zip, args.gtfs_url)
    result = crawl(
        archive_bytes,
        archive_name,
        args.gtfs_url or args.source_url,
        args.route,
        service_date,
        args.route_id,
        args.license,
    )
    route_dir = busline_dir(args.name or result["route"]["route_short_name"] or result["route"]["route_id"])
    businfo_path = args.output or busline_path("businfo", route_dir)
    stops_path = args.stops_output or (businfo_path.with_name("stops.json") if args.output
                                       else busline_path("stops", route_dir))
    stops = build_stops(result, args.mandatory_stop_id)
    if stops_path.is_file():
        previous = json.loads(stops_path.read_text())
        classes = {stop["name"]: stop["class"] for stop in previous}
        stops = [{**stop, "class": classes.get(stop["name"], stop["class"])} for stop in stops]
        names = {stop["name"] for stop in stops}
        stops.extend(stop for stop in previous if stop["name"].startswith("Stop_OSM_")
                     and stop["name"] not in names)
    write_json(businfo_path, result)
    write_json(stops_path, stops)
    print(f"Wrote {len(result['stops'])} stops and {len(result['patterns'])} patterns to {businfo_path}")
    print(f"Wrote REQreate stop places to {stops_path}")


if __name__ == "__main__":
    main()
