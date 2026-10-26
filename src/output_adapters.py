"""Define where busline sources, road graphs, and request instances live."""

import json
from itertools import count
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BUSLINES_DIR = DATA_DIR / "buslines"
GRAPHS_DIR = ROOT / "outputs" / "graphs"
REQUESTS_DIR = ROOT / "outputs" / "requests"
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
    "drive_nodes": "drive_nodes.csv",
    "drive_edges": "drive_edges.csv",
    "walk_nodes": "walk_nodes.csv",
    "walk_edges": "walk_edges.csv",
    "pois": "pois.json",
    "depot": "depot.json",
}
GRAPH_CSV_PRIORITY = {
    "nodes": ("osmid", "x", "y", "geometry"),
    "edges": ("u", "v", "key", "length", "geometry", "highway", "maxspeed", "access", "oneway"),
}
REQUEST_FILES = {
    "pool": "requests.json",
    "csv": "requests.csv",
    "metadata": "requests_metadata.json",  # Read old instances only.
    "operations": "operations.json",
    "parameters": "parameters.txt",
}
REQUEST_OUTPUT_FIELDS = (
    "reqid", "is_prebooked", "lead_time", "order_place_time", "earliest_departure",
    "latest_arrival", "pickup_from", "pickup_to", "dropoff_from", "dropoff_to",
    "service_time", "origin", "destination", "originnode_drive",
    "destinationnode_drive", "direct_distance", "direct_travel_time", "energy_kwh",
    "boarding_stop_id", "alighting_stop_id", "boarding_walk_distance_m",
    "alighting_walk_distance_m", "origin_drive_point", "destination_drive_point",
    "boarding_stop_point", "alighting_stop_point",
)
SFBS_OUTPUT_FIELDS = tuple(name for name in REQUEST_OUTPUT_FIELDS
                           if name not in ("originnode_drive", "destinationnode_drive"))
DARP_OUTPUT_FIELDS = tuple(name for name in REQUEST_OUTPUT_FIELDS
                           if not name.startswith(("boarding_", "alighting_")))


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
    path = directory / REQUEST_FILES[name]
    legacy = directory / f"raw_{REQUEST_FILES[name]}"
    return legacy if name != "operations" and not path.exists() and legacy.exists() else path


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


def create_request_dir(task, graph_name, requests_dir=REQUESTS_DIR):
    """Reserve a numbered request directory for the task and map."""
    requests_dir.mkdir(parents=True, exist_ok=True)
    for number in count(1):
        directory = requests_dir / f"{task.lower()}_{graph_name}_{number:04d}"
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


def graph_csv_columns(frame, priority):
    """Put routing columns first and optional OSM attributes last."""
    return [name for name in priority if name in frame] + sorted(set(frame.columns) - set(priority))


def write_graph_csv(graph, kind, directory):
    """Export one saved road graph to matching node and edge CSV files."""
    import osmnx as ox

    directory.mkdir(parents=True, exist_ok=True)
    nodes = ox.convert.graph_to_gdfs(graph, edges=False).reset_index()
    nodes[graph_csv_columns(nodes, GRAPH_CSV_PRIORITY["nodes"])].to_csv(
        graph_path(f"{kind}_nodes", directory), index=False)
    edges_path = graph_path(f"{kind}_edges", directory)
    if graph.number_of_edges():
        edges = ox.convert.graph_to_gdfs(graph, nodes=False).reset_index()
        edges[graph_csv_columns(edges, GRAPH_CSV_PRIORITY["edges"])].to_csv(edges_path, index=False)
    else:
        edges_path.write_text("u,v,key\n", encoding="utf-8")


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
        write_graph_csv(graph, kind, directory)
    return directory
