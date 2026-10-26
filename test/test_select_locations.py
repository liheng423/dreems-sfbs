"""Check route-stop editing and graph location selections."""

import csv
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as project_main
from src.locations import select_locations
from src.output_adapters import graph_path


def fixture(root):
    graph = root / "graphs" / "550"
    route = root / "buslines" / "550"
    graph.mkdir(parents=True)
    route.mkdir(parents=True)
    graph_path("drive_nodes", graph).write_text("osmid,x,y\n1,6.2,49.5\n2,6.21,49.51\n")
    (route / "buslines.json").write_text(json.dumps({"stops": [
        {"stop_id": "A", "stop_name": "Alpha", "stop_lon": 6.0, "stop_lat": 49.4},
        {"stop_id": "B", "stop_name": "Beta", "stop_lon": 6.1, "stop_lat": 49.45},
    ], "patterns": [{"pattern_id": "out", "label": "Alpha to Beta",
                     "stop_ids": ["A", "B"], "terminal_stop_ids": ["A", "B"],
                     "trips": [{"stop_times": [{"stop_id": "A"}, {"stop_id": "B"}]}]}]}))
    (route / "stops.json").write_text(json.dumps([
        {"name": "Stop_A", "type": "location", "class": "mandatory", "lon": 6.0, "lat": 49.4},
        {"name": "Stop_B", "type": "location", "class": "optional", "lon": 6.1, "lat": 49.45},
    ]))
    return graph, route


