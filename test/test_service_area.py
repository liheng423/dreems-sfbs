"""Check that a drawn polygon becomes reusable GeoJSON and GraphML files."""

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import networkx as nx
import osmnx as ox
import pandas as pd
from requests.exceptions import ConnectionError as RequestConnectionError, ReadTimeout
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.output_adapters import graph_path
from src.reqreate.utils.graph_utils import GraphNodeIndex, nearest_graph_point


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
    graph.add_node(141925, x=6.2, y=49.5, highway="traffic_signals")
    graph.add_node(141928, x=6.21, y=49.51)
    graph.add_edge(141925, 141928, length=100)
    graph.add_edge(141925, 141928, length=120, highway="residential", maxspeed="30", name="Parallel")
    assert nearest_graph_point(graph, 49.5001, 6.2001) == {
        "node_id": 141925, "point": [49.5, 6.2]}
    assert nearest_graph_point(graph, node_id=141928) == {
        "node_id": 141928, "point": [49.51, 6.21]}
    assert GraphNodeIndex(graph).nearest(49.5001, 6.2001)["node_id"] == 141925
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
        assert set(ox.load_graphml(graph_path("drive_graph", graph_dir)).nodes) == {141925, 141928}
        for kind in ("drive", "walk"):
            nodes = pd.read_csv(graph_path(f"{kind}_nodes", graph_dir))
            edges = pd.read_csv(graph_path(f"{kind}_edges", graph_dir))
            assert nodes.columns[:4].tolist() == ["osmid", "x", "y", "geometry"]
            assert nodes.columns[-1] == "highway"
            assert edges.columns[:7].tolist() == [
                "u", "v", "key", "length", "geometry", "highway", "maxspeed"]
            assert edges.columns[-1] == "name"
            assert nodes[["osmid", "y", "x"]].values.tolist() == [
                [141925, 49.5, 6.2], [141928, 49.51, 6.21]]
            assert edges[["u", "v", "key", "length"]].values.tolist() == [
                [141925, 141928, 0, 100], [141925, 141928, 1, 120]]
            assert edges.loc[1, "name"] == "Parallel"
        depot = json.loads(graph_path("depot", graph_dir).read_text())
        assert depot["original_point"] == [49.568613, 5.922762]
        node = graph.nodes[depot["drive_node_id"]]
        assert depot["drive_point"] == [node["y"], node["x"]]
        assert depot["snap_distance_m"] > 0
        assert json.loads(graph_path("pois", graph_dir).read_text())["features"][0]["tags"] == {"amenity": "cafe"}
        assert fetch.call_args.kwargs["tags"]["amenity"]
        assert all(call.args[0].equals(shape(geometry)) for call in download.call_args_list)
        assert all(call.kwargs["retain_all"] for call in download.call_args_list)
        assert [call.kwargs["network_type"] for call in download.call_args_list] == ["drive", "walk"]
        csv_paths = [graph_path(f"{kind}_{table}", graph_dir)
                     for kind in ("drive", "walk") for table in ("nodes", "edges")]
        original_csvs = {path: path.read_bytes() for path in csv_paths}
        for path in csv_paths:
            path.unlink()
        service_area.save_area(geometry, graph_dir)
        assert {path: path.read_bytes() for path in csv_paths} == original_csvs


