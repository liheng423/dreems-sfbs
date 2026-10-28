"""Read saved map POIs and prepare REQreate sampling zones."""

import json

import osmnx as ox
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform


def load_pois(poi_path):
    """Return sampling coordinates from the selected map's saved POIs."""
    return [[poi["lat"], poi["lon"]]
            for poi in json.loads(poi_path.read_text(encoding="utf-8"))["features"]]


def set_poi_zones(net, pois, cell_size_m):
    """Build metre-sized sampling zones weighted by their eligible POI counts."""
    if cell_size_m <= 0:
        raise ValueError("POI grid cell_size_m must be positive")
    polygon, crs = ox.projection.project_geometry(net.polygon)
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    unproject = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    min_x, min_y, _, _ = polygon.bounds
    counts = {}
    for lat, lon in pois:
        x, y = project(lon, lat)
        row = int((y - min_y) // cell_size_m)
        column = int((x - min_x) // cell_size_m)
        counts[row, column] = counts.get((row, column), 0) + 1
    zones = []
    for (row, column), count in sorted(counts.items()):
        cell = box(min_x + column * cell_size_m, min_y + row * cell_size_m,
                   min_x + (column + 1) * cell_size_m,
                   min_y + (row + 1) * cell_size_m)
        zones.append({"polygon": transform(unproject, polygon.intersection(cell)),
                      "number_pois": count, "density_pois": count / len(pois)})
    net.zones = pd.DataFrame(zones)
