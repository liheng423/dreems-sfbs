#!/usr/bin/env python3
"""Edit route stops, parking, and charging sites on a saved drive graph."""

import argparse
import csv
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sys
from threading import Lock
import traceback
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.output_adapters import busline_dir, busline_path, graph_dir, graph_path, write_json

PAGE_PATH = Path(__file__).with_suffix(".html")
ROUTE_ASSETS = ROOT / "shared"
LOCATION_TYPES = {
    "parking_locations": "parking",
    "fixed_charging_stations": "charging",
}
LEGACY_LOCATION_FILES = {kind: f"{kind}.csv" for kind in LOCATION_TYPES}
LOG_FILE = "select_locations.jsonl"
LOG_LOCK = Lock()
LOG_ACTIONS = {"edit_stop_field", "edit_gtfs_field", "change_stop_class",
               "remove_bus_stop", "insert_bus_stop", "change_location", "edit_sequence",
               "select_mode", "select_pattern", "save_attempt"}


def append_log(directory, route_directory, event):
    """Append one timestamped selector action to the map's audit log."""
    record = {**event, "at": datetime.now(timezone.utc).isoformat(), "map": directory.name,
              "busline": route_directory.name if route_directory else None}
    with LOG_LOCK, (directory / LOG_FILE).open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def drive_nodes(directory):
    """Read the existing driving graph's candidate nodes by OSM ID."""
    path = graph_path("drive_nodes", directory)
    if not path.is_file():
        raise FileNotFoundError(f"No saved driving graph nodes: {path}")
    with path.open(newline="", encoding="utf-8") as file:
        return {row["osmid"]: (row["x"], row["y"]) for row in csv.DictReader(file)}


def read_locations(directory):
    """Load previous selections, if any."""
    locations = {kind: [] for kind in LOCATION_TYPES}
    path = directory / "locations.csv"
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                for kind, label in LOCATION_TYPES.items():
                    if row["type"] == label:
                        locations[kind].append(row["osmid"])
        return locations
    for kind, filename in LEGACY_LOCATION_FILES.items():
        path = directory / filename
        if path.is_file():
            with path.open(newline="", encoding="utf-8") as file:
                locations[kind] = [row["osmid"] for row in csv.DictReader(file)]
    return locations


def location_data(directory, route_directory=None):
    """Return graph nodes, route stops, and selections still on this graph."""
    nodes = drive_nodes(directory)
    stops = (json.loads(busline_path("stops", route_directory).read_text())
             if route_directory else [])
    if route_directory:
        timetable = json.loads(busline_path("businfo", route_directory).read_text())
        source_stops = {f"Stop_{stop['stop_id']}": stop for stop in timetable["stops"]}
        for stop in stops:
            stop["original_name"] = stop["name"]
            stop["gtfs"] = source_stops.get(stop["name"])
            stop["label"] = (stop["gtfs"] or {}).get("stop_name", stop["name"])
            node_id = stop["name"].removeprefix("Stop_OSM_")
            if not stop["gtfs"] and stop["name"].startswith("Stop_OSM_") and node_id in nodes:
                x, y = nodes[node_id]
                stop.update(lon=float(x), lat=float(y))
    # Carry forward choices made before bus stops were saved in stops.json.
    legacy = directory / "optional_bus_stops.csv"
    if route_directory and legacy.is_file():
        existing = {stop["name"] for stop in stops}
        for node_id in read_legacy_stops(legacy):
            if node_id in nodes and f"Stop_OSM_{node_id}" not in existing:
                x, y = nodes[node_id]
                stops.append({"name": f"Stop_OSM_{node_id}", "type": "location",
                              "class": "optional", "lon": float(x), "lat": float(y),
                              "original_name": f"Stop_OSM_{node_id}", "gtfs": None})
                existing.add(f"Stop_OSM_{node_id}")
    return {
        "nodes": [[node_id, y, x] for node_id, (x, y) in nodes.items()],
        "locations": {kind: [node_id for node_id in selected if node_id in nodes]
                      for kind, selected in read_locations(directory).items()},
        "stops": stops,
        "patterns": [{"pattern_id": pattern["pattern_id"], "label": pattern["label"],
                      "stop_ids": pattern.get("selected_stop_ids", pattern["stop_ids"])}
                     for pattern in timetable.get("patterns", [])] if route_directory else [],
        "has_busline": route_directory is not None,
    }


def read_legacy_stops(path):
    with path.open(newline="", encoding="utf-8") as file:
        return [row["osmid"] for row in csv.DictReader(file)]


