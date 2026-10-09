"""Exercise a non-550 route through GTFS, stop places, and demand settings."""

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/reqreate"))

from src.output_adapters import (available_buslines, busline_dir, busline_path, create_request_dir, graph_dir,
                                 graph_path, request_path, write_json)
from src.crawler.busline import crawl_gtfs
from src.reqreate import generate
from src.crawler.service_area.define_service_area import render_page, save_area
from filters import route_schedule
import main as project_main


TABLES = {
    "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR605,605,Test route,3\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,0,1,0,0,0,0,0,20261001,20261031\n",
    "calendar_dates.txt": "service_id,date,exception_type\n",
    "trips.txt": "route_id,service_id,trip_id,direction_id\nR605,S,T,0\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\nT,06:00:00,06:00:00,A,1,,\nT,06:10:00,06:11:00,B,2,,\nT,06:20:00,06:20:00,C,3,,\n",
    "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nA,Start,49.50,6.10\nB,Middle,49.51,6.11\nC,End,49.52,6.12\n",
}


def test_route_pipeline():
    """The public command writes 605 data that REQreate can configure."""
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        buslines_dir = data_dir / "buslines"
        graphs_dir = data_dir / "graphs"
        requests_dir = data_dir / "requests"
        requests_dir.mkdir()
        route_dir = busline_dir("605", buslines_dir)
        gtfs_path = Path(directory) / "gtfs.zip"
        with zipfile.ZipFile(gtfs_path, "w") as archive:
            for name, content in TABLES.items():
                archive.writestr(name, content)
        subprocess.run([
            sys.executable, str(ROOT / "crawl_busline.py"), "--route", "605",
            "--gtfs-zip", str(gtfs_path), "--service-date", "2026-10-06",
            "--output", str(busline_path("businfo", route_dir)),
            "--stops-output", str(busline_path("stops", route_dir)),
        ], check=True, capture_output=True, text=True)
        default_dir = data_dir / "default/605"
        with patch("src.output_adapters.busline_dir", return_value=default_dir), patch.object(
            sys, "argv", ["crawl_busline.py", "--route", "605",
                          "--gtfs-zip", str(gtfs_path), "--service-date", "2026-10-06"],
        ):
            crawl_gtfs.main()
        assert busline_path("businfo", default_dir).is_file()
        assert busline_path("stops", default_dir).is_file()

        businfo = json.loads(busline_path("businfo", route_dir).read_text())
        stops = json.loads(busline_path("stops", route_dir).read_text())
        assert businfo["route"]["route_short_name"] == "605"
        assert b"Map 605 service area" in render_page("605", buslines_dir=buslines_dir)
        named_page = render_page("test", "605", buslines_dir)
        assert b"Map test service area" in named_page
        assert b'"stop_name": "Start"' in named_page
        assert [stop["class"] for stop in stops] == ["mandatory", "optional", "mandatory"]
        assert businfo["operating_hours"] == {
            "start_seconds": 21600, "end_seconds": 22800,
            "start_minute": 360, "end_minute": 380,
        }
        assert route_schedule.index_route_departures(businfo)[("A", "C")] == [(21600, 22800)]
        with patch.object(generate, "busline_dir", return_value=route_dir):
            cfg = generate.load_config("605")
        assert cfg["busline_name"] == "605"
        assert cfg["places"] == stops
        assert cfg["attributes"]["earliest_departure"]["pdf"][0]["loc"] == 22200

        graph = nx.MultiDiGraph(crs="epsg:4326")
        graph.add_node(1, x=6.10, y=49.50)
        graph.add_node(2, x=6.12, y=49.52)
        graph.add_edge(1, 2, length=100)
        geometry = {"type": "Polygon", "coordinates": [[
            [6.09, 49.49], [6.13, 49.49], [6.13, 49.53], [6.09, 49.49],
        ]]}
        area_dir = graph_dir("550", graphs_dir)
        features = pd.DataFrame({"geometry": [Point(6.12, 49.50)],
                                 "name": ["Cafe"], "amenity": ["cafe"]},
                                index=pd.MultiIndex.from_tuples([("node", 1)]))
        with patch.object(ox, "graph_from_polygon", return_value=graph), patch.object(
            ox, "features_from_polygon", return_value=features
        ):
            save_area(geometry, area_dir)
        poi_path = graph_path("pois", area_dir)
        with patch.object(generate, "available_buslines", return_value=["605", "550"]), patch.object(
            generate, "available_graphs", return_value=["550"]
        ), patch("builtins.input") as prompt, patch.object(
            generate, "busline_dir", return_value=route_dir
        ), patch.object(generate, "graph_dir", return_value=area_dir), patch.object(
            generate, "generate", return_value={"num_data:": 0, "requests": {}}
        ) as sample, patch.object(
            generate, "create_request_dir",
            side_effect=lambda busline_name, graph_name: create_request_dir(
                busline_name, graph_name, requests_dir),
        ), patch.object(sys, "argv", ["generate.py", "--map", "550",
                                       "--busline", "605", "--requests", "2"]):
            generate.main()
            prompt.assert_not_called()
            prompt.return_value = "1"
            sys.argv[:] = ["generate.py", "--map", "550", "--requests", "2"]
            generate.main()
        prompt.assert_called_once_with("Choose busline number: ")
        assert sample.call_args.args[0]["busline_name"] == "605"
        assert sample.call_args.args[1:] == (graph_path("area", area_dir), poi_path)
        instance_dir = requests_dir / "605_550_0001"
        assert request_path("pool", instance_dir).is_file()
        assert request_path("pool", requests_dir / "605_550_0002").is_file()
        meta = json.loads(request_path("metadata", instance_dir).read_text())
        assert (meta["candidate_count"], meta["busline"], meta["graph"]) == (2, "605", "550")
        assert {path.relative_to(instance_dir).as_posix() for path in instance_dir.rglob("*")
                if path.is_file()} == {
            "raw_requests.json", "raw_requests_metadata.json",
        }


