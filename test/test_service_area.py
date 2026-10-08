"""Check that a drawn polygon becomes reusable GeoJSON and GraphML files."""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import networkx as nx
import osmnx as ox
from shapely.geometry import shape


SCRIPT = Path(__file__).resolve().parents[1] / "src/crawler/service_area/define_service_area.py"
spec = importlib.util.spec_from_file_location("define_service_area", SCRIPT)
service_area = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service_area)


def test_save_area():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_node(1, x=6.2, y=49.5)
    graph.add_node(2, x=6.21, y=49.51)
    graph.add_edge(1, 2, length=100)
    geometry = {"type": "Polygon", "coordinates": [[
        [6.2, 49.5], [6.21, 49.5], [6.205, 49.51], [6.2, 49.5]
    ]]}

    with TemporaryDirectory() as tmp, patch.object(ox, "graph_from_polygon", return_value=graph) as download:
        out_dir = service_area.save_area(geometry, Path(tmp))
        area = json.loads((out_dir / "service_area.geojson").read_text())
        assert area["geometry"] == geometry
        assert (out_dir / "drive.graphml").is_file()
        assert (out_dir / "walk.graphml").is_file()
        assert all(call.args[0].equals(shape(geometry)) for call in download.call_args_list)
        assert all(call.kwargs["retain_all"] for call in download.call_args_list)
        assert [call.kwargs["network_type"] for call in download.call_args_list] == ["drive", "walk"]


if __name__ == "__main__":
    test_save_area()
