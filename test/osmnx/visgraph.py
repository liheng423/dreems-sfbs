"""Save a selected map's drive arcs, graph vertices, and zone grid preview."""

import argparse
import json
import sys
import tomllib
from math import ceil
from pathlib import Path

import osmnx as ox
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform


root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from src.output_adapters import available_graphs, graph_dir, graph_path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--map", required=True, choices=available_graphs(),
                    help="Saved map to preview")
args = parser.parse_args()
map_dir = graph_dir(args.map)

graph = ox.load_graphml(graph_path("drive_graph", map_dir))
vertices = [data for _, data in graph.nodes(data=True)]
intersections = [node for node in vertices if node.get("street_count", 0) >= 3]
config = tomllib.loads((root / "src/reqreate/maps/map_config.toml").read_text(encoding="utf-8"))
area = json.loads(graph_path("area", map_dir).read_text(encoding="utf-8"))
boundary = area["geometry"]["coordinates"][0]
cell_size_m = config["method_pois"]["cell_size_m"]
projected_area, crs = ox.projection.project_geometry(shape(area["geometry"]))
min_x, min_y, max_x, max_y = projected_area.bounds
unproject = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
columns = ceil((max_x - min_x) / cell_size_m)

fig, ax = ox.plot_graph(
    graph, node_size=0, edge_linewidth=0.5, edge_color="#555555",
    bgcolor="white", figsize=(14, 14), show=False, close=False,
)
area_outline = Polygon(boundary, fill=False, edgecolor="#2678a8", linewidth=1.2,
                       zorder=4, label="Service area")
ax.add_patch(area_outline)
lines = [transform(unproject, LineString([(min_x + column * cell_size_m, min_y),
                                          (min_x + column * cell_size_m, max_y)]))
         for column in range(1, columns)]
lines += [transform(unproject, LineString([(min_x, min_y + row * cell_size_m),
                                           (max_x, min_y + row * cell_size_m)]))
          for row in range(1, ceil((max_y - min_y) / cell_size_m))]
grid = LineCollection([list(line.coords) for line in lines], colors="#2678a8",
                      linewidths=0.35, alpha=0.7, zorder=2,
                      label=f"Zone boundaries ({cell_size_m} m cells)")
grid.set_clip_path(area_outline)
ax.add_collection(grid)
ax.scatter(
    [node["x"] for node in vertices],
    [node["y"] for node in vertices],
    s=8, color="#e69f00", zorder=3, label=f"Graph vertices ({len(vertices)})",
)
ax.scatter(
    [node["x"] for node in intersections],
    [node["y"] for node in intersections],
    s=12, color="#d62728", zorder=4, label=f"Intersections ({len(intersections)})",
)
ax.legend(loc="upper left")
preview_dir = root / "visualizations"
preview_dir.mkdir(exist_ok=True)
preview_path = preview_dir / f"drive_preview_{args.map}.png"
fig.savefig(preview_path, dpi=220, bbox_inches="tight")
print(f"Saved {args.map} preview to {preview_path}")
