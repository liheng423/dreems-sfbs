# Overview

DREEMS-SFBS generates synthetic passenger requests for Semi-Flex Bus (SFBS) and Dial-a-Ride Problem (DARP) services.

Features:

- 🗺️ Draw an **operation area** on an OpenStreetMap (OSM) map for the driving and walking road graphs. Set a **service area** inside it for points of interest (POIs) and passenger request origins and destinations.
- 🎲 Generate POI-based requests with REQreate, using bus stops and timetables for SFBS or no bus route for DARP.
- ⚙️ Tune demand, filters, and vehicle settings through configuration files.
- 🔎 Inspect road graph previews and explore requests in an interactive browser viewer.
- 📤 Export graphs and request instances in GraphML, JSON, and CSV for downstream optimization.

## Input and Output Data

### Inputs

- An operation area for road networks and a service area inside it for POIs and request endpoints, selected in the browser map.
- Demand settings in [request_gen.toml](src/reqreate/request_gen.toml), plus [map](src/reqreate/maps/map_config.toml), [filter](src/reqreate/filters/filters.toml), and [operation](src/reqreate/operation/operation_profile.toml) settings.
- For SFBS, GTFS stops and schedules saved under `data/buslines/<route>/` by [crawl_busline.py](crawl_busline.py).

### Outputs

- Driving and walking graphs in GraphML and CSV, plus the selected area and POIs, under `outputs/graphs/<map>/`.
- One JSON and CSV request pool per run under `outputs/requests/<task>_<map>_<number>/`, such as `outputs/requests/darp_my_area_0001/`.

## Quick start

Use Python 3.12 and `uv` from the repository root. Install the dependencies into the Python environment you will use for the commands below:

```bash
uv pip install --python python -r requirements.txt
python check_dependencies.py
```

To create a new map, run:

```bash
python main.py select-area my_area
```

In the browser, draw the **operation area** to download its road networks. The **service area** initially matches it; adjust the service area inside it if requests and POIs should cover a smaller region. Click **Save**, wait for the download to finish, then stop the area selector with Ctrl+C.

Generate a DARP instance and open the viewer:

```bash
python main.py generate-demand DARP --map my_area
python main.py visualize
```

For SFBS, use a map and route with saved GTFS data. The repository includes map and route `550`:

```bash
python main.py generate-demand SFBS --map 550 --busline 550
```

### Plot a request map

From the repository root, choose a saved map and request instance by folder name. Either command saves one PNG under `visualizations/` showing requests, the road network, POIs, depot, and service area. SFBS maps also show the selected bus route as straight links between consecutive GTFS stops; the feed snapshot does not store the route's road geometry.

```bash
python visualize_requests.py --map Esch --instance darp_Esch_0001
julia visualize_requests.jl --map Esch --instance darp_Esch_0001
python visualize_requests.py --map 550 --instance sfbs_550_0001
```

For Julia, install `JSON3` and `Luxor` once with `julia -e 'using Pkg; Pkg.add(["JSON3", "Luxor"])'`.

For another route, use [crawl_busline.py](crawl_busline.py) to save its GTFS stops and schedule, then pass `--busline NAME` when selecting an area to display its stops. Add `--times N` to a generation command for N instances. Selecting a new area requires OSM access. The published `reqreate==0.1.1` may fail with NumPy 2.x during generation; see the bundled [patch](src/reqreate/instance_generator.patch).

### [SFBS Only] Importing an Existing Bus Line

