"""Write the generated request pool and its configuration snapshot."""

import csv
import json
from pathlib import Path
import tomllib

from src.output_adapters import DAR_OUTPUT_FIELDS, SFBS_OUTPUT_FIELDS, request_path, write_json


ROOT = Path(__file__).resolve().parents[3]
CFG_PATH = ROOT / "src/reqreate/request_gen.toml"
MAPS_CFG_PATH = ROOT / "src/reqreate/maps/map_config.toml"
FILTERS_PATH = ROOT / "src/reqreate/filters/filters.toml"
OPERATIONS_PATH = ROOT / "src/reqreate/operation/operation_profile.toml"
VEHICLES_PATH = ROOT / "src/reqreate/operation/veh_profile.toml"
CHARGING_TRUCKS_PATH = ROOT / "src/reqreate/operation/c_truck_profile.toml"


def write_requests_csv(path, requests, task):
    """Write one request per row, preserving array values as JSON text."""
    base_fields = SFBS_OUTPUT_FIELDS if task == "SFBS" else DAR_OUTPUT_FIELDS
    fields = [*base_fields, *sorted(set().union(*(req.keys() for req in requests.values()))
                                    - set(base_fields))]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for req in requests.values():
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, tuple, dict))
                             else value for key, value in req.items()})
    return path


def write_pool(cfg, busline_name, graph_name, instance_dir, pool):
    """Write the request pool and its settings; return the pool path."""
    config = tomllib.loads(OPERATIONS_PATH.read_text())
    profiles = tomllib.loads(VEHICLES_PATH.read_text())["profiles"]
    charging_truck_profiles = tomllib.loads(CHARGING_TRUCKS_PATH.read_text())["charging_truck_profiles"]
    mode = cfg["task"].lower()
    attributes = config[mode]["attribute"]
    operations = {mode: {
        "average_speed_mps": attributes["vehicle_speed"],
        "vehicle_count": attributes["num_of_vehicles"],
        "vehicle_type": attributes["profile"],
        "temperature_case": attributes["temperature_case"],
        "vehicle": profiles[attributes["profile"]],
        "detour_factor": attributes["detour_factor"],
        "charging_trucks": {
            "count": attributes["num_of_charging_trucks"],
            "type": attributes["charging_truck_profile"],
            "profile": charging_truck_profiles[attributes["charging_truck_profile"]],
        },
    }}
    pool_path = write_json(request_path("pool", instance_dir), pool, compact=True)
    write_requests_csv(request_path("csv", instance_dir), pool["requests"], cfg["task"])
    write_json(request_path("operations", instance_dir), operations)
    parameters_path = request_path("parameters", instance_dir)
    settings = [
        f"task = {json.dumps(cfg['task'])}",
        f"map = {json.dumps(graph_name)}",
        f"busline = {json.dumps(busline_name)}",
        f"effective_seed = {cfg['seed']}",
        f"debug = {str(cfg.get('debug', False)).lower()}",
    ]
    for path in (CFG_PATH, MAPS_CFG_PATH):
        settings.extend(("", f"# {path.relative_to(ROOT)}", path.read_text(encoding="utf-8").rstrip()))
    other_mode = "sfbs" if mode == "dar" else "dar"
    for path in (FILTERS_PATH, OPERATIONS_PATH):
        source = path.read_text(encoding="utf-8")
        start = source.index(f"[{mode}")
        end = source.find(f"[{other_mode}", start)
        section = source[start:end if end != -1 else None].splitlines()
        while section and (not section[-1].strip() or section[-1].lstrip().startswith("#")):
            section.pop()
        settings.extend(("", f"# {path.relative_to(ROOT)}", "\n".join(section)))
    profile_name = attributes["profile"]
    settings.extend(("", f"# {VEHICLES_PATH.relative_to(ROOT)}", f"[profiles.{profile_name}]"))
    for name, value in profiles[profile_name].items():
        if isinstance(value, dict):
            rendered = "{ " + ", ".join(f"{key} = {json.dumps(item)}" for key, item in value.items()) + " }"
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        settings.append(f"{name} = {rendered}")
    charging_truck_name = attributes["charging_truck_profile"]
    settings.extend(("", f"# {CHARGING_TRUCKS_PATH.relative_to(ROOT)}",
                     f"[charging_truck_profiles.{charging_truck_name}]"))
    for name, value in charging_truck_profiles[charging_truck_name].items():
        settings.append(f"{name} = {json.dumps(value, ensure_ascii=False)}")
    parameters_path.write_text("\n".join(settings) + "\n", encoding="utf-8")
    return pool_path
