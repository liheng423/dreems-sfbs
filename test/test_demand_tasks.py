"""Check the required task selector and its downstream configuration."""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/reqreate"))

import main as project_main
from src.reqreate import generate
from filters.filters import BASE_REQUEST_FILTERS, REQUEST_FILTERS


def test_sfbs_saves_stop_endpoints_only():
    request = {"reqid": 1, "origin": [49.5, 6.1], "destination": [49.6, 6.2],
               "originnode_drive": 1, "destinationnode_drive": 2,
               "boarding_stop_id": "A", "alighting_stop_id": "B",
               "direct_distance": 1000}
    with patch.object(generate, "prepare_network"), patch.object(
        generate, "generate_candidates", return_value={"1": request}
    ), patch.object(generate, "filter_requests", side_effect=lambda cfg, net, reqs: reqs):
        saved = generate.generate({"task": "SFBS"}, None, None)["requests"]["1"]
    assert "originnode_drive" not in saved and "destinationnode_drive" not in saved
    assert (saved["boarding_stop_id"], saved["alighting_stop_id"]) == ("A", "B")


def test_demand_tasks():
    for args in (["--map", "Esch"], ["DARP", "--map", "Esch", "--busline", "550"],
                 ["SFBS", "--map", "Esch"]):
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "generate-demand", *args],
                                capture_output=True, text=True)
        assert result.returncode != 0

    with patch.object(sys, "argv", ["main.py", "generate-demand", "SFBS", "--map", "550",
                                    "--busline", "550"]), patch.object(project_main.subprocess, "run") as run:
        project_main.main()
    assert run.call_args.args[0][-5:] == ["SFBS", "--map", "550", "--busline", "550"]

    with TemporaryDirectory() as directory:
        operations = Path(directory) / "operations.toml"
        operations.write_text("[darp.attribute]\nvehicle_speed = 10\ndetour_factor = 1.5\n"
                              "[sfbs.attribute]\nvehicle_speed = 5\ndetour_factor = 2\n")
        filters = Path(directory) / "filters.toml"
        filters.write_text("[darp]\nmax_walking_distance_m = 100\nwalking_speed_mps = 1\n"
                           "[[darp.parameters]]\nname = 'min_distance'\nvalue = 100\n"
                           "[sfbs]\nmax_walking_distance_m = 500\nwalking_speed_mps = 2\n"
                           "[[sfbs.parameters]]\nname = 'min_distance'\nvalue = 500\n")
        with patch.object(generate, "OPERATION_CFG_PATH", operations), patch.object(
            generate, "FILTERS_PATH", filters
        ), patch.object(generate, "busline_dir", return_value=ROOT / "data/buslines/550"):
            darp = generate.load_config("DARP")
            sfbs = generate.load_config("SFBS", "550")
    assert (darp["vehicle_speed_mps"], darp["detour_factor"],
            darp["parameters"][0]["value"], darp["request_filters"]) == (
                10, 1.5, 100, BASE_REQUEST_FILTERS)
    assert (sfbs["vehicle_speed_mps"], sfbs["detour_factor"],
            sfbs["parameters"][0]["value"], sfbs["request_filters"]) == (
                5, 2, 500, REQUEST_FILTERS)
