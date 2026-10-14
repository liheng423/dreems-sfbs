# DREEMS-SFBS

## Overview

Generate **synthetic** passenger requests for a chosen area and. Draw its service area on an OSM map, then generate either Semi-Flex Bus (**SFBS**) requests constrained by bus stops and timetables or Dial-and-Ride (**DAR**) requests without a bus route.

This repo consists of the following features: 
- Select area of interest anywhere in the world to retrieve driving graph and Points of Interest (POIs).
- Automatic synthetic demand generation based on POIs and REQreate.
- Parameters fully tunable.
- Both simple visualization and interactive visualization available for debugging and demonstration.
- **Generate Realistic Graph and Synthetic Requests Data** that are **Ready to use** for downstream optimization algorithms.  

## Input and Output Data

### Inputs
- [SFBS ONLY] Bus stop and schedule information (See ...file).
- Select an area of interest with embedded area selector (See Quick start)
- Parameters to set up the generation algorithm. 

### Outputs
- Driving and walking graph data in `.graphml` and `.csv` formats.
- 



## Quick start

Use Python 3.12 and `uv` from the repository root:

```bash
uv pip install --python python -r requirements.txt
python check_dependencies.py
python crawl_busline.py --route 550
python main.py select-area 550 --busline 550
python main.py generate-demand SFBS --map 550 --busline 550
python main.py visualize
```

Route 550 uses the crawler's default Luxembourg GTFS feed and service date. In the `select-area` browser page, draw the operation area, adjust the service area inside it, and click **Save** before generating demand. For another route, including one in Belgium, replace the feed, date, route, and map name:

```bash
python crawl_busline.py --gtfs-zip path/to/feed.zip --service-date YYYY-MM-DD --route ROUTE
python main.py select-area MAP --busline ROUTE
python main.py generate-demand SFBS --map MAP --busline ROUTE
```

Use `--route-id ID` if the GTFS feed has multiple routes with the same short name. For demand without a bus timetable, run `python main.py generate-demand DARP --map MAP`. Add `--times N` to generate N instances. Results go to `outputs/requests/`; the viewer opens them with the saved map and busline data. Area selection needs OSM access. The published `reqreate==0.1.1` may fail with NumPy 2.x during generation; see the bundled [patch](src/reqreate/instance_generator.patch).

## How requests are calculated

- Set `simulation.start`, `demand_start`, `end`, arrival rates, lead times, and stop windows in [request_gen.toml](src/reqreate/request_gen.toml). Clock settings use `HH:MM[:SS]`; generated request times use seconds from the service day's midnight. The current simulation runs 08:00–12:00.
- Dynamic and prebooked candidate counts are independent Poisson draws: `rate_per_hour × window_hours` gives each expected count. Dynamic requests sample an appearance time between `start` and `end`, then add lead time for `earliest_departure`. Prebooked requests sample `earliest_departure` between `demand_start` and `end`, then subtract lead time for appearance; a negative appearance time means the previous day.
- REQreate samples origins and destinations within the saved service area using OSM POIs, configured distance and direction, and the road graph. `direct_distance` is the shortest directed driving path; `direct_travel_time = int(direct_distance / vehicle_speed)`, with speed from [operation_profile.toml](src/reqreate/operation/operation_profile.toml).
- `pickup_from = earliest_departure`; `pickup_to = pickup_from + pickup_window`. `dropoff_to = pickup_to + ceil(direct_travel_time × detour_factor) + service_time`; `dropoff_from = dropoff_to - dropoff_window`. `latest_arrival = dropoff_to`. Requests finishing after `end` are rejected.
- Both tasks require valid area, minimum road distance, and positive travel time. SFBS also requires reachable stops and a scheduled trip that fits the passenger's time limits. Rejected candidates are resampled when `retry_if_filtered = true`. See [output field definitions](#request-fields) for the full field list and units.

## Project structure

| Path | Purpose |
| --- | --- |
| `crawl_busline.py`, `src/crawler/` | Read GTFS; save routes, stops, service areas, OSM graphs, and POIs. |
| `main.py`, `src/reqreate/` | Run demand generation, filters, and calculations; configure them in `*.toml`. |
| `data/buslines/` | Saved GTFS route data. |
| `outputs/graphs/`, `outputs/requests/` | Saved maps and generated request JSON/CSV with metadata. |
| `interactive_visualizer/` | Browser viewer for generated results. |

