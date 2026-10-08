#!/usr/bin/env python3
"""Draw a Route 550 service area in a browser and save its OSM road graphs.

Run with
``.venv/bin/python src/crawler/service_area/define_service_area.py``. The browser
opens on a local map; draw one rectangle or polygon and click Save. The chosen
boundary and OSMnx drive/walk GraphML files go to
``data/reqreate/service_area_550/``.
The road graphs come from current OpenStreetMap data, not the GTFS service date.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

ROOT = Path(__file__).resolve().parents[3]
CRAWL_PATH = ROOT / "data/crawled_550.json"
OUT_DIR = ROOT / "data/reqreate/service_area_550"

PAGE_PATH = Path(__file__).with_name("service_area.html")


def save_area(geometry, out_dir=OUT_DIR):
    """Download roads within the selected polygon and keep its GeoJSON."""
    import osmnx as ox
    from shapely.geometry import mapping, shape

    ox.settings.use_cache = False

    polygon = shape(geometry)
    if polygon.geom_type != "Polygon" or not polygon.is_valid or polygon.is_empty:
        raise ValueError("Select a valid rectangle or polygon")

    graphs = {kind: ox.graph_from_polygon(polygon, network_type=kind, retain_all=True)
              for kind in ("drive", "walk")}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "service_area.geojson").write_text(json.dumps({
        "type": "Feature", "geometry": mapping(polygon), "properties": {}
    }, indent=2) + "\n")
    for kind, graph in graphs.items():
        ox.save_graphml(graph, filepath=out_dir / f"{kind}.graphml")
    return out_dir


class Handler(BaseHTTPRequestHandler):
    """Serve the local selection page and accept its chosen polygon."""

    def do_GET(self):
        stops = json.loads(CRAWL_PATH.read_text())["stops"]
        page = PAGE_PATH.read_text().replace("__STOPS__", json.dumps(stops)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        geometry = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            out_dir = save_area(geometry)
            message, status = f"Saved boundary and drive/walk graphs to {out_dir}", 200
        except Exception as error:
            message, status = str(error), 500
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode())


def main():
    """Open the local map and keep serving until interrupted."""
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