def test_edit_stops_and_locations():
    with TemporaryDirectory() as tmp:
        graph, route = fixture(Path(tmp))
        (graph / "optional_bus_stops.csv").write_text("osmid,x,y\n2,6.21,49.51\n")
        data = select_locations.location_data(graph, route)
        assert data["stops"][0]["label"] == "Alpha"
        assert data["stops"][-1]["name"] == "Stop_OSM_2"
        locations = {"parking_locations": ["1"], "fixed_charging_stations": ["2"]}
        classes = {"Stop_A": "optional", "Stop_B": "mandatory",
                   "Stop_OSM_1": "mandatory", "Stop_OSM_2": "optional"}
        select_locations.save_locations(graph, locations, route, classes)
        stops = json.loads((route / "stops.json").read_text())
        assert [(stop["name"], stop["class"]) for stop in stops] == list(classes.items())
        assert stops[2]["lon"] == 6.2 and stops[2]["lat"] == 49.5
        assert not (graph / "optional_bus_stops.csv").exists()
        with (graph / "parking_locations.csv").open(newline="") as file:
            assert list(csv.DictReader(file)) == [{"osmid": "1", "x": "6.2", "y": "49.5"}]
        select_locations.save_locations(graph, locations, route,
                                       {name: kind for name, kind in classes.items()
                                        if name != "Stop_OSM_2"})
        assert "Stop_OSM_2" not in {stop["name"] for stop in json.loads((route / "stops.json").read_text())}
        before = (route / "stops.json").read_bytes()
        for invalid in ({"Stop_fake": "mandatory"}, {"Stop_OSM_9": "optional"},
                        {"Stop_A": "invalid"}):
            try:
                select_locations.save_locations(graph, locations, route, invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted an invalid stop selection")
        assert (route / "stops.json").read_bytes() == before


def test_standalone_endpoints():
    with TemporaryDirectory() as tmp:
        graph, route = fixture(Path(tmp))
        with patch.object(select_locations, "graph_dir", return_value=graph), patch.object(
            select_locations, "busline_dir", return_value=route
        ):
            handler = object.__new__(select_locations.Handler)
            handler.map_name = handler.busline_name = "550"
            handler.path = "/data"
            handler.wfile = BytesIO()
            with patch.object(handler, "send_response") as response, patch.object(
                handler, "send_header"
            ), patch.object(handler, "end_headers"):
                handler.do_GET()
            response.assert_called_once_with(200)
            assert json.loads(handler.wfile.getvalue())["stops"][0]["name"] == "Stop_A"

            body = json.dumps({"locations": {"parking_locations": ["1"],
                                             "fixed_charging_stations": []},
                               "location_details": {"parking_locations": [
                                   {"osmid": "1", "x": "6.9", "y": "49.9"}]},
                               "stop_classes": {"Stop_A": "optional"}}).encode()
            handler.path = "/save"
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            with patch.object(handler, "send_response") as response, patch.object(
                handler, "send_header"
            ), patch.object(handler, "end_headers"):
                handler.do_POST()
            response.assert_called_once_with(200)
            assert json.loads((route / "stops.json").read_text())[0]["class"] == "optional"
            with (graph / "parking_locations.csv").open(newline="") as file:
                assert list(csv.DictReader(file)) == [{"osmid": "1", "x": "6.2", "y": "49.5"}]


def test_edit_stop_metadata_and_bus_sequence():
    with TemporaryDirectory() as tmp:
        graph, route = fixture(Path(tmp))
        data = select_locations.location_data(graph, route)
        assert data["patterns"][0]["stop_ids"] == ["A", "B"]
        stops = data["stops"]
        stops[0]["class"] = "optional"
        stops[0]["gtfs"]["stop_name"] = "First stop"
        stops.append({"name": "Stop_OSM_1", "original_name": "Stop_OSM_1",
                      "type": "location", "class": "mandatory", "lon": 6.2, "lat": 49.5,
                      "gtfs": None})
        patterns = [{"pattern_id": "out", "stop_ids": ["B", "OSM_1", "A"]}]
        locations = {"parking_locations": ["1"], "fixed_charging_stations": ["2"]}
        select_locations.save_locations(graph, locations, route, stops_data=stops,
                                        patterns_data=patterns)
        saved_stops = json.loads((route / "stops.json").read_text())
        assert saved_stops[0] == {"name": "Stop_A", "type": "location", "class": "optional",
                                  "lon": 6.0, "lat": 49.4}
        businfo = json.loads((route / "buslines.json").read_text())
        assert businfo["stops"][0]["stop_name"] == "First stop"
        assert businfo["patterns"][0]["stop_ids"] == ["A", "B"]
        assert businfo["patterns"][0]["selected_stop_ids"] == ["B", "OSM_1", "A"]
        assert businfo["patterns"][0]["trips"][0]["stop_times"][0]["stop_id"] == "A"
        with (graph / "parking_locations.csv").open(newline="") as file:
            assert list(csv.DictReader(file))[0] == {"osmid": "1", "x": "6.2", "y": "49.5"}
        before = (route / "buslines.json").read_bytes()
        try:
            select_locations.save_locations(graph, locations, route, stops_data=stops,
                                            patterns_data=[{"pattern_id": "out", "stop_ids": ["missing", "B"]}])
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted an invalid sequence")
        assert (route / "buslines.json").read_bytes() == before


def test_reject_changed_stop_identity_or_coordinates():
    with TemporaryDirectory() as tmp:
        graph, route = fixture(Path(tmp))
        data = select_locations.location_data(graph, route)
        data["stops"].append({"name": "Stop_OSM_1", "original_name": "Stop_OSM_1",
                              "type": "location", "class": "optional", "lon": 6.2,
                              "lat": 49.5, "gtfs": None})
        locations = {"parking_locations": ["1"], "fixed_charging_stations": []}
        before = (route / "stops.json").read_bytes()
        changes = [
            (0, "name", "Stop_changed"),
            (0, "lon", 6.3),
            (0, "lat", 49.6),
            (0, "gtfs", {**data["stops"][0]["gtfs"], "stop_lon": 6.3}),
            (2, "lon", 6.3),
        ]
        for index, field, value in changes:
            stops = json.loads(json.dumps(data["stops"]))
            stops[index][field] = value
            try:
                select_locations.save_locations(graph, locations, route, stops_data=stops,
                                                patterns_data=data["patterns"])
            except ValueError:
                pass
            else:
                raise AssertionError(f"Accepted changed stop {field}")
            assert (route / "stops.json").read_bytes() == before


def test_graph_stop_uses_current_node_coordinates():
    with TemporaryDirectory() as tmp:
        graph, route = fixture(Path(tmp))
        saved = json.loads((route / "stops.json").read_text())
        saved.append({"name": "Stop_OSM_1", "type": "location", "class": "optional",
                      "lon": 6.0, "lat": 49.0})
        (route / "stops.json").write_text(json.dumps(saved))
        data = select_locations.location_data(graph, route)
        assert (data["stops"][-1]["lon"], data["stops"][-1]["lat"]) == (6.2, 49.5)
        select_locations.save_locations(graph, {kind: [] for kind in select_locations.LOCATION_FILES},
                                        route, stops_data=data["stops"], patterns_data=data["patterns"])
        assert json.loads((route / "stops.json").read_text())[-1]["lon"] == 6.2


def test_command_passes_busline():
    with patch.object(sys, "argv", ["main.py", "select-locations", "550", "--busline", "605"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    command = run.call_args.args[0]
    assert command[1] == str(project_main.COMMANDS["select-locations"])
    assert command[2:] == ["--map", "550", "--busline", "605"]


def test_map_without_route():
    with TemporaryDirectory() as tmp:
        graph, _ = fixture(Path(tmp))
        with patch.object(sys, "argv", ["select_locations.py", "--map", "my_area"]), patch.object(
            select_locations, "graph_dir", return_value=graph
        ), patch.object(select_locations, "ThreadingHTTPServer"), patch.object(
            select_locations.webbrowser, "open"
        ):
            select_locations.main()
        assert select_locations.Handler.busline_name == ""


if __name__ == "__main__":
    test_edit_stops_and_locations()
    test_standalone_endpoints()
    test_edit_stop_metadata_and_bus_sequence()
    test_reject_changed_stop_identity_or_coordinates()
    test_graph_stop_uses_current_node_coordinates()
    test_command_passes_busline()
    test_map_without_route()