## Saved road graphs

Each `outputs/graphs/<map>/` folder contains the selected `service_area.geojson`, `pois.json`, `depot.json`, and two road networks. `drive.graphml` and `walk.graphml` are the complete OSMnx graphs used by demand generation. The matching `drive_nodes.csv`, `drive_edges.csv`, `walk_nodes.csv`, and `walk_edges.csv` are tables of those same graphs for spreadsheet or data-frame use. The graphs cover the selected operation area; the GeoJSON boundary is the service area.

Saving a map with `python main.py select-area <map>` writes the GraphML and CSV files together. Saving the same map again regenerates all four CSVs alongside the new GraphML files.

Both formats use the original OSM node IDs: a nodes CSV `osmid` matches its GraphML node ID and the `u` and `v` endpoints in the corresponding edges CSV.

Each nodes CSV has one row per graph node. Each edges CSV has one row per **directed** edge, including separate rows for parallel edges. Route planning columns come first in the order shown below. Remaining OSM attributes appear afterward, alphabetically; their presence varies by map and network. A blank cell means that attribute was absent for that row. Values containing commas are quoted using standard CSV rules. OSMnx list attributes appear as Python-style lists, and geometry uses WKT with coordinates in longitude, latitude order. Use GraphML when graph-level metadata or original attribute types matter.

### Route planning columns

| File | Columns, in order | Use |
| --- | --- | --- |
| Nodes | `osmid`, `x`, `y`, `geometry` | Original OSM node ID; longitude and latitude in decimal degrees; WKT point for mapping. `osmid` matches edge endpoints and the GraphML node ID. |
| Edges | `u`, `v`, `key`, `length`, `geometry` | Source and target node IDs, parallel-edge key, length in metres for routing cost, and WKT path for mapping. Use `(u, v, key)` to identify an edge. |
| Edges, when present | `highway`, `maxspeed`, `access`, `oneway` | Road or path class, posted speed, access restrictions, and OSM direction tag. The edge direction is already encoded by `u` and `v`. |

### Additional OSM details

| Column | Meaning |
| --- | --- |
| `street_count` in nodes | Number of physical streets connected to the node, as computed by OSMnx. |
| `osmid` in edges | OSM way ID, or a list of way IDs when a simplified edge combines ways. |
| `name`, `ref` | OSM road or path name and route reference. |
| `reversed` | Whether OSMnx reversed the original OSM way direction. |
| Other columns, such as `lanes`, `bridge`, `tunnel`, `width`, `junction`, `service` | Optional OSM attributes; they may contain a single value or a list. |

For example, join `drive_edges.csv.u` to `drive_nodes.csv.osmid` for the start coordinate, and join `v` for the end coordinate. Use the `walk_` files the same way.

## Generated demand outputs

