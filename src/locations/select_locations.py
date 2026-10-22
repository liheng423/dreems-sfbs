#!/usr/bin/env python3
"""Select optional stops, parking, and charging sites on a saved drive graph."""

import argparse
import csv
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import traceback
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.output_adapters import graph_dir, graph_path

PAGE_PATH = Path(__file__).with_suffix(".html")
LOCATION_FILES = {
    "optional_bus_stops": "optional_bus_stops.csv",
    "parking_locations": "parking_locations.csv",
    "fixed_charging_stations": "fixed_charging_stations.csv",
}


def drive_nodes(directory):
    """Read the existing driving graph's candidate nodes by OSM ID."""
    path = graph_path("drive_nodes", directory)
    if not path.is_file():
        raise FileNotFoundError(f"No saved driving graph nodes: {path}")
    with path.open(newline="", encoding="utf-8") as file:
        return {row["osmid"]: (row["x"], row["y"]) for row in csv.DictReader(file)}


def read_locations(directory):
    """Load previous selections, if any."""
    locations = {}
    for kind, filename in LOCATION_FILES.items():
        path = directory / filename
        if path.is_file():
            with path.open(newline="", encoding="utf-8") as file:
                locations[kind] = [row["osmid"] for row in csv.DictReader(file)]
        else:
            locations[kind] = []
    return locations


def location_data(directory):
    """Return graph nodes and selections still present on that graph."""
    nodes = drive_nodes(directory)
    return {
        "nodes": [[node_id, y, x] for node_id, (x, y) in nodes.items()],
        "locations": {kind: [node_id for node_id in selected if node_id in nodes]
                      for kind, selected in read_locations(directory).items()},
    }


def save_locations(directory, locations):
    """Validate all three lists before writing their separate CSV files."""
    nodes = drive_nodes(directory)
    if not isinstance(locations, dict) or set(locations) != set(LOCATION_FILES):
        raise ValueError("Provide all three location lists")
    for kind, ids in locations.items():
        if not isinstance(ids, list) or any(not isinstance(node_id, str) or node_id not in nodes
                                             for node_id in ids):
            raise ValueError(f"{kind} must contain saved driving graph node IDs")
    for kind, filename in LOCATION_FILES.items():
        with (directory / filename).open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("osmid", "x", "y"))
            for node_id in dict.fromkeys(locations[kind]):
                writer.writerow((node_id, *nodes[node_id]))


class Handler(BaseHTTPRequestHandler):
    """Serve only the location selector and its saved graph data."""

    map_name = ""

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
                self.respond(200, json.dumps(location_data(graph_dir(self.map_name))),
                             "application/json; charset=utf-8")
            except FileNotFoundError as error:
                self.respond(404, str(error))
        else:
            self.respond(404, "Unknown endpoint")

    def do_POST(self):
        if self.path != "/save":
            self.respond(404, "Unknown endpoint")
            return
        try:
            locations = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            directory = graph_dir(self.map_name)
            save_locations(directory, locations)
            self.respond(200, f"Saved three location CSVs to {directory}")
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
    args = parser.parse_args()
    if Path(args.map).name != args.map or args.map in (".", ".."):
        parser.error("Map must be a graph directory name")
    try:
        drive_nodes(graph_dir(args.map))
    except FileNotFoundError as error:
        parser.error(str(error))
    Handler.map_name = args.map
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Select locations for {args.map} at {url}", flush=True)
        webbrowser.open(url)
        server.serve_forever()


if __name__ == "__main__":
    main()
