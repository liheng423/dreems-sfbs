#!/usr/bin/env python3
"""Capture Route 550 real-time departure estimates from the ATP HAFAS API.

The ATP API exposes live departure boards, not a historical archive. This
script records only departures for which HAFAS returns ``rtTime`` and matches
each record to the selected day's static GTFS trip. The resulting JSON Lines
file is input for ``src/reqreate-gen/travel_time_matrix.jl``.

Set ``ATP_API_KEY`` to the personal key issued by ATP before running. The key
is sent to the API and is never written to the output file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


API_ROOT = "https://cdt.hafas.de/opendata/apiserver"
LOCAL_TIME = ZoneInfo("Europe/Luxembourg")
USER_AGENT = "bus550-realtime-crawler/1.0"


def api_json(endpoint: str, params: dict[str, str]) -> dict:
    """Fetch one ATP JSON endpoint using the user's API key."""
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{API_ROOT}/{endpoint}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def as_entries(container: dict, key: str) -> list[dict]:
    """Read a repeated HAFAS JSON element whether it has one or many items."""
    entries = container.get(key, [])
    return entries if isinstance(entries, list) else [entries]


def hafas_stops(crawled: dict, api_key: str) -> dict[str, str]:
    """Map GTFS source stop IDs to the nearest ATP HAFAS stop IDs."""
    result = {}
    for stop in crawled["stops"]:
        nearby = api_json(
            "location.nearbystops",
            {
                "accessId": api_key,
                "originCoordLat": str(stop["stop_lat"]),
                "originCoordLong": str(stop["stop_lon"]),
                "maxNo": "10",
                "r": "200",
                "type": "SE",
                "format": "json",
            },
        )
        locations = nearby.get("LocationList", nearby)
        choices = as_entries(locations, "StopLocation")
        nearest = min(
            choices,
            key=lambda item: math.hypot(
                float(item["lat"]) - float(stop["stop_lat"]),
                float(item["lon"]) - float(stop["stop_lon"]),
            ),
        )
        result[str(stop["stop_id"])] = str(nearest.get("id") or nearest["extId"])
    return result


def service_seconds(date_text: str, time_text: str, service_date: dt.date) -> int:
    """Convert an ATP local date and time to seconds from GTFS service-day start."""
    event_date = dt.date.fromisoformat(date_text)
    event_time = dt.time.fromisoformat(time_text)
    event = dt.datetime.combine(event_date, event_time)
    midnight = dt.datetime.combine(service_date, dt.time())
    return int((event - midnight).total_seconds())


def route_line(departure: dict) -> str:
    product = departure.get("Product", {})
    return str(product.get("line") or product.get("name") or departure.get("name") or "").strip()


def is_route_550(departure: dict) -> bool:
    line = route_line(departure).lower()
    return line == "550" or line == "bus 550"


def scheduled_events(crawled: dict) -> dict[str, list[dict]]:
    """Index active GTFS stop departures for matching to ATP board entries."""
    by_stop = defaultdict(list)
    for pattern in crawled["patterns"]:
        for trip in pattern["trips"]:
            for event in trip["stop_times"]:
                by_stop[str(event["stop_id"])].append(
                    {
                        "pattern_id": str(pattern["pattern_id"]),
                        "direction_id": str(pattern["direction_id"]),
                        "trip_id": str(trip["trip_id"]),
                        "trip_headsign": str(trip["trip_headsign"]),
                        "stop_sequence": int(event["stop_sequence"]),
                        "scheduled_departure_seconds": int(event["departure_seconds"]),
                    }
                )
    return by_stop


def matching_event(
    departure: dict,
    stop_id: str,
    events_by_stop: dict[str, list[dict]],
    service_date: dt.date,
) -> Optional[dict]:
    """Match an ATP scheduled departure to the closest active GTFS stop event."""
    if not is_route_550(departure):
        return None
    planned_seconds = service_seconds(
        str(departure["date"]), str(departure["time"]), service_date
    )
    candidates = events_by_stop[stop_id]
    match = min(
        candidates,
        key=lambda event: abs(event["scheduled_departure_seconds"] - planned_seconds),
    )
    if abs(match["scheduled_departure_seconds"] - planned_seconds) > 600:
        return None
    return match


