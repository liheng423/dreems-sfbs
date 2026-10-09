#!/usr/bin/env python3
"""Draw a named service area and save its OSM road graphs and POIs.

Run with
``python main.py select-area test --busline 605``. The browser
opens on a local map; draw one rectangle or polygon and click Save. The chosen
boundary, OSMnx drive/walk GraphML files, and POIs go to ``data/graphs/<map>/``.
The road graphs come from current OpenStreetMap data, not the GTFS service date.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tomllib
import webbrowser

from requests.exceptions import ConnectionError as RequestConnectionError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.output_adapters import (BUSLINES_DIR, busline_dir, busline_path, graph_dir,
                                 graph_path, write_area, write_json)

PAGE_PATH = Path(__file__).with_name("service_area.html")
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
OVERPASS_URLS = (
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
)


def save_area(geometry, out_dir):
    """Download roads and POIs within the polygon, then save the map inputs."""
    from shapely.geometry import mapping, shape

    import osmnx as ox
    from osmnx._errors import ResponseStatusCodeError

    ox.settings.use_cache = False

    polygon = shape(geometry)
    if polygon.geom_type != "Polygon" or not polygon.is_valid or polygon.is_empty:
        raise ValueError("Select a valid rectangle or polygon")

    tags = tomllib.loads(MAPS_CFG_PATH.read_text())["poi_tags"]
    # OSMnx appends /interpreter to these API base URLs.
    for overpass_url in OVERPASS_URLS:
        ox.settings.overpass_url = overpass_url
        try:
            graphs = {kind: ox.graph_from_polygon(polygon, network_type=kind, retain_all=True)
                      for kind in ("drive", "walk")}
            features = ox.features_from_polygon(polygon, tags=tags)
            break
        except (RequestConnectionError, ResponseStatusCodeError):
            if overpass_url == OVERPASS_URLS[-1]:
                raise
            print(f"Overpass request failed at {overpass_url}; trying another server", flush=True)
    pois = []
    for (osm_type, osm_id), feature in features.iterrows():
        point = feature.geometry.representative_point()
        if polygon.contains(point):
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
    write_area(mapping(polygon), graphs, out_dir)
    write_json(graph_path("pois", out_dir), {"features": pois})
    return out_dir


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
        geometry = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            out_dir = save_area(geometry, graph_dir(self.map_name))
            message, status = f"Saved boundary, drive/walk graphs, and POIs to {out_dir}", 200
        except Exception as error:
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
    args = parser.parse_args()
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
        print(f"Select the service area at {url}", flush=True)
        webbrowser.open(url)
        server.serve_forever()


if __name__ == "__main__":
    main()
