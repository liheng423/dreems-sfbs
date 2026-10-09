"""Check that a drawn polygon becomes reusable GeoJSON and GraphML files."""

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import networkx as nx
import osmnx as ox
import pandas as pd
from osmnx._errors import ResponseStatusCodeError
from requests.exceptions import ConnectionError as RequestConnectionError
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.output_adapters import graph_path


SCRIPT = Path(__file__).resolve().parents[1] / "src/crawler/service_area/define_service_area.py"
spec = importlib.util.spec_from_file_location("define_service_area", SCRIPT)
service_area = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service_area)


def sample_pois():
    """Return one OSM-style POI inside the test polygon."""
    return pd.DataFrame({"geometry": [Point(6.205, 49.502)], "name": ["Cafe"],
                         "amenity": ["cafe"]},
                        index=pd.MultiIndex.from_tuples([("node", 1)]))


def test_save_area():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_node(1, x=6.2, y=49.5)
    graph.add_node(2, x=6.21, y=49.51)
    graph.add_edge(1, 2, length=100)
    geometry = {"type": "Polygon", "coordinates": [[
        [6.2, 49.5], [6.21, 49.5], [6.205, 49.51], [6.2, 49.5]
    ]]}

    with TemporaryDirectory() as tmp, patch.object(ox, "graph_from_polygon", return_value=graph) as download, patch.object(
        ox, "features_from_polygon", return_value=sample_pois()
    ) as fetch:
        graph_dir = Path(tmp) / "graphs"
        out_dir = service_area.save_area(geometry, graph_dir)
        area = json.loads(graph_path("area", graph_dir).read_text())
        assert area["geometry"] == geometry
        assert out_dir == graph_dir
        assert graph_path("drive_graph", graph_dir).is_file()
        assert graph_path("walk_graph", graph_dir).is_file()
        assert json.loads(graph_path("pois", graph_dir).read_text())["features"][0]["tags"] == {"amenity": "cafe"}
        assert fetch.call_args.kwargs["tags"]["amenity"]
        assert all(call.args[0].equals(shape(geometry)) for call in download.call_args_list)
        assert all(call.kwargs["retain_all"] for call in download.call_args_list)
        assert [call.kwargs["network_type"] for call in download.call_args_list] == ["drive", "walk"]


def test_save_area_tries_another_overpass_server():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_node(1, x=6.2, y=49.5)
    graph.add_node(2, x=6.21, y=49.51)
    graph.add_edge(1, 2, length=100)
    geometry = {"type": "Polygon", "coordinates": [[
        [6.2, 49.5], [6.21, 49.5], [6.205, 49.51], [6.2, 49.5]
    ]]}
    overpass_urls = []

    def download(*args, **kwargs):
        overpass_urls.append(ox.settings.overpass_url)
        if len(overpass_urls) == 1:
            raise RequestConnectionError("connection refused")
        if len(overpass_urls) == 2:
            raise ResponseStatusCodeError("500 Internal Server Error")
        return graph

    with TemporaryDirectory() as tmp, patch.object(ox, "graph_from_polygon", side_effect=download), patch.object(
        ox, "features_from_polygon", return_value=sample_pois()
    ):
        service_area.save_area(geometry, Path(tmp))

    assert overpass_urls == [
        "https://overpass-api.de/api",
        "https://overpass.private.coffee/api",
        "https://maps.mail.ru/osm/tools/overpass/api",
        "https://maps.mail.ru/osm/tools/overpass/api",
    ]


def test_area_map_without_busline():
    with TemporaryDirectory() as tmp:
        page = service_area.render_page("test", buslines_dir=Path(tmp))
    assert b"Map test service area" in page
    assert b"const stops = [];" in page


if __name__ == "__main__":
    test_save_area()
    test_save_area_tries_another_overpass_server()
    test_area_map_without_busline()
