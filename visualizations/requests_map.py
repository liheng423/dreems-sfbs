"""Draw one saved request pool over its matching driving network."""

import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from shapely import wkt

from src.output_adapters import busline_dir


ROOT = Path(__file__).resolve().parents[1]


def draw_requests_map(graph_name, instance, output_file=None):
    if any(name in ("", ".", "..") or Path(name).name != name
           for name in (graph_name, instance)):
        raise ValueError("Map and instance must be folder names")
    requests_file = ROOT / "outputs" / "requests" / instance / "requests.json"
    requests = list(json.loads(requests_file.read_text())["requests"].values())
    settings = dict(line.split(" = ", 1) for line in
                    (requests_file.parent / "parameters.txt").read_text().splitlines()[:3])
    busline = json.loads(settings["busline"]) if json.loads(settings["task"]) == "SFBS" else None
    if busline:
        info = json.loads((busline_dir(busline, ROOT / "data" / "buslines") / "businfo.json").read_text())
        stops = {stop["stop_id"]: (stop["stop_lon"], stop["stop_lat"])
                 for stop in info["stops"]}
        route_lines = [[stops[stop_id] for stop_id in pattern["stop_ids"]]
                       for pattern in info["patterns"]]
    graph_dir = ROOT / "outputs" / "graphs" / graph_name
    output_file = Path(output_file) if output_file else ROOT / "visualizations" / f"{requests_file.parent.name}_requests_map.png"

    with (graph_dir / "drive_nodes.csv").open(newline="") as source:
        nodes = {row["osmid"]: (float(row["x"]), float(row["y"]))
                 for row in csv.DictReader(source)}
    roads = []
    with (graph_dir / "drive_edges.csv").open(newline="") as source:
        for edge in csv.DictReader(source):
            roads.append(list(wkt.loads(edge["geometry"]).coords) if edge.get("geometry")
                         else [nodes[edge["u"]], nodes[edge["v"]]])
    pois = json.loads((graph_dir / "pois.json").read_text())["features"]
    depot = json.loads((graph_dir / "depot.json").read_text())
    depot_lat, depot_lon = depot["drive_point"]
    area = json.loads((graph_dir / "service_area.geojson").read_text())["geometry"]
    polygons = [area["coordinates"]] if area["type"] == "Polygon" else area["coordinates"]
    boundaries = [ring for polygon in polygons for ring in polygon]

    origins = [(request["origin"][1], request["origin"][0]) for request in requests]
    destinations = [(request["destination"][1], request["destination"][0]) for request in requests]
    mean_lat = sum(point[1] for point in nodes.values()) / len(nodes)
    all_points = (list(nodes.values()) + origins + destinations + [(depot_lon, depot_lat)]
                  + [tuple(point) for ring in boundaries for point in ring])
    lon_span = max(point[0] for point in all_points) - min(point[0] for point in all_points)
    lat_span = max(point[1] for point in all_points) - min(point[1] for point in all_points)
    height = max(4.5, min(10, 13 * lat_span / (lon_span * math.cos(math.radians(mean_lat)))))
    fig, ax = plt.subplots(figsize=(13, height), layout="constrained")
    ax.add_collection(LineCollection(roads, colors="#b7c1c9", linewidths=0.55, zorder=1))
    ax.add_collection(LineCollection(list(zip(origins, destinations)), colors="#577fa8",
                                     linewidths=0.65, alpha=0.28, label="Straight OD",
                                     zorder=2))
    if busline:
        ax.add_collection(LineCollection(route_lines, colors="#1268a3", linewidths=2.5,
                                         label=f"Bus {busline} (stops linked)", zorder=3))
        ax.scatter(*zip(*stops.values()), s=12, color="#1268a3", edgecolors="white",
                   linewidths=0.4, label="Bus stops", zorder=4)
    if pois:
        ax.scatter([poi["lon"] for poi in pois], [poi["lat"] for poi in pois],
                   s=7, color="#d8c895", alpha=0.65, linewidths=0,
                   label=f"POIs ({len(pois)})", zorder=4)
    if requests:
        ax.scatter(*zip(*origins), s=18, color="#008f85", edgecolors="white",
                   linewidths=0.25, label=f"Origins ({len(requests)})", zorder=5)
        ax.scatter(*zip(*destinations), s=18, color="#d96845", edgecolors="white",
                   linewidths=0.25, label=f"Destinations ({len(requests)})", zorder=6)
    ax.scatter(depot_lon, depot_lat, s=90, marker="s", color="#c62828",
               edgecolors="white", linewidths=0.8, label="Depot", zorder=7)
    for index, ring in enumerate(boundaries):
        ax.plot(*zip(*ring), color="#8356a6", linewidth=1.8,
                label="Service area" if index == 0 else None, zorder=8)
    ax.legend(loc="upper left")
    ax.autoscale()
    ax.set_aspect(1 / math.cos(math.radians(mean_lat)))
    ax.set(xlabel="Longitude", ylabel="Latitude",
           title=f"{requests_file.parent.name} · {graph_name} driving network")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_file, dpi=180)
    plt.close(fig)
    return output_file
