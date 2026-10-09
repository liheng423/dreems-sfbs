"""Define where busline sources, road graphs, and request instances live."""

import json
from itertools import count
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BUSLINES_DIR = DATA_DIR / "buslines"
GRAPHS_DIR = DATA_DIR / "graphs"
REQUESTS_DIR = DATA_DIR / "requests"
BUSLINE_FILES = {
    "businfo": "businfo.json",
    "stops": "stops.json",
    "energy": "energy.json",
    "distance_matrix": "distance_matrix.json",
}
GRAPH_FILES = {
    "area": "service_area.geojson",
    "drive_graph": "drive.graphml",
    "walk_graph": "walk.graphml",
    "pois": "pois.json",
}
REQUEST_FILES = {
    "pool": "raw_requests.json",
    "metadata": "raw_requests_metadata.json",
}


def busline_dir(route_short_name, buslines_dir=BUSLINES_DIR):
    """Return the directory holding one GTFS route's source files."""
    if not route_short_name.replace("-", "").isalnum():
        raise ValueError("Route short name must contain letters, digits, or hyphens")
    return buslines_dir / route_short_name


def graph_dir(graph_name, graphs_dir=GRAPHS_DIR):
    """Return one service-area graph directory, independent of buslines."""
    return graphs_dir / graph_name


def busline_path(name, directory):
    """Resolve a busline artifact within one route directory."""
    return directory / BUSLINE_FILES[name]


def graph_path(name, directory):
    """Resolve an area or road graph within one graph directory."""
    return directory / GRAPH_FILES[name]


def request_path(name, directory):
    """Resolve a request artifact within one generated instance."""
    return directory / REQUEST_FILES[name]


def available_buslines(buslines_dir=BUSLINES_DIR):
    """List routes with both GTFS data and REQreate stop places."""
    if not buslines_dir.exists():
        return []
    return [directory.name for directory in sorted(buslines_dir.iterdir())
            if directory.is_dir() and busline_path("businfo", directory).is_file()
            and busline_path("stops", directory).is_file()]


def available_graphs(graphs_dir=GRAPHS_DIR):
    """List complete service-area and drive/walk graph sets."""
    return [directory.name for directory in sorted(graphs_dir.iterdir())
            if directory.is_dir() and all(graph_path(name, directory).is_file()
                                          for name in GRAPH_FILES)]


def create_request_dir(busline_name, graph_name, requests_dir=REQUESTS_DIR):
    """Reserve a new, numbered request instance for the selected inputs."""
    requests_dir.mkdir(parents=True, exist_ok=True)
    for number in count(1):
        directory = requests_dir / f"{busline_name}_{graph_name}_{number:04d}"
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return directory


def write_json(path, value, *, compact=False):
    """Write project JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {"separators": (",", ":")} if compact else {"indent": 2}
    path.write_text(json.dumps(value, ensure_ascii=False, **options) + "\n", encoding="utf-8")
    return path


def write_area(geometry, graphs, directory):
    """Save the selected GeoJSON service area and its two OSM road graphs."""
    import osmnx as ox

    write_json(graph_path("area", directory), {
        "type": "Feature", "geometry": geometry, "properties": {},
    })
    for kind, graph in graphs.items():
        path = graph_path(f"{kind}_graph", directory)
        path.parent.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(graph, filepath=path)
    return directory
