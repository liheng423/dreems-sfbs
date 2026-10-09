"""Read saved map POIs and prepare REQreate sampling zones."""

import json

import pandas as pd
from shapely.geometry import box


def load_pois(poi_path):
    """Return sampling coordinates from the selected map's saved POIs."""
    return [[poi["lat"], poi["lon"]]
            for poi in json.loads(poi_path.read_text())["features"]]


def set_poi_zones(net, pois, rows, columns):
    """Build sampling grid zones weighted by their eligible POI counts."""
    min_lon, min_lat, max_lon, max_lat = net.polygon.bounds
    cell_width = (max_lon - min_lon) / columns
    cell_height = (max_lat - min_lat) / rows
    counts = {}
    for lat, lon in pois:
        row = min(int((lat - min_lat) / cell_height), rows - 1)
        column = min(int((lon - min_lon) / cell_width), columns - 1)
        counts[row, column] = counts.get((row, column), 0) + 1
    zones = []
    for (row, column), count in sorted(counts.items()):
        cell = box(min_lon + column * cell_width, min_lat + row * cell_height,
                   min_lon + (column + 1) * cell_width,
                   min_lat + (row + 1) * cell_height)
        zones.append({"polygon": net.polygon.intersection(cell),
                      "number_pois": count, "density_pois": count / len(pois)})
    net.zones = pd.DataFrame(zones)