def edited_route(route_directory, edited_stops, edited_patterns, nodes):
    """Validate editable stop records and separate route order from GTFS times."""
    existing = json.loads(busline_path("stops", route_directory).read_text())
    businfo = json.loads(busline_path("businfo", route_directory).read_text())
    if not isinstance(edited_stops, list) or not all(isinstance(stop, dict) for stop in edited_stops):
        raise ValueError("Stops must be a list of records")
    old_stops = {stop["name"]: stop for stop in existing}
    originals = [stop.get("original_name") for stop in edited_stops]
    scheduled_names = {f"Stop_{stop['stop_id']}" for stop in businfo["stops"]}
    if len(originals) != len(set(originals)) or not scheduled_names <= set(originals):
        raise ValueError("Scheduled stops must appear exactly once")
    names = [stop.get("name") for stop in edited_stops]
    if (any(not isinstance(name, str) or not name.startswith("Stop_") or len(name) <= 5
            for name in names) or len(names) != len(set(names))):
        raise ValueError("Stop names must be unique and begin with Stop_")
    cleaned = []
    by_original = {}
    for stop in edited_stops:
        old = stop["original_name"]
        if old not in old_stops and not (isinstance(old, str) and old.startswith("Stop_OSM_")
                                         and old not in scheduled_names
                                         and old.removeprefix("Stop_OSM_") in nodes):
            raise ValueError(f"Unknown stop: {old}")
        if stop["name"] != old:
            raise ValueError("Stop IDs cannot be changed")
        if stop.get("type") != "location" or stop.get("class") not in ("mandatory", "optional"):
            raise ValueError("Stops need location type and mandatory or optional class")
        node_id = old.removeprefix("Stop_OSM_")
        expected = ({"lon": float(nodes[node_id][0]), "lat": float(nodes[node_id][1])}
                    if old.startswith("Stop_OSM_") and old not in scheduled_names
                    and node_id in nodes else old_stops[old])
        for field, limit in (("lon", 180), ("lat", 90)):
            value = stop.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
                raise ValueError(f"Invalid stop {field}")
            if value != expected[field]:
                raise ValueError(f"Stop {field} cannot be changed")
        cleaned.append({key: value for key, value in stop.items()
                        if key not in ("original_name", "label", "gtfs")})
        by_original[old] = stop
    for source in businfo["stops"]:
        edited = by_original[f"Stop_{source['stop_id']}"]
        gtfs = edited.get("gtfs")
        if not isinstance(gtfs, dict) or set(gtfs) != set(source):
            raise ValueError("Every GTFS stop field is required")
        if any(gtfs[field] != source[field] for field in ("stop_id", "stop_lat", "stop_lon")):
            raise ValueError("GTFS ID and coordinates cannot be changed")
        source.update(gtfs)
    if edited_patterns is not None:
        if not isinstance(edited_patterns, list) or len(edited_patterns) != len(businfo.get("patterns", [])):
            raise ValueError("Provide one sequence per bus pattern")
        valid_ids = {stop["name"].removeprefix("Stop_") for stop in cleaned}
        for pattern, edited in zip(businfo["patterns"], edited_patterns):
            ids = (edited.get("stop_ids") if isinstance(edited, dict)
                   and edited.get("pattern_id") == pattern["pattern_id"] else None)
            if (not isinstance(ids, list) or len(ids) < 2 or
                    any(not isinstance(stop_id, str) or stop_id not in valid_ids for stop_id in ids)):
                raise ValueError("Each bus sequence needs at least two selected stops")
            pattern["selected_stop_ids"] = ids
    return cleaned, businfo


