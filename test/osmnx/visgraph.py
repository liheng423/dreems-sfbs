"""Preview drive arcs, intersection vertices, and the configured zone grid."""

import json
import tomllib
from pathlib import Path

import osmnx as ox
from matplotlib.patches import Polygon


root = Path(__file__).resolve().parents[2]
graph = ox.load_graphml(root / "data/reqreate/service_area_550/drive.graphml")
intersections = [data for _, data in graph.nodes(data=True) if data["street_count"] >= 3]
config = tomllib.loads((root / "src/reqreate/request_gen.toml").read_text())
area = json.loads((root / config["service_area_path"]).read_text())
boundary = area["geometry"]["coordinates"][0]
min_lon, min_lat = map(min, zip(*boundary))
max_lon, max_lat = map(max, zip(*boundary))
rows = config["method_pois"]["rows"]
columns = config["method_pois"]["columns"]

fig, ax = ox.plot_graph(
    graph, node_size=0, edge_linewidth=0.5, edge_color="#555555",
    bgcolor="white", figsize=(14, 14), show=False, close=False,
)
# REQreate's POI zones use equal cells across the service area's bounds.
area_outline = Polygon(boundary, fill=False, edgecolor="#2678a8", linewidth=1.2,
                       zorder=4, label="Service area")
ax.add_patch(area_outline)
vertical_lines = ax.vlines(
    [min_lon + (max_lon - min_lon) * column / columns for column in range(1, columns)],
    min_lat, max_lat, colors="#2678a8", linewidth=0.35, alpha=0.7,
    zorder=2, label=f"Zone boundaries ({rows} × {columns})",
)
horizontal_lines = ax.hlines(
    [min_lat + (max_lat - min_lat) * row / rows for row in range(1, rows)],
    min_lon, max_lon, colors="#2678a8", linewidth=0.35, alpha=0.7, zorder=2,
)
vertical_lines.set_clip_path(area_outline)
horizontal_lines.set_clip_path(area_outline)
ax.scatter(
    [node["x"] for node in intersections],
    [node["y"] for node in intersections],
    s=3, color="#d62728", zorder=3, label="Intersection vertex",
)
ax.legend(loc="upper left")
fig.savefig(Path(__file__).with_name("drive_preview.png"), dpi=220, bbox_inches="tight")