`python main.py generate-demand ...` creates one `outputs/requests/<task>_<map>_<number>/` directory per run. `data/buslines/` and `outputs/graphs/` supply its inputs. Earlier runs under `data/requests/` are legacy data and are not moved by the generator. See [graph CSV fields](#route-planning-columns) for the saved road networks.

Each run contains:

| File | Contents |
| --- | --- |
| `requests.json` | `{ "num_data:": N, "requests": { "<id>": request, ... } }`; request IDs are strings in the map. |
| `requests.csv` | One row per request, including a header when N is zero. Uses UTF-8 and standard CSV quoting. Coordinate arrays are JSON text such as `"[49.5, 6.1]"` inside a CSV cell. Extra `--debug` fields are appended after the standard columns in alphabetical order. |
| [`operations.json`](#operations) | One object keyed by task (`darp` or `sfbs`) with the selected operating and vehicle profile. |
| [`requests_metadata.json`](#metadata) | Run settings, software versions, input hashes, and SHA-256 hashes of `requests.json`, `requests.csv`, and `operations.json`. |

Request times are seconds relative to the service day; negative `time_stamp` means a prebooked request appeared on the previous day. Coordinate arrays use `[latitude, longitude]` in decimal degrees. Empty CSV cells mean that a field was absent or null in that request. The CSV and JSON contain the same request values, with arrays serialized as JSON text in CSV. A dash (—) in the Unit column means the field is an ID, label, Boolean, ratio, or other unitless value.

The methods below follow [`generate.py`](src/reqreate/generate.py), [`area_network.py`](src/reqreate/maps/area_network.py), [`filters.py`](src/reqreate/filters/filters.py), and [`pool_output.py`](src/reqreate/adapters/pool_output.py). Configuration comes from [`request_gen.toml`](src/reqreate/request_gen.toml), [`operation_profile.toml`](src/reqreate/operation/operation_profile.toml), and [`filters.toml`](src/reqreate/filters/filters.toml).

The generator draws separate Poisson counts for dynamic and prebooked requests. Given those counts, it samples dynamic appearance times uniformly in the simulation window and prebooked departure times uniformly from `demand_start` to simulation end. REQreate samples locations using saved POIs, POI-density zones, and configured radial distance and direction. Candidates must pass the service-area, minimum-driving-distance, positive-travel-time, and time-window checks. SFBS additionally requires stop access, a trip that is not dominated by walking, and a feasible scheduled bus. With `retry_if_filtered = true`, a rejected request is resampled under the same candidate ID (up to 1,000 attempts); otherwise it is dropped. Only retained requests are written.

### Time axis

Numeric time points such as `time_stamp`, `earliest_departure`, and the window boundaries use **seconds since the service day's midnight**. Durations such as `lead_time`, `direct_travel_time`, `service_time`, and the sampled pickup and dropoff window lengths are also seconds, but they are intervals rather than clock positions. A negative `time_stamp` refers to the preceding day. `operations.json` stores a separate operating period as clock strings; it does not set the demand simulation boundaries.

The following **illustrative dynamic request** uses a 5-minute lead time, a 15-minute pickup window, 10 minutes of direct driving, a 1.5 detour factor, 30 seconds of stop service, and a 15-minute dropoff window. The axis shows clock positions; the calculations underneath show how each position is obtained.

```text
Time since service-day midnight →

seconds     32400       32700             33600   33630             34530
clock       09:00       09:05             09:20   09:20:30          09:35:30
            │           │                 │       │                 │
            │           │                 │       │                 └─ dropoff_to = latest_arrival
            │           │                 │       └─ dropoff_from
            │           │                 └─ pickup_to
            │           └─ earliest_departure = pickup_from
            └─ time_stamp (request appears)

pickup window:         [32700 ─────────── 33600]
dropoff window:                                  [33630 ─────────── 34530]

dynamic:   time_stamp          = sampled appearance time       = 32400
           earliest_departure = time_stamp + lead_time        = 32400 + 300 = 32700
pickup:    pickup_from         = earliest_departure           = 32700
           pickup_to           = pickup_from + pickup_window  = 32700 + 900 = 33600
drive:     direct_travel_time  = int(direct_distance / vehicle_speed_mps) = 600
dropoff:   dropoff_to          = pickup_to + ceil(600 × 1.5) + 30 = 34530
           dropoff_from        = dropoff_to - dropoff_window  = 34530 - 900 = 33630
deadline:  latest_arrival      = dropoff_to                    = 34530

Same 09:05 earliest departure, but PREBOOKED with a 10-hour lead time:
           earliest_departure = sampled departure time       = 32700
           time_stamp         = earliest_departure - 36000   = -3300
           -3300 seconds means 23:05 on the PREVIOUS day.
```

| Time concept | Source or calculation | What it limits |
| --- | --- | --- |
| Simulation start/end | `simulation.start` and `simulation.end` in `request_gen.toml`, converted from clock strings to seconds. | Dynamic appearance times are drawn inside this interval; retained requests must finish by simulation end. |
| Demand start | `simulation.demand_start` in `request_gen.toml`, converted to seconds. | Prebooked earliest departures are drawn from here to simulation end; every retained request must have `earliest_departure >= demand_start`. |
| Appearance and lead time | Dynamic: draw `time_stamp`, then add the sampled `lead_time`. Prebooked: draw `earliest_departure`, then subtract `lead_time`. | Prebooked requests are retained only if their appearance is before simulation start. |
| Pickup window | Starts at `earliest_departure`; its length is sampled from `pickup_timewindow`. | Pickup service must fit inside `[pickup_from, pickup_to]`. |
| Direct driving time | `int(direct_distance / vehicle_speed_mps)`. | Supplies the road travel estimate used in the dropoff deadline. |
| Dropoff window | Ends at `pickup_to + ceil(direct_travel_time × detour_factor) + service_time`; its length is sampled from `dropoff_timewindow`. | Dropoff service must fit inside `[dropoff_from, dropoff_to]`; `latest_arrival` equals `dropoff_to`. |

The pickup and dropoff windows may **overlap**. `dropoff_from` is calculated from `dropoff_to`; it is not calculated by adding driving time to `pickup_from`. The generator checks that `service_time` fits within each window. These windows are bounds for scheduling, not predicted actual pickup and dropoff times.

### Request fields

| Field | Unit | How generated |
| --- | --- | --- |
| `num_data:` | requests | Count of retained requests: `len(requests)`. |
| `requests` | — | Map of retained requests, keyed by their candidate IDs as strings. Rejected IDs may leave gaps when retries are disabled. |
| `reqid` | — | Candidate index assigned to REQreate; matches the JSON request key. |
| `is_prebooked` | — | `1` for a candidate drawn from the prebooked Poisson count, `0` for one drawn from the dynamic count; flags are shuffled before generation. |
| `lead_time` | s | REQreate samples `lt_prebooked` or `lt_dynamic` from the configured distribution according to `is_prebooked`. |
| `time_stamp` | s from service-day midnight | Dynamic: sampled appearance time. Prebooked: `earliest_departure - lead_time`; may be negative. |
| `earliest_departure` | s from service-day midnight | Prebooked: sampled departure time. Dynamic: `time_stamp + lead_time`. |
| `pickup_from`, `pickup_to` | s from service-day midnight | `pickup_from = earliest_departure`; `pickup_to = pickup_from +` a sampled `pickup_timewindow` duration. Pickup service must finish by `pickup_to`. |
| `dropoff_from`, `dropoff_to` | s from service-day midnight | `dropoff_to = pickup_to + ceil(direct_travel_time × detour_factor) + service_time`; `dropoff_from = dropoff_to -` a sampled `dropoff_timewindow` duration. |
| `latest_arrival` | s from service-day midnight | Set equal to `dropoff_to`. |
| `service_time` | s | Duration sampled from the configured `service_time` distribution; applied at each stop. |
| `origin`, `destination` | decimal degrees `[latitude, longitude]` | REQreate samples trip endpoints from the saved service-area and POI-density zones using configured radial distance and direction. |
| `originnode_drive`, `destinationnode_drive` | — | DARP only: drive-graph node IDs to which REQreate snaps the sampled endpoints. |
| `origin_drive_point`, `destination_drive_point` | decimal degrees `[latitude, longitude]` | Read the snapped nodes' `y` (latitude) and `x` (longitude) coordinates from `drive.graphml`. |
| `direct_distance` | m | REQreate's `dist_drive(origin, destination)`: directed shortest path between snapped drive nodes, weighted by edge `length`. |
| `direct_travel_time` | s | `int(direct_distance / vehicle_speed_mps)` using the task's operation profile. |
| `energy_kwh` | kWh | `(direct_distance / 1000) × reference_kwh_per_km × (1 + temperature_increase_pct / 100)`; the reference temperature case uses 0% increase. Walking energy is excluded. |
| `boarding_stop_id`, `alighting_stop_id` | — | SFBS only: choose a GTFS stop pair with a feasible scheduled trip; minimize combined access walks, then prefer earlier bus arrival and departure. |
| `boarding_walk_distance_m`, `alighting_walk_distance_m` | m | SFBS only: shortest paths on the undirected walk graph, plus straight-line connectors from the passenger and stop to their nearest graph nodes. |
| `boarding_stop_point`, `alighting_stop_point` | decimal degrees `[latitude, longitude]` | SFBS only: copy the chosen stops' coordinates from the saved busline `stops.json`. |

`--debug` retains REQreate's extra sampling fields. `lt_dynamic` and `lt_prebooked` are sampled lead times in seconds from `request_gen.toml`; `lead_time` selects one of them. Other REQreate debug fields follow their upstream definitions.

### Operations

Each run's `operations.json` has one top-level `darp` or `sfbs` object. The writer copies its values from the selected task in [`operation_profile.toml`](src/reqreate/operation/operation_profile.toml) and its vehicle entry from [`veh_profile.toml`](src/reqreate/operation/veh_profile.toml). The clock strings below describe the **operation profile**; request generation uses the separate simulation boundaries documented in [the time axis](#time-axis).

| Field | Unit | How generated |
| --- | --- | --- |
| `start_time`, `end_time` | clock time (`H:MM:SS`) | Copy the task's `operation.start` and `operation.end` strings. |
| `average_speed_mps` | m/s | Copy `attribute.vehicle_speed`; used to calculate `direct_travel_time`. |
| `vehicle_count` | vehicles | Copy `attribute.num_of_vehicles`. |
| `vehicle_type` | — | Copy `attribute.profile`, the vehicle profile name. |
| `temperature_case` | — | Copy the configured temperature scenario label; `reference_20_22_c` denotes the 20–22 °C reference case. |
| `vehicle` | mixed; see below | Copy the profile selected by `vehicle_type` from `veh_profile.toml`. |
| `detour_factor` | — | Copy `attribute.detour_factor`; used to calculate `dropoff_to`. |

Within `vehicle`, `battery_capacity_kwh` is kWh, `passenger_capacity` is passengers, `sample_buses` is buses, `reference_kwh_per_km` is kWh/km, and `relative_increase_pct` values are percent. Keys such as `at_0_c` indicate ambient temperature in °C. `manufacturer`, `battery_system`, `battery_type`, `bus_type`, and `heating_strategy` are unitless labels. Some profiles omit optional fields.

### Metadata

Each run's `requests_metadata.json` records the inputs and effective settings used to generate its requests. The `simulation_*_s` values describe **demand sampling**; the `start_time` and `end_time` strings in [`operations.json`](#operations) describe a separate operation profile. See [the time axis](#time-axis) for how request times are calculated. Fields are written by [`pool_output.py`](src/reqreate/adapters/pool_output.py).

| Field | Unit | How generated |
| --- | --- | --- |
| `task`, `busline`, `graph` | — | Copy the command-line task, optional `--busline`, and `--map` selection. |
| `seed` | — | Read from `request_gen.toml`, unless `--seed` overrides it; `--times N` increments it for each run. |
| `generator` | — | Fixed description of the REQreate sampler and local time sampler. |
| `python_version`, `package_versions` | — | Read the running Python version and installed package metadata when writing the run. |
| `candidate_count` | attempts | Count calls to the REQreate candidate sampler, including retries. |
| `mean_candidate_count` | requests | Sum each arrival rate × its sampling-window duration in hours; the expected Poisson candidate count. |
| `request_count` | requests | Copy `num_data:` from the saved request pool. |
| `prebooked_probability` | — (0–1) | Expected prebooked count divided by `mean_candidate_count`; 0 when the mean is 0. |
| `dynamic_time_stamp_distribution`, `prebooked_earliest_departure_distribution` | mixed; see below | Copy the corresponding Poisson configuration objects from `request_gen.toml`. |
| `simulation_start_s`, `simulation_end_s`, `demand_start_s` | s from service-day midnight | Parse `simulation.start`, `simulation.end`, and `simulation.demand_start` clock strings from `request_gen.toml`. |
| `network_input`, `spatial_sampling`, `distance_method`, `travel_time_method` | — | Fixed method descriptions recorded by the writer; `spatial_sampling` adds the SFBS filters for SFBS runs. |
| `vehicle_speed_mps` | m/s | Copy the selected task's `attribute.vehicle_speed`, also saved as `average_speed_mps` in `operations.json`. |
| `detour_factor` | — | Copy the selected task's `attribute.detour_factor`, also saved in `operations.json`. |
| `bus_filters_enabled` | — | `true` for SFBS, `false` for DARP. |
| `poi_count` | POIs | Count features in the selected map's saved `pois.json`. |
| `inputs_sha256` | — | Compute SHA-256 for the configuration files, selected graph files, and, for SFBS, busline `stops.json` and `businfo.json`. |
| `pool_sha256`, `csv_sha256`, `operations_sha256` | — | Compute SHA-256 from the bytes of `requests.json`, `requests.csv`, and `operations.json` after writing them. |

The distribution objects have a unitless `type` (currently `poisson`) and `rate_per_hour` in requests/hour; both values come directly from [`request_gen.toml`](src/reqreate/request_gen.toml).