The input format follows [GTFS Schedule ZIP](https://gtfs.org/documentation/schedule/reference/) standard. Choose a service date covered by the feed and a route's `route_short_name` or `route_id` from `routes.txt` (`route_type=3` for a standard bus route). From the repository root, run:

```bash
python crawl_busline.py --gtfs-zip path/to/feed.zip --service-date 2026-10-19 --route 12 --name tec-12
```

Replace the example path, date, route, and output name with values from your feed. For a downloadable feed, use `--gtfs-url URL` in place of `--gtfs-zip path/to/feed.zip`. Use `--route-id ID` instead of `--route 12` if the feed has no short name, or add it when several routes share that name. `--name` sets the folder under `data/buslines/`; use an operator prefix such as `tec-12` when route numbers may overlap. If omitted, the folder uses the route's short name or ID. For a local ZIP, `--source-url URL` records its original source; `--license TEXT` records the feed's license when known.

The crawler writes `data/buslines/<name>/businfo.json` with the selected day's stops, trip times, and route patterns, plus `stops.json` for REQreate. 

For example, to import the timetable for Luxembourg bus route 550, run:
```
python crawl_busline.py \
  --gtfs-url "https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20261015-054835/gtfs-20261014-20261212.zip" \
  --service-date 2026-10-19 \
  --route 550 \
  --name lu-550 \
  --license "Creative Commons Attribution 4.0"
```

For other feeds, consult an open-data portal such as [Belgian Mobility Open Data](https://data.belgianmobility.io/en/data.html).

## How requests are calculated

[request_gen.toml](src/reqreate/request_gen.toml) sets arrival rates, lead times, and time windows; [operation_profile.toml](src/reqreate/operation/operation_profile.toml) sets vehicle speed and detour factor. The generator then:

1. Draws independent Poisson counts for dynamic and prebooked requests. Dynamic requests sample an appearance time; prebooked requests sample an earliest departure time. Lead time connects the two.
2. Samples origins and destinations within the service area using OSM POIs, estimates driving time from the directed road graph, and sets pickup and dropoff windows.
3. Keeps requests that meet area, distance, and time limits. SFBS also checks walking and bus timetable feasibility. With `retry_if_filtered = true`, rejected candidates are resampled.

### Time axis

Request times are seconds from service-day midnight. The formulas below show how appearance, pickup, and dropoff times are calculated; `service_time` is sampled per stop and must fit both time windows. This illustrative dynamic request uses a 5-minute lead time, a 15-minute pickup window, 10 minutes of direct driving, a 1.5 detour factor, 30 seconds of stop service, and a 15-minute dropoff window.

```text
Time since service-day midnight →

## Dynamic Requests:

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
dropoff:   dropoff_to          = pickup_to + ceil(direct_travel_time × detour_factor) + service_time
                                   = 33600 + ceil(600 × 1.5) + 30 = 34530
           dropoff_from        = dropoff_to - dropoff_window  = 34530 - 900 = 33630
deadline:  latest_arrival      = dropoff_to                    = 34530

## Prebooked:

Same 09:05 earliest departure, but PREBOOKED with a 10-hour lead time:
           earliest_departure = sampled departure time       = 32700
           time_stamp         = earliest_departure - lead_time = 32700 - 36000 = -3300
           -3300 seconds means 23:05 on the PREVIOUS day.
```

See [Request Outputs](#request-outputs) for the saved field definitions.

## Project structure

| Path | Purpose |
| --- | --- |
| `crawl_busline.py`, `src/crawler/` | Read GTFS; save routes, stops, service areas, OSM graphs, and POIs. |
| `main.py`, `src/reqreate/` | Run demand generation, filters, and calculations; configure them in `*.toml`. |
| `data/buslines/` | Saved GTFS route data. |
| `outputs/graphs/`, `outputs/requests/` | Saved maps and generated request JSON/CSV with parameters. |
| `interactive_visualizer/` | Browser viewer for generated results. |

# Configurations

Edit these TOML files before running `generate-demand`:

1. [request_gen.toml](src/reqreate/request_gen.toml): Set `simulation.start`, `end`, and `demand_start` as `HH:MM:SS` times. Set the two `rate_per_hour` values for dynamic and prebooked demand. The `lt_*`, `pickup_timewindow`, `dropoff_timewindow`, and `service_time` values are in seconds; `radial_distance` is in metres. For a fixed value, use `type = "uniform"` with `scale = 0`. Set `seed` for repeatable runs and `retry_if_filtered` to choose whether rejected requests are resampled until the number of requests reaches the preset.
2. [map_config.toml](src/reqreate/maps/map_config.toml): Choose OSM `poi_tags` to collect when saving a map, set `method_pois.rows` and `columns` for the POI sampling grid, and set `locations.depot` with a default name, latitude, and longitude. Add a map name under `[locations.depots]` to override it for one map. After changing `poi_tags` for an existing map, run `python main.py recrawl-pois MAP` to update its saved POIs. Save the area again if you change the depot.
3. [veh_profile.toml](src/reqreate/operation/veh_profile.toml): Use an existing `[profiles.NAME]` or add one with `battery_capacity_kwh`, `passenger_capacity`, and `reference_kwh_per_km`. Add `relative_increase_pct` entries only for temperature cases you intend to select.
4. [operation_profile.toml](src/reqreate/operation/operation_profile.toml): Edit `[darp.attribute]` or `[sfbs.attribute]` for the task you run. Set `vehicle_speed` in m/s, `detour_factor` (at least 1), `num_of_vehicles`, and `profile` to a `NAME` in `veh_profile.toml`. Use `temperature_case = "reference_20_22_c"` for the unadjusted energy rate, or an `at_*_c` key present in that vehicle's `relative_increase_pct`. Request sampling times come from `request_gen.toml`.

See [vehicle profile details](src/reqreate/operation/README.md) for the supplied energy values.

# Outputs

## Saved road graphs

Each `outputs/graphs/<map>/` folder contains the selected `service_area.geojson`, `pois.json`, `depot.json`, and two road networks. `drive.graphml` and `walk.graphml` are the complete OSMnx graphs used by demand generation. The matching csvs are tables of those same graphs for spreadsheet or data-frame use. The graphs (graphml) cover the selected operation area; the GeoJSON boundary is the service area.

Saving a map with `python main.py select-area <map>` writes the GraphML and CSV files together. Saving the same map again regenerates all four CSVs alongside the new GraphML files.

Both formats use the original OSM node IDs: a nodes CSV `osmid` matches its GraphML node ID and the `u` and `v` endpoints in the corresponding edges CSV. *Since the number of IDs in OSM could be extremely large, it's encouraged to re-enumerate the node IDs in downstream tasks.*



### Route planning columns

| File | Columns, in order | Use |
| --- | --- | --- |
| Nodes | `osmid`, `x`, `y`, `geometry` | Original OSM node ID; longitude and latitude in decimal degrees; WKT point for mapping. `osmid` matches edge endpoints and the GraphML node ID. |
| Edges | `u`, `v`, `key`, `length`, `geometry` | Source and target node IDs, parallel-edge key, length in metres for routing cost, and WKT path for mapping. Use `(u, v, key)` to identify an edge. |
| Edges, when present | `highway`, `maxspeed`, `access`, `oneway` | Road or path class, posted speed, access restrictions, and OSM direction tag. The edge direction is already encoded by `u` and `v`. |

### Additional details

These fields are less relevant to the optimization problems but useful when working with OSMnx.

In the nodes file, `street_count` gives the number of physical streets connected to each node. In the edges file, `osmid` is the OSM way ID, or a list of IDs if a simplified edge combines multiple ways. `name` and `ref` give the road or path name and route reference, while `reversed` indicates whether OSMnx reversed the original way direction. Optional attributes such as `lanes`, `bridge`, `tunnel`, `width`, `junction`, and `service` may contain a single value or a list. To get an edge’s start and end coordinates, join `drive_edges.csv.u` and `drive_edges.csv.v` to `drive_nodes.csv.osmid`, respectively; use the `walk_` files the same way.

## Generated demand outputs

Each `generate-demand` run writes a new numbered directory at `outputs/requests/<task>_<map>_<number>/` (for example, `darp_my_area_0001`). DARP uses the saved map in `outputs/graphs/`; SFBS also uses its route data in `data/buslines/`.

| File | What it contains |
| --- | --- |
| `requests.json` | A request pool shaped as `{"num_data:": N, "requests": {"<id>": {...}}}`. The unusual `num_data:` key includes the colon. IDs are strings and can have gaps if filtering removes candidates. |
| `requests.csv` | The same requests, the same as `requests.json` content-wise. |
| `operations.json` | One `darp` or `sfbs` operation setting with the selected operating hours, vehicle settings, and full vehicle profile. |
| `parameters.txt` | The demand and map settings, only the selected task's filter and operation settings, and only its vehicle profile. The task, map, busline, effective seed, and debug setting appear at the top. |

The JSON and CSV request values use the same fields. CSV is UTF-8 with standard quoting; Times and durations are in seconds. Coordinates are `[latitude, longitude]` in decimal degrees.

## Request Outputs

Time fields and their calculations are explained in the [Time axis](#time-axis).

| Field | Meaning |
| --- | --- |
| `reqid`, `is_prebooked` | Request ID (the `requests.json` key); `1` = prebooked, `0` = dynamic. |
| `time_stamp`, `lead_time`, `earliest_departure`, `pickup_*`, `dropoff_*`, `latest_arrival`, `service_time`, `direct_travel_time` | Appearance, lead time, departure, pickup and dropoff windows, deadline, stop service duration, and direct driving time. |
| `origin`, `destination` | Sampled passenger locations, possibly off the road network. |
| `origin_drive_point`, `destination_drive_point`; `originnode_drive`, `destinationnode_drive` | Nearest driving graph nodes to the passenger locations: coordinates for both tasks, node IDs saved only for DARP. SFBS still uses the nodes internally to calculate `direct_distance`. |
| `direct_distance`, `energy_kwh` | Directed shortest road distance between those nodes (metres); estimated energy = `(direct_distance / 1000) × reference_kwh_per_km × (1 + temperature_increase_pct / 100)`. The reference case uses 0% increase. |
| `boarding_stop_id`, `alighting_stop_id`; `boarding_stop_point`, `alighting_stop_point`; `boarding_walk_distance_m`, `alighting_walk_distance_m` | SFBS only: selected GTFS stops, their coordinates, and walking distances (including connectors to the walking graph). The bus stops are separate from the passenger locations and driving graph points. |

Only requests passing area, distance, travel time, and time window checks are saved; SFBS also checks walking access and timetable feasibility. `retry_if_filtered = true` resamples rejected candidates under the same ID up to 1,000 times; otherwise they are dropped. `--debug` retains extra sampling fields such as `lt_dynamic` and `lt_prebooked`.

### Operations

`operations.json` has one top-level key, `darp` or `sfbs`. Its `average_speed_mps`, `vehicle_count`, `vehicle_type`, `temperature_case`, and `detour_factor` come from that task's attributes in [operation_profile.toml](src/reqreate/operation/operation_profile.toml). `vehicle` contains the selected profile from [veh_profile.toml](src/reqreate/operation/veh_profile.toml), including battery capacity, passenger capacity, and reference energy consumption. Optional profile fields vary by vehicle.