def test_distinct_operation_and_service_areas():
    operation = {"type": "Polygon", "coordinates": [[
        [6.1, 49.4], [6.3, 49.4], [6.3, 49.6], [6.1, 49.6], [6.1, 49.4]
    ]]}
    service = {"type": "Polygon", "coordinates": [[
        [6.2, 49.5], [6.21, 49.5], [6.205, 49.51], [6.2, 49.5]
    ]]}
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_node(1, x=6.2, y=49.5)
    pois = pd.DataFrame({
        "geometry": [Point(6.205, 49.502), Point(6.25, 49.55)],
        "name": ["Inside", "Outside service"],
        "amenity": ["cafe", "cafe"],
    }, index=pd.MultiIndex.from_tuples([("node", 1), ("node", 2)]))
    with TemporaryDirectory() as tmp, patch.object(
        ox, "graph_from_polygon", return_value=graph
    ) as download, patch.object(
        ox, "features_from_polygon", return_value=pois
    ) as fetch:
        out_dir = Path(tmp)
        service_area.save_area(operation, out_dir, service)
        assert json.loads(graph_path("area", out_dir).read_text())["geometry"] == service
        assert graph_path("drive_edges", out_dir).read_text() == "u,v,key\n"
        assert all(call.args[0].equals(shape(operation)) for call in download.call_args_list)
        assert fetch.call_args.args[0].equals(shape(service))
        assert [poi["name"] for poi in json.loads(graph_path("pois", out_dir).read_text())["features"]] == ["Inside"]

    outside = {"type": "Polygon", "coordinates": [[
        [6.4, 49.4], [6.5, 49.4], [6.5, 49.5], [6.4, 49.4]
    ]]}
    with TemporaryDirectory() as tmp, patch.object(ox, "graph_from_polygon") as download:
        try:
            service_area.save_area(operation, Path(tmp), outside)
        except ValueError as error:
            assert "inside the operation area" in str(error)
        else:
            raise AssertionError("Service area outside operation area was accepted")
        download.assert_not_called()


def test_recrawl_pois_updates_only_pois():
    geometry = {"type": "Polygon", "coordinates": [[
        [6.2, 49.5], [6.21, 49.5], [6.205, 49.51], [6.2, 49.5]
    ]]}
    with TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        graph_path("area", out_dir).write_text(json.dumps({"geometry": geometry}))
        graph_path("drive_graph", out_dir).write_text("existing graph")
        poi_path = graph_path("pois", out_dir)
        poi_path.write_text("old pois")
        with patch.object(ox, "features_from_polygon", return_value=sample_pois()) as fetch, patch.object(
            ox, "graph_from_polygon"
        ) as download:
            service_area.recrawl_pois(out_dir)
        assert fetch.call_args.args[0].equals(shape(geometry))
        download.assert_not_called()
        assert json.loads(poi_path.read_text())["features"][0]["name"] == "Cafe"
        assert graph_path("drive_graph", out_dir).read_text() == "existing graph"
        with patch.object(ox, "features_from_polygon", side_effect=ValueError("fetch failed")):
            try:
                service_area.recrawl_pois(out_dir)
            except ValueError:
                pass
            else:
                raise AssertionError("Failed recrawl was accepted")
        assert json.loads(poi_path.read_text())["features"][0]["name"] == "Cafe"


def test_recrawl_pois_accepts_graph_name_case():
    with patch.object(sys, "argv", ["define_service_area.py", "--map", "esch", "--recrawl-pois"]), patch.object(
        service_area, "recrawl_pois"
    ) as recrawl:
        service_area.main()
    assert recrawl.call_args.args[0].samefile(service_area.GRAPHS_DIR / "Esch")


def test_validate_endpoint_does_not_download_graphs():
    operation = {"type": "Polygon", "coordinates": [[
        [0, 0], [2, 0], [2, 2], [0, 2], [0, 0]
    ]]}
    inside = {"type": "Polygon", "coordinates": [[
        [0.5, 0.5], [1, 0.5], [1, 1], [0.5, 0.5]
    ]]}
    outside = {"type": "Polygon", "coordinates": [[
        [2, 2], [3, 2], [3, 3], [2, 2]
    ]]}
    with patch.object(ox, "graph_from_polygon") as download:
        for service, expected in ((inside, 200), (outside, 400)):
            body = json.dumps({"operation_area": operation, "service_area": service}).encode()
            handler = object.__new__(service_area.Handler)
            handler.path = "/validate"
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            with patch.object(handler, "send_response") as response, patch.object(
                handler, "send_header"
            ), patch.object(handler, "end_headers"):
                handler.do_POST()
            response.assert_called_once_with(expected)
        download.assert_not_called()


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
            raise ReadTimeout("request timed out")
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
    assert b"Map test operation and service areas" in page
    assert b"const stops = [];" in page
    assert b"operation_area" in page and b"service_area" in page


if __name__ == "__main__":
    test_save_area()
    test_distinct_operation_and_service_areas()
    test_recrawl_pois_updates_only_pois()
    test_recrawl_pois_accepts_graph_name_case()
    test_validate_endpoint_does_not_download_graphs()
    test_save_area_tries_another_overpass_server()
    test_area_map_without_busline()