def realtime_record(
    departure: dict,
    stop: dict,
    hafas_stop_id: str,
    event: dict,
    observed_at: dt.datetime,
    service_date: dt.date,
) -> Optional[dict]:
    """Normalize one HAFAS departure with an available real-time estimate."""
    if str(departure.get("cancelled", "false")).lower() == "true" or not departure.get("rtTime"):
        return None
    hafas_scheduled_seconds = service_seconds(
        str(departure["date"]), str(departure["time"]), service_date
    )
    realtime_seconds = service_seconds(
        str(departure.get("rtDate") or departure["date"]),
        str(departure["rtTime"]),
        service_date,
    )
    midnight = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
    observed_service_seconds = int((observed_at.replace(tzinfo=None) - midnight.replace(tzinfo=None)).total_seconds())
    return {
        "schema_version": 1,
        "source": "ATP mobiliteit.lu HAFAS departureBoard",
        "time_kind": "HAFAS real-time departure estimate",
        "route_short_name": "550",
        "service_date": service_date.isoformat(),
        "observed_at_utc": observed_at.astimezone(dt.timezone.utc).isoformat(),
        "observed_at_service_seconds": observed_service_seconds,
        "pattern_id": event["pattern_id"],
        "direction_id": event["direction_id"],
        "trip_id": event["trip_id"],
        "trip_headsign": event["trip_headsign"],
        "stop_id": str(stop["stop_id"]),
        "stop_name": str(stop["stop_name"]),
        "stop_sequence": event["stop_sequence"],
        "hafas_stop_id": hafas_stop_id,
        "scheduled_departure_seconds": event["scheduled_departure_seconds"],
        "hafas_scheduled_departure_seconds": hafas_scheduled_seconds,
        "realtime_departure_seconds": realtime_seconds,
        "delay_seconds": realtime_seconds - event["scheduled_departure_seconds"],
        "hafas_direction": str(departure.get("direction", "")),
        "journey_reference": str(departure.get("JourneyDetailRef", {}).get("ref", "")),
    }


def capture(args: argparse.Namespace) -> None:
    crawled = json.loads(args.gtfs_json.read_text(encoding="utf-8"))
    service_date = dt.date.fromisoformat(crawled["service_date"])
    today = dt.datetime.now(LOCAL_TIME).date()
    if service_date != today:
        raise ValueError(
            f"GTFS service date is {service_date}; live capture requires today's "
            f"Luxembourg service date ({today}). Re-crawl the static GTFS for today first."
        )

    api_key = args.api_key or os.environ.get("ATP_API_KEY")
    if not api_key:
        raise ValueError("Set ATP_API_KEY or pass --api-key (request a personal key from ATP).")

    output_path = args.output or (
        args.gtfs_json.parent / f"realtime_550_{service_date.isoformat()}.jsonl"
    )
    stops_by_id = {str(stop["stop_id"]): stop for stop in crawled["stops"]}
    hafas_ids = hafas_stops(crawled, api_key)
    events_by_stop = scheduled_events(crawled)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cycle = 0
    with output_path.open("a", encoding="utf-8") as output:
        while args.cycles is None or cycle < args.cycles:
            cycle_started = time.monotonic()
            for stop_id, hafas_stop_id in hafas_ids.items():
                board = api_json(
                    "departureBoard",
                    {
                        "accessId": api_key,
                        "lang": "en",
                        "id": hafas_stop_id,
                        "format": "json",
                    },
                )
                board = board.get("DepartureBoard", board)
                departures = as_entries(board, "Departure")
                observed_at = dt.datetime.now(LOCAL_TIME)
                for departure in departures:
                    event = matching_event(departure, stop_id, events_by_stop, service_date)
                    if event is None:
                        continue
                    row = realtime_record(
                        departure,
                        stops_by_id[stop_id],
                        hafas_stop_id,
                        event,
                        observed_at,
                        service_date,
                    )
                    if row is not None:
                        output.write(json.dumps(row, ensure_ascii=False) + "\n")
                        output.flush()
            cycle += 1
            print(f"Completed capture cycle {cycle}; wrote observations to {output_path}", flush=True)
            delay = args.poll_seconds - (time.monotonic() - cycle_started)
            if delay > 0 and (args.cycles is None or cycle < args.cycles):
                time.sleep(delay)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gtfs-json",
        type=Path,
        default=root / "data" / "crawled_550.json",
        help="Normalized GTFS snapshot for today's service date",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Append-only JSON Lines output (defaults to realtime_550_<service-date>.jsonl beside the GTFS JSON)",
    )
    parser.add_argument("--api-key", help="ATP personal key; ATP_API_KEY is preferred")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--cycles", type=int, help="Stop after this many full route sweeps")
    args = parser.parse_args()
    if args.poll_seconds < 1:
        parser.error("--poll-seconds must be positive")
    if args.cycles is not None and args.cycles < 1:
        parser.error("--cycles must be positive")
    capture(args)


if __name__ == "__main__":
    main()
