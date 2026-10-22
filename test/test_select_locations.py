"""Check the standalone graph-node location selector and its CSV files."""

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


def test_location_csvs():
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        graph_path("drive_nodes", directory).write_text("osmid,x,y\n1,6.2,49.5\n2,6.21,49.51\n")
        locations = {kind: [] for kind in select_locations.LOCATION_FILES}
        locations["optional_bus_stops"] = ["1", "1"]
        locations["parking_locations"] = ["2"]
        locations["fixed_charging_stations"] = ["1"]
        select_locations.save_locations(directory, locations)
        assert select_locations.read_locations(directory) == {
            "optional_bus_stops": ["1"],
            "parking_locations": ["2"],
            "fixed_charging_stations": ["1"],
        }
        with (directory / "optional_bus_stops.csv").open(newline="") as file:
            assert list(csv.DictReader(file)) == [{"osmid": "1", "x": "6.2", "y": "49.5"}]
        assert select_locations.location_data(directory)["nodes"] == [
            ["1", "49.5", "6.2"], ["2", "49.51", "6.21"]]

        locations["parking_locations"] = ["absent"]
        try:
            select_locations.save_locations(directory, locations)
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted a node outside the saved graph")
        assert select_locations.read_locations(directory)["parking_locations"] == ["2"]

        graph_path("drive_nodes", directory).write_text("osmid,x,y\n2,6.22,49.52\n")
        assert select_locations.location_data(directory)["locations"] == {
            "optional_bus_stops": [], "parking_locations": ["2"],
            "fixed_charging_stations": [],
        }


def test_standalone_endpoints():
    with TemporaryDirectory() as tmp, patch.object(select_locations, "graph_dir", return_value=Path(tmp)):
        graph_path("drive_nodes", Path(tmp)).write_text("osmid,x,y\n1,6.2,49.5\n")
        handler = object.__new__(select_locations.Handler)
        handler.map_name = "test"
        handler.path = "/"
        handler.wfile = BytesIO()
        with patch.object(handler, "send_response") as response, patch.object(
            handler, "send_header"
        ), patch.object(handler, "end_headers"):
            handler.do_GET()
        response.assert_called_once_with(200)
        assert b"Graph locations" in handler.wfile.getvalue()
        assert b"Draw or edit" not in handler.wfile.getvalue()

        locations = {kind: ["1"] for kind in select_locations.LOCATION_FILES}
        for payload, expected in ((locations, 200),
                                  ({**locations, "parking_locations": ["2"]}, 400)):
            body = json.dumps(payload).encode()
            handler.path = "/save"
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            with patch.object(handler, "send_response") as response, patch.object(
                handler, "send_header"
            ), patch.object(handler, "end_headers"):
                handler.do_POST()
            response.assert_called_once_with(expected)
        assert select_locations.read_locations(Path(tmp)) == locations


def test_separate_command():
    with patch.object(sys, "argv", ["main.py", "select-locations", "550"]), patch.object(
        project_main.subprocess, "run"
    ) as run:
        project_main.main()
    command = run.call_args.args[0]
    assert command[1] == str(project_main.COMMANDS["select-locations"])
    assert command[2:] == ["--map", "550"]


if __name__ == "__main__":
    test_location_csvs()
    test_standalone_endpoints()
    test_separate_command()
