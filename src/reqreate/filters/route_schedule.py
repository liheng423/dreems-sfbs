"""Index scheduled Route 550 trips by ordered boarding and alighting stops."""

from collections import defaultdict


def arrival_seconds(stop_time):
    """Return a GTFS arrival time as seconds since service-day midnight."""
    hours, minutes, seconds = map(int, stop_time["arrival_time"].split(":"))
    return hours * 3600 + minutes * 60 + seconds


def index_route_departures(schedule):
    """Index sorted departure and arrival times by ordered stop pair."""
    departures = defaultdict(list)
    for pattern in schedule["patterns"]:
        for trip in pattern["trips"]:
            stop_times = trip["stop_times"]
            for index, boarding in enumerate(stop_times):
                if boarding["pickup_type"] != "0":
                    continue
                for alighting in stop_times[index + 1:]:
                    if alighting["drop_off_type"] == "0":
                        pair = boarding["stop_id"], alighting["stop_id"]
                        departures[pair].append((boarding["departure_seconds"],
                                                 arrival_seconds(alighting)))
    return {pair: sorted(times) for pair, times in departures.items()}
