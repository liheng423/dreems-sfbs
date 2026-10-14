"""Exercise a non-550 route through GTFS, stop places, and demand settings."""

import hashlib
import csv
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
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
        assert b"Map 605 operation and service areas" in render_page("605", buslines_dir=buslines_dir)
        named_page = render_page("test", "605", buslines_dir)
        assert b"Map test operation and service areas" in named_page
        assert b'"stop_name": "Start"' in named_page
        assert [stop["class"] for stop in stops] == ["mandatory", "optional", "mandatory"]
        assert businfo["operating_hours"] == {
            "start_seconds": 21600, "end_seconds": 22800,
            "start_minute": 360, "end_minute": 380,
        }
        assert route_schedule.index_route_departures(businfo)[("A", "C")] == [(21600, 22800)]
        with patch.object(generate, "busline_dir", return_value=route_dir):
            cfg = generate.load_config("SFBS", "605")
        assert cfg["busline_name"] == "605"
        assert cfg["places"] == stops
        assert cfg["simulation_start_s"] == 28800
        assert cfg["simulation_end_s"] == 43200
        assert cfg["requests"] == 100

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
        ), patch.object(
            generate, "busline_dir", return_value=route_dir
        ), patch.object(generate, "graph_dir", return_value=area_dir), patch.object(
            generate, "generate", return_value={"num_data:": 0, "requests": {}}
        ) as sample, patch.object(
            generate, "create_request_dir",
            side_effect=lambda task, graph_name: create_request_dir(
                task, graph_name, requests_dir),
        ), patch.object(sys, "argv", ["generate.py", "SFBS", "--map", "550",
                                       "--busline", "605"]):
            generate.main()
        assert sample.call_args.args[0]["busline_name"] == "605"
        assert sample.call_args.args[1:] == (graph_path("area", area_dir), poi_path)
        instance_dir = requests_dir / "sfbs_550_0001"
        assert request_path("pool", instance_dir).is_file()
        meta = json.loads(request_path("metadata", instance_dir).read_text())
        assert (meta["candidate_count"], meta["busline"], meta["graph"]) == (100, "605", "550")
        assert (meta["mean_candidate_count"], meta["prebooked_probability"]) == (100, 0.5)
        assert meta["dynamic_time_stamp_distribution"] == {
            "type": "poisson", "rate_per_hour": 12.5}
        assert meta["prebooked_earliest_departure_distribution"] == {
            "type": "poisson", "rate_per_hour": 12.5}
        assert (meta["simulation_start_s"], meta["simulation_end_s"],
                meta["demand_start_s"]) == (28800, 43200, cfg["demand_start_s"])
        assert {path.relative_to(instance_dir).as_posix() for path in instance_dir.rglob("*")
                if path.is_file()} == {
            "requests.json", "requests.csv", "operations.json", "requests_metadata.json",
        }
        operations = json.loads(request_path("operations", instance_dir).read_text())
        assert set(operations) == {"sfbs"}
        assert operations["sfbs"]["start_time"] == "7:00:00"
        assert operations["sfbs"]["average_speed_mps"] == 6.111111111111111
        assert operations["sfbs"]["vehicle_count"] == 6
        assert operations["sfbs"]["vehicle_type"] == "evobus_396_nmc_na_hybrid"
        assert operations["sfbs"]["vehicle"]["manufacturer"] == "Evobus eCitaro"
        assert meta["operations_sha256"] == hashlib.sha256(
            request_path("operations", instance_dir).read_bytes()).hexdigest()
        assert list(csv.DictReader(request_path("csv", instance_dir).open(newline=""))) == []
        assert meta["csv_sha256"] == hashlib.sha256(
            request_path("csv", instance_dir).read_bytes()).hexdigest()