def test_generate_demand_command():
    """The public command forwards the requested map and optional busline."""
    with patch.object(sys, "argv", ["main.py", "generate-demand", "--map", "550",
                                   "--busline", "605", "--requests", "2"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    run.assert_called_once_with([
        sys.executable, str(project_main.COMMANDS["generate-demand"]),
        "--map", "550", "--busline", "605", "--requests", "2",
    ], check=True)
    with patch.object(sys, "argv", ["main.py", "generate-demand", "--map", "550"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    run.assert_called_once_with([
        sys.executable, str(project_main.COMMANDS["generate-demand"]), "--map", "550",
    ], check=True)


def test_generate_without_busline():
    """Skipping a busline retains general filters and records disabled bus filters."""
    cfg = generate.load_config(None)
    assert cfg["places"] == []
    assert cfg["parameters"][0]["value"] == 17100
    valid_req = {"reqid": 0, "origin": [0.5, 0.5], "destination": [0.7, 0.7],
                 "direct_distance": 200, "direct_travel_time": 30}
    short_req = valid_req | {"reqid": 1, "direct_distance": 50}
    with patch.object(generate, "build_area_net", return_value=SimpleNamespace(
        polygon=box(0, 0, 1, 1)
    )), patch.object(
        generate, "load_pois", return_value=[[49.5, 6.1]]
    ), patch.object(generate, "set_poi_zones"), patch.object(
        generate, "_generate_single_data_impl", side_effect=[valid_req, short_req]
    ), patch.object(
        generate, "select_scheduled_bus_stops", side_effect=AssertionError("bus stops selected")
    ):
        cfg["requests"] = 2
        pool = generate.generate(cfg, Path("unused"), Path("unused"))
    assert pool == {"num_data:": 1, "requests": {"0": valid_req}}

    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        assert available_buslines(data_dir / "missing_buslines") == []
        area_dir = graph_dir("Esch", data_dir / "graphs")
        area_dir.mkdir(parents=True)
        for name in ("area", "drive_graph", "walk_graph"):
            graph_path(name, area_dir).write_text(name)
        poi_path = graph_path("pois", area_dir)
        write_json(poi_path, {"features": []})
        output = StringIO()
        with patch.object(generate, "available_buslines", return_value=[]), patch.object(
            generate, "available_graphs", return_value=["Esch"]
        ), patch("builtins.input", return_value="0"), patch.object(
            generate, "graph_dir", return_value=area_dir
        ), patch.object(generate, "generate", return_value=pool
        ), patch.object(generate, "create_request_dir",
                        side_effect=lambda busline_name, graph_name: create_request_dir(
                            busline_name, graph_name, data_dir / "requests")), patch.object(
            sys, "argv", ["generate.py", "--map", "Esch", "--requests", "2"]
        ), redirect_stdout(output):
            generate.main()
        assert "No available buslines." in output.getvalue()
        assert "0. Skip" in output.getvalue()
        assert "bus-related filters disabled" in output.getvalue()
        instance_dir = data_dir / "requests/no_bus_Esch_0001"
        meta = json.loads(request_path("metadata", instance_dir).read_text())
        assert meta["busline"] is None
        assert meta["bus_filters_enabled"] is False
        assert all("buslines" not in path for path in meta["inputs_sha256"])
        assert json.loads(request_path("pool", instance_dir).read_text()) == pool


def test_select_area_command():
    """A map name does not have to match the optional busline name."""
    with patch.object(sys, "argv", ["main.py", "select-area", "test", "--busline", "550"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    run.assert_called_once_with([
        sys.executable, str(project_main.COMMANDS["select-area"]),
        "--map", "test", "--busline", "550",
    ], check=True)


if __name__ == "__main__":
    test_route_pipeline()
    test_generate_demand_command()
    test_generate_without_busline()
    test_select_area_command()
