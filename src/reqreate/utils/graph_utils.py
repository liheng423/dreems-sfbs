"""Resolve a WGS84 coordinate to a saved OSM graph node."""

import osmnx as ox
import numpy as np
from sklearn.neighbors import BallTree


def nearest_graph_point(graph, lat=None, lon=None, *, node_id=None):
    """Return the nearest node ID and its [latitude, longitude] coordinates.

    Supply node_id alone when another step has already snapped the coordinate.
    """
    if node_id is None:
        if lat is None or lon is None:
            raise ValueError("lat and lon are required when node_id is omitted")
        node_id = ox.distance.nearest_nodes(graph, lon, lat)
    node = graph.nodes[node_id]
    return {"node_id": node_id, "point": [node["y"], node["x"]]}


class GraphNodeIndex:
    """Reuse one nearest-node index for repeated WGS84 coordinate lookups."""

    def __init__(self, graph):
        self.graph = graph
        self.nodes = list(graph)
        self.tree = BallTree(np.deg2rad([
            (graph.nodes[node]["y"], graph.nodes[node]["x"])
            for node in self.nodes
        ]), metric="haversine")

    def nearest(self, lat, lon):
        """Return node ID, [lat, lon], and straight-line distance in metres."""
        distances, indices = self.tree.query(np.deg2rad([[lat, lon]]), k=1)
        result = nearest_graph_point(self.graph, node_id=self.nodes[indices[0, 0]])
        result["distance_m"] = float(distances[0, 0] * ox.distance.EARTH_RADIUS_M)
        return result
