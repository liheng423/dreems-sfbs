"""Adapt the saved service-area graphs to REQreate's network interface."""

import json
import math
from functools import lru_cache

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, shape
from REQreate.network_class import Network

from utils.walking_distance import WalkingDistance


class AreaNetwork(Network):
    """Route sampled OSM nodes directly on the saved directed drive graph."""

    # build_area_net attaches the precomputed stop-access distances.
    walking_distance: WalkingDistance

    def _get_random_coord(self, polygon, seed_coord):
        """Draw a point inside the POI-selected polygon."""
        min_lon, min_lat, max_lon, max_lat = polygon.bounds
        rng = np.random.default_rng(seed_coord)
        while True:
            point = Point(rng.uniform(min_lon, max_lon), rng.uniform(min_lat, max_lat))
            if polygon.contains(point):
                return point

    def _get_random_coord_radius(self, lat, lon, radius, polygon, seed_coord):
        """Apply REQreate's radial placement within the stop-accessible area."""
        rng = np.random.default_rng(seed_coord)
        radius_km = float(np.asarray(radius).item()) / 1000
        for _ in range(1000):
            bearing = rng.uniform(0, 2 * math.pi)
            lat_start = math.radians(lat)
            lon_start = math.radians(lon)
            angular_distance = radius_km / 6378.1
            lat_end = math.asin(math.sin(lat_start) * math.cos(angular_distance)
                                + math.cos(lat_start) * math.sin(angular_distance) * math.cos(bearing))
            lon_end = lon_start + math.atan2(
                math.sin(bearing) * math.sin(angular_distance) * math.cos(lat_start),
                math.cos(angular_distance) - math.sin(lat_start) * math.sin(lat_end),
            )
            point = Point(math.degrees(lon_end), math.degrees(lat_end))
            if polygon.contains(point):
                return point
        return Point(-1, -1)

    @lru_cache(maxsize=1)
    def _return_estimated_distance_drive(self, org, dst):
        """Reuse the latest OD distance for its travel-time attribute.

        REQreate rejects unreachable pairs through its minimum-distance constraint.
        """
        try:
            return nx.shortest_path_length(self.G_drive, org, dst, weight="length")
        except nx.NetworkXNoPath:
            return -1

    def _return_estimated_travel_time_drive(self, org, dst):
        """Match REQreate's 20 km/h (5.56 m/s) distance-based estimate."""
        return int(self._return_estimated_distance_drive(org, dst) / 5.56)


def build_area_net(area_path, stops, max_walking_distance_m):
    """Load the area and precompute shortest walking distances to its stops."""
    polygon = shape(json.loads(area_path.read_text())["geometry"])
    net = AreaNetwork(
        "Route 550 service area",
        ox.load_graphml(area_path.with_name("drive.graphml")),
        ox.load_graphml(area_path.with_name("walk.graphml")),
        polygon, pd.DataFrame(),
    )
    net.walking_distance = WalkingDistance(net.G_walk, stops, max_walking_distance_m)
    return net
