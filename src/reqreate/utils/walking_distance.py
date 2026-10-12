"""Filter generated requests by walking access to bus stops."""

import networkx as nx
import osmnx as ox

from src.reqreate.utils.graph_utils import GraphNodeIndex


class WalkingDistance:
    """Measure point-to-stop routes with straight links to walking graph nodes."""

    def __init__(self, graph, stops, max_distance_m):
        """Precompute stop routes and index nodes for nearest-node lookup."""
        self.graph = graph.to_undirected()
        self.max_distance_m = max_distance_m
        self.stop_distances = {}
        routes = self.graph.copy()
        source = "Bus stops"
        self.index = GraphNodeIndex(graph)
        for stop in stops:
            snapped = self.index.nearest(stop["lat"], stop["lon"])
            node = snapped["node_id"]
            connector = ox.distance.great_circle(stop["lat"], stop["lon"],
                                                 *snapped["point"])
            routes.add_edge(source, node, length=connector)
            stop_id = stop["name"].removeprefix("Stop_")
            self.stop_distances[stop_id] = (
                connector,
                nx.single_source_dijkstra_path_length(self.graph, node, weight="length"),
            )
        self.distances = nx.single_source_dijkstra_path_length(routes, source, weight="length")

    def nearest_node(self, point):
        """Return the nearest walking node and its straight-line distance in metres."""
        snapped = self.index.nearest(point.y, point.x)
        return snapped["node_id"], snapped["distance_m"]

    def distance_to_nearest_stop(self, point):
        """Return the shortest walk to any stop, including endpoint connectors."""
        node, connector = self.nearest_node(point)
        return self.distances.get(node, float("inf")) + connector

    def within_limit(self, point):
        """Return whether the nearest-stop walk is below the configured limit."""
        return self.distance_to_nearest_stop(point) < self.max_distance_m

    def accessible_stops(self, point):
        """Return walking distances to all stops below the access limit."""
        node, connector = self.nearest_node(point)
        return {
            stop_id: distance + stop_connector + connector
            for stop_id, (stop_connector, distances) in self.stop_distances.items()
            if (distance := distances.get(node, float("inf"))) + stop_connector + connector
            < self.max_distance_m
        }

    def direct_distance_within(self, origin, destination, limit_m):
        """Return whether the direct walk is at most limit_m metres."""
        origin_node, origin_connector = self.nearest_node(origin)
        destination_node, destination_connector = self.nearest_node(destination)
        remaining = limit_m - origin_connector - destination_connector
        if remaining < 0:
            return False
        distances = nx.single_source_dijkstra_path_length(
            self.graph, origin_node, cutoff=remaining, weight="length"
        )
        return destination_node in distances
