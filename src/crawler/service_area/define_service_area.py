#!/usr/bin/env python3
"""Draw operation and service areas and save road graphs and POIs.

Run with
``python main.py select-area test --busline 605``. The browser
opens on a local map; draw the operation area, optionally adjust the service
area, and click Save. The service boundary, OSMnx drive/walk GraphML and CSV
files, and POIs go to ``outputs/graphs/<map>/``.
The road graphs come from current OpenStreetMap data, not the GTFS service date.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tomllib
import traceback
import webbrowser

from requests.exceptions import RequestException

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.output_adapters import (BUSLINES_DIR, GRAPHS_DIR, busline_dir, busline_path, graph_dir,
                                 graph_path, write_area, write_json)
from src.reqreate.utils.graph_utils import GraphNodeIndex

PAGE_PATH = Path(__file__).with_name("service_area.html")
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
OVERPASS_URLS = (
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
)


def validate_areas(geometry, service_geometry=None):
    """Return valid operation and service polygons with service contained."""
    from shapely.geometry import shape

    operation = shape(geometry)
    service = shape(service_geometry) if service_geometry is not None else operation
    for name, polygon in (("operation", operation), ("service", service)):
        if polygon.geom_type != "Polygon" or not polygon.is_valid or polygon.is_empty:
            raise ValueError(f"Select a valid {name} rectangle or polygon")
    if not operation.covers(service):
        raise ValueError("The service area must be inside the operation area")
    return operation, service


def crawl_pois(service, tags):
    """Fetch OSM POIs inside a saved or newly selected service area."""
    import osmnx as ox
    from osmnx._errors import InsufficientResponseError, ResponseStatusCodeError

    for overpass_url in OVERPASS_URLS:
        ox.settings.overpass_url = overpass_url
        try:
            features = ox.features_from_polygon(service, tags=tags)
            break
        except (RequestException, InsufficientResponseError, ResponseStatusCodeError) as error:
            if overpass_url == OVERPASS_URLS[-1]:
                raise
            print(f"Overpass request failed at {overpass_url}: {error}; trying another server", flush=True)
    pois = []
    for (osm_type, osm_id), feature in features.iterrows():
        point = feature.geometry.representative_point()
        if service.contains(point):
            pois.append({
                "osm_type": osm_type,
                "osm_id": int(osm_id),
                "name": feature["name"] if isinstance(feature.get("name"), str) else None,
                "tags": {tag: feature[tag] for tag in tags
                         if isinstance(feature.get(tag), str)},
                "lat": point.y,
                "lon": point.x,
            })
    if not pois:
        raise ValueError("No OSM POIs in the service area")
    return pois


def recrawl_pois(out_dir):
    """Replace only the POIs for an existing saved service area."""
    from shapely.geometry import shape

    area_path = graph_path("area", out_dir)
    if not area_path.is_file():
        raise ValueError(f"Saved service area not found: {area_path}")
    service = shape(json.loads(area_path.read_text())["geometry"])
    if service.geom_type != "Polygon" or not service.is_valid or service.is_empty:
        raise ValueError(f"Invalid saved service area: {area_path}")
    import osmnx as ox
    ox.settings.use_cache = False
    tags = tomllib.loads(MAPS_CFG_PATH.read_text())["poi_tags"]
    write_json(graph_path("pois", out_dir), {"features": crawl_pois(service, tags)})


def save_area(geometry, out_dir, service_geometry=None):
    """Download roads for the operation area and POIs for its service area."""
    from shapely.geometry import mapping

    import osmnx as ox
    from osmnx._errors import InsufficientResponseError, ResponseStatusCodeError

    operation, service = validate_areas(geometry, service_geometry)
    ox.settings.use_cache = False

    map_config = tomllib.loads(MAPS_CFG_PATH.read_text())
    tags = map_config["poi_tags"]
    # OSMnx appends /interpreter to these API base URLs.
    for overpass_url in OVERPASS_URLS:
        ox.settings.overpass_url = overpass_url
        try:
            graphs = {kind: ox.graph_from_polygon(operation, network_type=kind, retain_all=True)
                      for kind in ("drive", "walk")}
            break
        except (RequestException, InsufficientResponseError, ResponseStatusCodeError) as error:
            if overpass_url == OVERPASS_URLS[-1]:
                raise
            print(f"Overpass request failed at {overpass_url}: {error}; trying another server", flush=True)
    pois = crawl_pois(service, tags)
    write_area(mapping(service), graphs, out_dir)
    write_json(graph_path("pois", out_dir), {"features": pois})
    locations = map_config["locations"]
    save_depot(graphs["drive"], out_dir,
               locations.get("depots", {}).get(out_dir.name, locations["depot"]))
    return out_dir


def save_depot(graph, out_dir, depot):
    """Save the configured depot and its nearest drive graph node."""
    snapped = GraphNodeIndex(graph).nearest(depot["lat"], depot["lon"])
    write_json(graph_path("depot", out_dir), {
        "name": depot["name"],
        "original_point": [depot["lat"], depot["lon"]],
        "drive_node_id": snapped["node_id"],
        "drive_point": snapped["point"],
        "snap_distance_m": snapped["distance_m"],
    })


def render_page(map_name, busline_name=None, buslines_dir=BUSLINES_DIR):
    """Show optional route stops on a named area-selection map."""
    route_name = busline_name or map_name
    businfo_path = busline_path("businfo", busline_dir(route_name, buslines_dir))
    if busline_name or businfo_path.is_file():
        stops = json.loads(businfo_path.read_text())["stops"]
    else:
        stops = []
    return (PAGE_PATH.read_text()
            .replace("__MAP__", map_name)
            .replace("__STOPS__", json.dumps(stops))).encode()


class Handler(BaseHTTPRequestHandler):
    """Serve the local selection page and accept its chosen polygon."""

    map_name = ""
    busline_name = None

    def do_GET(self):
        page = render_page(self.map_name, self.busline_name)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        try:
            areas = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            operation = areas["operation_area"]
            service = areas.get("service_area")
            if self.path == "/validate":
                validate_areas(operation, service)
                message, status = "Area is valid", 200
            elif self.path == "/save":
                out_dir = save_area(operation, graph_dir(self.map_name), service)
                message, status = f"Saved service area, operation-area road graphs, POIs, and depot to {out_dir}", 200
            else:
                message, status = "Unknown endpoint", 404
        except ValueError as error:
            message, status = str(error), 400
        except Exception as error:
            traceback.print_exc()
            message, status = str(error), 500
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode())


def main():
    """Open the local map and keep serving until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True)
    parser.add_argument("--busline")
    parser.add_argument("--recrawl-pois", action="store_true")
    args = parser.parse_args()
    if args.recrawl_pois:
        if Path(args.map).name != args.map or args.map in (".", ".."):
            parser.error("Map must be a graph directory name")
        out_dir = graph_dir(args.map)
        if not out_dir.is_dir() and GRAPHS_DIR.is_dir():
            matches = [path for path in GRAPHS_DIR.iterdir()
                       if path.is_dir() and path.name.casefold() == args.map.casefold()]
            if len(matches) == 1:
                out_dir = matches[0]
        try:
            recrawl_pois(out_dir)
        except ValueError as error:
            parser.error(str(error))
        print(f"Updated {graph_path('pois', out_dir)}")
        return
    Handler.map_name = args.map
    Handler.busline_name = args.busline
    try:
        import osmnx
    except ModuleNotFoundError as error:
        raise SystemExit(
            f"Missing Python package '{error.name}'. Run with "
            ".venv/bin/python src/crawler/service_area/define_service_area.py"
        ) from error

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Select operation and service areas at {url}", flush=True)
        webbrowser.open(url)
        server.serve_forever()


if __name__ == "__main__":
    main()