def save_locations(directory, locations, route_directory=None, stop_classes=None, *,
                   stops_data=None, patterns_data=None):
    """Validate selections, then save graph locations and route stop classes."""
    nodes = drive_nodes(directory)
    if not isinstance(locations, dict) or set(locations) != set(LOCATION_TYPES):
        raise ValueError("Provide both graph location lists")
    for kind, ids in locations.items():
        if not isinstance(ids, list) or any(not isinstance(node_id, str) or node_id not in nodes
                                             for node_id in ids):
            raise ValueError(f"{kind} must contain saved driving graph node IDs")
    if route_directory is not None:
        if stops_data is not None:
            stops, businfo = edited_route(route_directory, stops_data, patterns_data, nodes)
            stops_path = busline_path("stops", route_directory)
        else:
            if not isinstance(stop_classes, dict) or any(
                not isinstance(name, str) or kind not in ("mandatory", "optional")
                for name, kind in stop_classes.items()
            ):
                raise ValueError("Stop classes must map stop names to mandatory or optional")
            stops_path = busline_path("stops", route_directory)
            existing = json.loads(stops_path.read_text())
            existing_names = {stop["name"] for stop in existing}
            for name in stop_classes:
                if name not in existing_names and not (
                    name.startswith("Stop_OSM_") and name.removeprefix("Stop_OSM_") in nodes
                ):
                    raise ValueError(f"Unknown stop: {name}")
            stops = []
            for stop in existing:
                name = stop["name"]
                if name.startswith("Stop_OSM_") and name not in stop_classes:
                    continue
                stop = {**stop, "class": stop_classes.get(name, stop["class"])}
                node_id = name.removeprefix("Stop_OSM_")
                if name.startswith("Stop_OSM_") and node_id in nodes:
                    x, y = nodes[node_id]
                    stop.update(lon=float(x), lat=float(y))
                stops.append(stop)
            for name, kind in stop_classes.items():
                if name not in existing_names:
                    x, y = nodes[name.removeprefix("Stop_OSM_")]
                    stops.append({"name": name, "type": "location", "class": kind,
                                  "lon": float(x), "lat": float(y)})
    with (directory / "locations.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("type", "osmid", "x", "y"))
        for kind, label in LOCATION_TYPES.items():
            for node_id in dict.fromkeys(locations[kind]):
                writer.writerow((label, node_id, *nodes[node_id]))
    for filename in LEGACY_LOCATION_FILES.values():
        (directory / filename).unlink(missing_ok=True)
    if route_directory is not None:
        write_json(stops_path, stops)
        if stops_data is not None:
            write_json(busline_path("businfo", route_directory), businfo)
        (directory / "optional_bus_stops.csv").unlink(missing_ok=True)
    append_log(directory, route_directory, {"action": "save", "locations": locations,
                                          **({"stops": stops} if route_directory else {}),
                                          **({"patterns": patterns_data} if patterns_data is not None else {})})


class Handler(BaseHTTPRequestHandler):
    """Serve only the location selector and its saved graph data."""

    map_name = ""
    busline_name = ""

    def route_directory(self):
        return busline_dir(self.busline_name) if self.busline_name else None

    def respond(self, status, body, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path == "/":
            self.respond(200, PAGE_PATH.read_text().replace("__MAP__", escape(self.map_name)),
                         "text/html; charset=utf-8")
        elif self.path == "/data":
            try:
                self.respond(200, json.dumps(location_data(
                    graph_dir(self.map_name), self.route_directory())),
                             "application/json; charset=utf-8")
            except FileNotFoundError as error:
                self.respond(404, str(error))
        elif self.path in ("/sfbs_route.js", "/sfbs_route.css"):
            self.respond(200, (ROUTE_ASSETS / self.path[1:]).read_text(),
                         "text/javascript; charset=utf-8" if self.path.endswith(".js")
                         else "text/css; charset=utf-8")
        else:
            self.respond(404, "Unknown endpoint")

    def do_POST(self):
        if self.path not in ("/save", "/log"):
            self.respond(404, "Unknown endpoint")
            return
        try:
            length = int(self.headers["Content-Length"])
            if length < 0 or (self.path == "/log" and length > 65536):
                raise ValueError("Invalid request length")
            payload = json.loads(self.rfile.read(length))
            directory = graph_dir(self.map_name)
            if self.path == "/log":
                if not isinstance(payload, dict) or payload.get("action") not in LOG_ACTIONS:
                    raise ValueError("Unknown selector action")
                append_log(directory, self.route_directory(), payload)
                self.respond(200, "Logged")
                return
            if not isinstance(payload, dict) or "locations" not in payload:
                raise ValueError("Provide graph locations and stop classes")
            save_locations(directory, payload["locations"], self.route_directory(),
                           payload.get("stop_classes"), stops_data=payload.get("stops"),
                           patterns_data=payload.get("patterns"))
            self.respond(200, f"Saved locations and stops for {self.map_name}")
        except (ValueError, TypeError) as error:
            self.respond(400, str(error))
        except FileNotFoundError as error:
            self.respond(404, str(error))
        except Exception as error:
            traceback.print_exc()
            self.respond(500, str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True)
    parser.add_argument("--busline", help="Route to edit (defaults to the map name when available)")
    args = parser.parse_args()
    if Path(args.map).name != args.map or args.map in (".", ".."):
        parser.error("Map must be a graph directory name")
    try:
        drive_nodes(graph_dir(args.map))
    except FileNotFoundError as error:
        parser.error(str(error))
    route_name = args.busline or args.map
    try:
        route_directory = busline_dir(route_name)
        stops_path = busline_path("stops", route_directory)
        has_route = stops_path.is_file() and busline_path("businfo", route_directory).is_file()
    except ValueError as error:
        if args.busline:
            parser.error(str(error))
        stops_path = None
        has_route = False
    if args.busline and not has_route:
        parser.error(f"No saved route stops and timetable for {route_name}")
    Handler.map_name = args.map
    Handler.busline_name = route_name if has_route else ""
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Select locations for {args.map} at {url}", flush=True)
        webbrowser.open(url)
        server.serve_forever()


if __name__ == "__main__":
    main()
