"""Check the CSV view of generated request values."""

import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.reqreate.adapters.pool_output import write_pool, write_requests_csv


def test_output_csv():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "requests.csv"
        write_requests_csv(path, {}, "DARP")
        with path.open(newline="") as file:
            assert list(csv.DictReader(file)) == []
        requests = {"7": {"reqid": 7, "origin": (49.5, 6.1),
                          "destination": [49.6, 6.2], "direct_distance": 123.4,
                          "lt_dynamic": 60}}
        write_requests_csv(path, requests, "DARP")
        with path.open(newline="") as file:
            row = next(csv.DictReader(file))
        assert row["reqid"] == "7"
        assert json.loads(row["origin"]) == list(requests["7"]["origin"])
        assert row["direct_distance"] == "123.4"
        assert row["lt_dynamic"] == "60"
        assert "boarding_stop_id" not in row
        write_requests_csv(path, {"8": {"reqid": 8, "boarding_stop_id": "001"}}, "SFBS")
        with path.open(newline="") as file:
            row = next(csv.DictReader(file))
        assert row["boarding_stop_id"] == "001"
        assert "originnode_drive" not in row


def test_operation_profiles():
    for task in ("DARP", "SFBS"):
        with TemporaryDirectory() as directory:
            write_pool({"task": task, "seed": 42}, None, "Esch", Path(directory),
                       {"num_data:": 0, "requests": {}})
            instance = Path(directory)
            parameters = (instance / "parameters.txt").read_text()
            assert f"[{task.lower()}.attribute]" in parameters
            assert f"[{'sfbs' if task == 'DARP' else 'darp'}" not in parameters
            assert parameters.count("[profiles.") == 1
            assert "[charging_truck_profiles.dummy_mobile_charger]" in parameters
            operations = json.loads((instance / "operations.json").read_text())
            trucks = operations[task.lower()]["charging_trucks"]
            assert trucks == {
                "count": 1,
                "type": "dummy_mobile_charger",
                "profile": {
                    "traction_battery_capacity_kwh": 100,
                    "charging_battery_capacity_kwh": 200,
                    "charging_power_kw": 50,
                    "reference_kwh_per_km": 0.8,
                },
            }


if __name__ == "__main__":
    test_output_csv()
    test_operation_profiles()