def test_generate_demand_command():
    """The public command forwards the required task and its inputs."""
    with patch.object(sys, "argv", ["main.py", "generate-demand", "SFBS", "--map", "550",
                                   "--busline", "605"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    run.assert_called_once_with([
        sys.executable, str(project_main.COMMANDS["generate-demand"]),
        "SFBS", "--map", "550", "--busline", "605",
    ], check=True)
    with patch.object(sys, "argv", ["main.py", "generate-demand", "DARP", "--map", "550"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    run.assert_called_once_with([
        sys.executable, str(project_main.COMMANDS["generate-demand"]), "DARP", "--map", "550",
    ], check=True)
    with patch.object(sys, "argv", ["main.py", "generate-demand", "DARP", "--map", "550", "--debug"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    run.assert_called_once_with([
        sys.executable, str(project_main.COMMANDS["generate-demand"]),
        "DARP", "--map", "550", "--debug",
    ], check=True)


def test_generator_seed_override():
    cfg = {"task": "DARP", "seed": 42}
    with patch.object(generate, "available_graphs", return_value=["Esch"]), patch.object(
        generate, "load_config", return_value=cfg
    ), patch.object(generate, "graph_dir", return_value=Path("unused")), patch.object(
        generate, "generate", return_value={"requests": {}}
    ) as sample, patch.object(generate, "create_request_dir", return_value=Path("unused")), patch.object(
        generate, "write_pool", return_value=Path("unused/requests.json")
    ), patch.object(sys, "argv", ["generate.py", "DARP", "--map", "Esch", "--seed", "43"]):
        generate.main()
    assert sample.call_args.args[0]["seed"] == 43


def test_debug_lead_time_fields():
    """Normal output keeps downstream fields; debug exposes REQreate internals."""
    def candidates(*_):
        return {"0": {"is_prebooked": 0, "lt_dynamic": 300,
                      "lt_prebooked": 36000, "lead_time": 300,
                      "pickup_from": 300, "pickup_to": 1200,
                      "dropoff_from": 900, "dropoff_to": 1800, "service_time": 30,
                      "origin": [49.5, 6.1], "originnode_drive": 1,
                      "originx": 6.1, "originzone": 2,
                      "originnode_walk": 3, "seed_location": 42,
                      "origin_drive_point": [49.5, 6.1],
                      "boarding_stop_id": "A"}}

    net = SimpleNamespace(G_drive=SimpleNamespace(nodes={1: {"x": 6.1, "y": 49.5}}))
    with patch.object(generate, "prepare_network", return_value=net), patch.object(
        generate, "generate_candidates", side_effect=candidates
    ), patch.object(generate, "filter_requests", side_effect=lambda _, __, reqs: reqs):
        with patch.object(generate, "DEBUG", False):
            ordinary = generate.generate({"task": "DARP"}, Path("unused"), Path("unused"))["requests"]["0"]
        with patch.object(generate, "DEBUG", True):
            debug = generate.generate({"task": "DARP"}, Path("unused"), Path("unused"))["requests"]["0"]
    assert ordinary == {"is_prebooked": 0, "lead_time": 300,
                        "pickup_from": 300, "pickup_to": 1200,
                        "dropoff_from": 900, "dropoff_to": 1800, "service_time": 30,
                        "origin": [49.5, 6.1], "originnode_drive": 1,
                        "origin_drive_point": [49.5, 6.1],
                        "boarding_stop_id": "A"}
    assert debug == candidates()["0"]


def test_generated_request_energy_uses_driving_distance_and_selected_vehicle():
    """Energy follows the TOML vehicle rate and excludes walking distance."""
    req = {"reqid": 0, "direct_distance": 1000, "boarding_walk_distance_m": 400,
           "alighting_walk_distance_m": 300}
    with TemporaryDirectory() as directory:
        operation_path = Path(directory) / "operation.toml"
        operation_path.write_text('[darp.attribute]\nprofile = "bus"\ntemperature_case = "at_9_c"\n'
                                  '[sfbs.attribute]\nprofile = "semi_flex_bus"\n'
                                  'temperature_case = "reference_20_22_c"\n')
        vehicle_path = Path(directory) / "vehicles.toml"
        vehicle_path.write_text('[profiles.bus]\nreference_kwh_per_km = 0.8\n'
                                'relative_increase_pct = { at_9_c = 25 }\n'
                                '[profiles.semi_flex_bus]\nreference_kwh_per_km = 2.0\n')
        with patch.object(generate, "prepare_network"), patch.object(
            generate, "generate_candidates", return_value={"0": req}
        ), patch.object(generate, "filter_requests", side_effect=lambda _, __, requests: requests), patch.object(
            generate, "OPERATION_CFG_PATH", operation_path
        ), patch.object(generate, "VEHICLE_CFG_PATH", vehicle_path):
            pool = generate.generate({"task": "DARP"}, Path("unused"), Path("unused"))
    assert pool["requests"]["0"]["energy_kwh"] == 1.0


def test_generate_without_busline():
    """Skipping a busline retains general filters and records disabled bus filters."""
    cfg = generate.load_config("DARP")
    assert cfg["places"] == []
    assert next(param["value"] for param in cfg["parameters"]
                if param["name"] == "min_distance") == 100
    assert cfg["simulation_end_s"] == 43200
    drive = nx.DiGraph()
    drive.add_node(1, x=0.51, y=0.52)
    drive.add_node(2, x=0.71, y=0.72)
    valid_req = {"reqid": 0, "origin": [0.5, 0.5], "destination": [0.7, 0.7],
                 "originnode_drive": 1, "destinationnode_drive": 2,
                 "direct_distance": 200, "direct_travel_time": 30,
                 "is_prebooked": 0, "lead_time": 0}
    short_req = valid_req | {"reqid": 1, "direct_distance": 50,
                             "is_prebooked": 1, "lead_time": 36000}
    with patch.object(generate, "build_area_net", return_value=SimpleNamespace(
        polygon=box(0, 0, 1, 1), G_drive=drive
    )), patch.object(
        generate, "load_pois", return_value=[[49.5, 6.1]]
    ), patch.object(generate, "set_poi_zones"), patch.object(
        generate, "sample_arrivals", return_value=([False, True], [30000, 30000])
    ), patch.object(
        generate, "_generate_single_data_impl", side_effect=[valid_req, short_req]
    ), patch.object(
        generate, "select_scheduled_bus_stops", side_effect=AssertionError("bus stops selected")
    ):
        cfg["requests"] = 2
        pool = generate.generate(cfg, Path("unused"), Path("unused"))
    assert pool == {"num_data:": 1, "requests": {"0": valid_req}}
    assert "origin_drive_point" not in valid_req
    assert "destination_drive_point" not in valid_req

    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        assert available_buslines(data_dir / "missing_buslines") == []
        area_dir = graph_dir("Esch", data_dir / "graphs")
        area_dir.mkdir(parents=True)
        for name in ("area", "drive_graph", "walk_graph"):
            graph_path(name, area_dir).write_text(name)
        poi_path = graph_path("pois", area_dir)
        write_json(poi_path, {"features": []})
        write_json(graph_path("depot", area_dir), {"original_point": [49.5, 6.1]})
        output = StringIO()
        with patch.object(generate, "available_buslines", return_value=[]), patch.object(
            generate, "available_graphs", return_value=["Esch"]
        ), patch.object(
            generate, "graph_dir", return_value=area_dir
        ), patch.object(generate, "generate", return_value=pool
        ), patch.object(generate, "create_request_dir",
                        side_effect=lambda task, graph_name: create_request_dir(
                            task, graph_name, data_dir / "requests")), patch.object(
            sys, "argv", ["generate.py", "DARP", "--map", "Esch"]
        ), redirect_stdout(output):
            generate.main()
        instance_dir = data_dir / "requests/darp_Esch_0001"
        meta = json.loads(request_path("metadata", instance_dir).read_text())
        assert meta["busline"] is None
        assert meta["bus_filters_enabled"] is False
        assert all("buslines" not in path for path in meta["inputs_sha256"])
        assert json.loads(request_path("pool", instance_dir).read_text()) == pool
        with request_path("csv", instance_dir).open(newline="") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 1
        assert rows[0]["reqid"] == "0"
        assert json.loads(rows[0]["origin"]) == valid_req["origin"]
        assert rows[0]["direct_distance"] == str(valid_req["direct_distance"])
        assert "boarding_stop_id" not in rows[0]
        assert request_path("operations", instance_dir).is_file()
        assert set(json.loads(request_path("operations", instance_dir).read_text())) == {"darp"}


def test_generate_with_busline_saves_stop_points():
    cfg = {
        "requests": 1, "seed": 42, "busline_name": "550",
        "places": json.loads(busline_path("stops", busline_dir("550")).read_text()),
        "max_walking_distance_m": 1000, "simulation_end_s": 43200,
        "distributions": {"radial_direction": {"type": "uniform", "loc": 0, "scale": 360},
                          "radial_distance": {"type": "uniform", "loc": 500, "scale": 0}},
        "attributes": {"origin": {}, "destination": {}, "time_stamp": {}},
        "parameters": [], "method_pois": {"rows": 1, "columns": 1},
    }
    drive = nx.DiGraph()
    drive.add_node(1, x=6.1, y=49.5)
    drive.add_node(2, x=6.2, y=49.6)
    stops = cfg["places"][:2]
    req = {"reqid": 0, "originnode_drive": 1, "destinationnode_drive": 2,
           "latest_arrival": cfg["simulation_end_s"]}
    selection = {"boarding_stop_id": stops[0]["name"].removeprefix("Stop_"),
                 "alighting_stop_id": stops[1]["name"].removeprefix("Stop_")}
    with patch.object(generate, "build_area_net", return_value=SimpleNamespace(
        G_drive=drive
    )), patch.object(generate, "index_route_departures", return_value={}), patch.object(
        generate, "load_pois", return_value=[]
    ), patch.object(generate, "set_poi_zones"), patch.object(
        generate, "passes_filters", return_value=True
    ), patch.object(generate, "_generate_single_data_impl", return_value=req), patch.object(
        generate, "select_scheduled_bus_stops", return_value=selection
    ):
        pool = generate.generate(cfg, Path("unused"), Path("unused"))
    saved = pool["requests"]["0"]
    assert saved["origin_drive_point"] == [49.5, 6.1]
    assert saved["destination_drive_point"] == [49.6, 6.2]
    assert saved["boarding_stop_point"] == [stops[0]["lat"], stops[0]["lon"]]
    assert saved["alighting_stop_point"] == [stops[1]["lat"], stops[1]["lon"]]


def test_demand_time_window():
    """Departure times stay in one day; request appearance may be earlier."""
    assert generate.clock_seconds("07:30") == 27000
    assert generate.clock_seconds("23:59:59") == 86399
    defaults = generate.load_config("DARP")
    assert defaults["attributes"]["lt_prebooked"]["pdf"] == [
        defaults["distributions"]["lt_prebooked"]]
    for value in ("24:00", "12:60", "7:30", "12:00:60", "12"):
        try:
            generate.clock_seconds(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid clock time {value}")
    source = generate.CFG_PATH.read_text()
    with TemporaryDirectory() as directory:
        cfg_path = Path(directory) / "request_gen.toml"
        for start, end, demand in (("01:00", "01:00", "01:00"),
                                   ("02:00", "01:00", "02:00"),
                                   ("01:00", "02:00", "00:50"),
                                   ("01:00", "02:00", "02:00")):
            changed = source.replace('start = "08:00:00"', f'start = "{start}"')
            changed = changed.replace('end = "12:00:00"', f'end = "{end}"')
            cfg_path.write_text(re.sub(r'^demand_start = .*$', f'demand_start = "{demand}"',
                                       changed, count=1, flags=re.MULTILINE))
            with patch.object(generate, "CFG_PATH", cfg_path):
                try:
                    generate.load_config("DARP")
                except ValueError:
                    pass
                else:
                    raise AssertionError("accepted invalid time window")
        changed = source.replace('start = "08:00:00"', 'start = "01:00"')
        changed = changed.replace('end = "12:00:00"', 'end = "02:00"')
        cfg_path.write_text(re.sub(r'^demand_start = .*$', 'demand_start = "01:30"',
                                   changed, count=1, flags=re.MULTILINE))
        with patch.object(generate, "CFG_PATH", cfg_path):
            cfg = generate.load_config("DARP")
    assert (cfg["demand_start_s"], cfg["simulation_end_s"]) == (5400, 7200)
    cfg["requests"] = 3
    drive = nx.DiGraph()
    drive.add_node(1, x=0.51, y=0.52)
    drive.add_node(2, x=0.71, y=0.72)
    early = {"reqid": 0, "origin": [0.5, 0.5], "destination": [0.7, 0.7],
             "originnode_drive": 1, "destinationnode_drive": 2,
             "direct_distance": 200, "direct_travel_time": 30, "time_stamp": -3600,
             "latest_arrival": 7100}
    on_time = early | {"reqid": 1, "time_stamp": 3000}
    late_arrival = on_time | {"reqid": 2, "latest_arrival": 7201}
    with patch.object(generate, "build_area_net", return_value=SimpleNamespace(
        polygon=box(0, 0, 1, 1), G_drive=drive
    )), patch.object(generate, "load_pois", return_value=[]), patch.object(
        generate, "set_poi_zones"
    ), patch.object(
        generate, "sample_arrivals", return_value=([True, False, False], [6000, 6000, 7000])
    ), patch.object(generate, "_generate_single_data_impl",
                    side_effect=[early, on_time, late_arrival]):
        pool = generate.generate(cfg, Path("unused"), Path("unused"))
    assert pool["requests"] == {"0": early, "1": on_time}
    assert all(req["origin_drive_point"] == [0.52, 0.51]
               for req in pool["requests"].values())


def test_request_distributions_from_toml():
    """Changing TOML lead times and arrival rates changes sampling settings."""
    source = generate.CFG_PATH.read_text()
    source = re.sub(r'^lt_dynamic = .*$',
                    'lt_dynamic = { type = "uniform", loc = 60, scale = 120 }',
                    source, count=1, flags=re.MULTILINE)
    source = re.sub(r'^dynamic_time_stamp = .*$',
                    'dynamic_time_stamp = { type = "poisson", rate_per_hour = 10 }',
                    source, count=1, flags=re.MULTILINE)
    with TemporaryDirectory() as directory:
        cfg_path = Path(directory) / "request_gen.toml"
        cfg_path.write_text(source)
        with patch.object(generate, "CFG_PATH", cfg_path):
            cfg = generate.load_config("DARP")
    assert cfg["attributes"]["lt_dynamic"]["pdf"] == [
        {"type": "uniform", "loc": 60, "scale": 120}]
    assert cfg["distributions"]["dynamic_time_stamp"] == {
        "type": "poisson", "rate_per_hour": 10}
    assert cfg["requests"] == 90


def test_event_time_distribution_requires_poisson():
    source = generate.CFG_PATH.read_text()
    source = re.sub(r'^dynamic_time_stamp = .*$',
                    'dynamic_time_stamp = { type = "uniform", rate_per_hour = 10 }',
                    source, count=1, flags=re.MULTILINE)
    with TemporaryDirectory() as directory:
        cfg_path = Path(directory) / "request_gen.toml"
        cfg_path.write_text(source)
        with patch.object(generate, "CFG_PATH", cfg_path):
            try:
                generate.load_config("DARP")
            except ValueError as exc:
                assert "event-time distribution must be poisson" in str(exc)
            else:
                raise AssertionError("Unsupported event-time distribution was accepted")


def test_poisson_arrival_windows():
    """Each Poisson event stream has a variable count and ordered times."""
    cfg = generate.load_config("DARP")
    flags, times = generate.sample_arrivals(cfg)
    dynamic = [int(time) for flag, time in zip(flags, times) if not flag]
    prebooked = [int(time) for flag, time in zip(flags, times) if flag]
    assert dynamic == sorted(dynamic)
    assert prebooked == sorted(prebooked)
    assert all(cfg["simulation_start_s"] <= time < cfg["simulation_end_s"] for time in dynamic)
    assert all(cfg["demand_start_s"] <= time < cfg["simulation_end_s"] for time in prebooked)
    assert 30 < len(dynamic) < 70 and 30 < len(prebooked) < 70
    cfg["distributions"]["dynamic_time_stamp"]["rate_per_hour"] = 0
    cfg["distributions"]["prebooked_earliest_departure"]["rate_per_hour"] = 0
    assert len(generate.sample_arrivals(cfg)[0]) == 0


def test_retry_if_filtered_keeps_sampled_request_count():
    cfg = generate.load_config("DARP")
    cfg["retry_if_filtered"] = True
    def request(reqid):
        return {"reqid": reqid, "is_prebooked": 0, "lead_time": 300,
                "direct_travel_time": 30}

    with patch.object(generate, "sample_arrivals", return_value=([False, False], [43199, 31000])), patch.object(
        generate, "_generate_single_data_impl", side_effect=[request(0), request(0), request(1)]
    ), patch.object(generate.np.random, "uniform", return_value=30000), patch.object(
        generate, "passes_filters", return_value=True
    ):
        requests = generate.generate_candidates(cfg, SimpleNamespace())
    assert list(requests) == ["0", "1"]
    assert requests["0"]["time_stamp"] == 30000
    assert cfg["generated_candidate_count"] == 3


def test_distance_distribution_from_request_config():
    """The demand distance sampler uses the distribution from request_gen.toml."""
    source = generate.CFG_PATH.read_text()
    source = re.sub(r'^radial_distance = .*$',
                    'radial_distance = { type = "normal", loc = 900, scale = 100 }',
                    source, count=1, flags=re.MULTILINE)
    with TemporaryDirectory() as directory:
        cfg_path = Path(directory) / "request_gen.toml"
        cfg_path.write_text(source)
        with patch.object(generate, "CFG_PATH", cfg_path):
            cfg = generate.load_config("DARP")
    assert cfg["distributions"]["radial_distance"] == {
        "type": "normal", "loc": 900, "scale": 100}
    assert "pdf" not in cfg["method_pois"]
    cfg["requests"] = 1
    req = {"time_stamp": 0, "latest_arrival": 18000,
           "originnode_drive": 1, "destinationnode_drive": 2}
    drive = nx.DiGraph()
    drive.add_node(1, x=6.1, y=49.5)
    drive.add_node(2, x=6.2, y=49.6)
    with patch.object(generate, "build_area_net", return_value=SimpleNamespace(G_drive=drive)), patch.object(
        generate, "load_pois", return_value=[]
    ), patch.object(generate, "set_poi_zones"), patch.object(
        generate, "passes_filters", return_value=True
    ), patch.object(generate.norm, "rvs", return_value=950) as sample_distance, patch.object(
        generate.uniform, "rvs", side_effect=AssertionError("uniform distance sampled")
    ), patch.object(
        generate, "sample_arrivals", return_value=([False], [30000])
    ), patch.object(generate, "_generate_single_data_impl", return_value=req) as sample_request:
        pool = generate.generate(cfg, Path("unused"), Path("unused"))
    sample_distance.assert_called_once_with(loc=900, scale=100)
    assert sample_request.call_args.args[6:12] == (950, "origin", "destination",
                                                    "normal", 900, 100)
    assert pool["requests"] == {"0": req}
    assert req["origin_drive_point"] == [49.5, 6.1]


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
    test_generate_with_busline_saves_stop_points()
    test_demand_time_window()
    test_request_distributions_from_toml()
    test_event_time_distribution_requires_poisson()
    test_poisson_arrival_windows()
    test_distance_distribution_from_request_config()
    test_select_area_command()
