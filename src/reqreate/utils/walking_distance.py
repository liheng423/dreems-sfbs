"""Filter generated requests by walking access to Route 550 stops."""

import networkx as nx
import numpy as np
import osmnx as ox
from sklearn.neighbors import BallTree


class WalkingDistance:
    """Measure point-to-stop routes with straight links to walking graph nodes."""

    def __init__(self, graph, stops, max_distance_m):
        self.graph = graph
        self.max_distance_m = max_distance_m
        routes = graph.to_undirected()
        source = "Route 550 stops"
        for stop in stops:
            node = ox.nearest_nodes(graph, stop["lon"], stop["lat"])
            walk_node = graph.nodes[node]
            connector = ox.distance.great_circle(stop["lat"], stop["lon"],
                                                 walk_node["y"], walk_node["x"])
            routes.add_edge(source, node, length=connector)
        self.distances = nx.single_source_dijkstra_path_length(routes, source, weight="length")
        self.nodes = list(graph)
        self.tree = BallTree(np.deg2rad([
            (graph.nodes[node]["y"], graph.nodes[node]["x"])
            for node in self.nodes
        ]), metric="haversine")

    def within_limit(self, point):
        """Check the walking route from a coordinate to its closest stop."""
        connectors, indices = self.tree.query(np.deg2rad([[point.y, point.x]]), k=1)
        node = self.nodes[indices[0, 0]]
        connector = connectors[0, 0] * ox.distance.EARTH_RADIUS_M
        return self.distances.get(node, float("inf")) + connector < self.max_distance_m
