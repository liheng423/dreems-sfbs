"""Cache OSM points of interest and prepare REQreate sampling zones."""

import hashlib
import json

import osmnx as ox
import pandas as pd
from shapely.geometry import box
from REQreate.overpass_config import configure_overpass

from filters.filters import POI_FILTERS, passes_filters


def sha256(path):
    """Fingerprint a source file used by the POI cache."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pois(cfg, net, area_path, poi_path):
    """Cache OSM POIs that fall inside the service area."""
    source = {
        "schema": 3,
        "area_sha256": sha256(area_path),
        "walk_graph_sha256": sha256(area_path.with_name("walk.graphml")),
        "tags": cfg["poi_tags"],
        "stops": cfg["places"],
        "max_walking_distance_m": cfg["max_walking_distance_m"],
        "poi_filters": [predicate.__name__ for predicate in POI_FILTERS],
    }
    if poi_path.exists():
        snapshot = json.loads(poi_path.read_text())
        if snapshot["source"] == source:
            return [[poi["lat"], poi["lon"]] for poi in snapshot["features"]]

    configure_overpass()
    # The saved POI snapshot is this command's cache; avoid OSMnx's repo-root cache.
    ox.settings.use_cache = False
    features = ox.features_from_polygon(net.polygon, tags=cfg["poi_tags"])
    pois = []
    for (osm_type, osm_id), feature in features.iterrows():
        point = feature.geometry.representative_point()
        if not passes_filters(feature, POI_FILTERS, net, cfg):
            continue
        pois.append({
            "osm_type": osm_type,
            "osm_id": int(osm_id),
            "name": feature["name"] if isinstance(feature.get("name"), str) else None,
            "tags": {tag: feature[tag] for tag in cfg["poi_tags"]
                     if isinstance(feature.get(tag), str)},
            "lat": point.y,
            "lon": point.x,
        })
    locations = [[poi["lat"], poi["lon"]] for poi in pois]
    if not locations:
        raise ValueError("No OSM POIs in the service area")
    snapshot = {"source": source, "features": pois}
    poi_path.parent.mkdir(parents=True, exist_ok=True)
    poi_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    return locations


def set_poi_zones(net, pois, rows, columns):
    """Count eligible POIs in a grid for REQreate's zone-density sampler."""
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
