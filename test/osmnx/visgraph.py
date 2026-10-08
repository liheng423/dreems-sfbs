"""Preview drive arcs and mark each street intersection with one vertex dot."""

from pathlib import Path

import osmnx as ox


root = Path(__file__).resolve().parents[2]
graph = ox.load_graphml(root / "data/reqreate/service_area_550/drive.graphml")
intersections = [data for _, data in graph.nodes(data=True) if data["street_count"] >= 3]

fig, ax = ox.plot_graph(
    graph, node_size=0, edge_linewidth=0.5, edge_color="#555555",
    bgcolor="white", figsize=(14, 14), show=False, close=False,
)
ax.scatter(
    [node["x"] for node in intersections],
    [node["y"] for node in intersections],
    s=3, color="#d62728", zorder=3, label="Intersection vertex",
)
ax.legend(loc="lower left")
fig.savefig(Path(__file__).with_name("drive_preview.png"), dpi=220, bbox_inches="tight")
