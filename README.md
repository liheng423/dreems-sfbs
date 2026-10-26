# Overview

DREEMS-SFBS generates synthetic passenger requests for Semi-Flex Bus (SFBS) and Dial-a-Ride (DAR, also as known as Dynamic Ride Sharing (DRS)) services.

Features:

- 🗺️ Draw an area on an OpenStreetMap (OSM) map for the driving and walking road graphs. Generate points of interest (POIs) and passenger request origins and destinations.
- 🗺️ Retrieve POIs directly from OSM automatically. 
- 🎲 Generate POI-based requests with REQreate (see the [REQreate paper](https://arxiv.org/abs/2208.12225) for more details), using bus stops and timetables for SFBS or no bus route for DAR.
- ⚙️ Tune demand, filters, and vehicle settings through configuration files.
- 🔎 Inspect road graph previews and explore requests in an interactive browser viewer.
- 📤 Export graphs and request instances in GraphML, JSON, and CSV for downstream optimization.



## Input and Output Data

### Inputs

- An **operation area** for road networks and a **service area** inside it for POIs and request endpoints, selected in the browser map.
- Demand settings in [request_gen.toml](src/reqreate/request_gen.toml), plus [map](src/reqreate/maps/map_config.toml), [filter](src/reqreate/filters/filters.toml), and [operation](src/reqreate/operation/operation_profile.toml) settings.
- For SFBS, GTFS stops and schedules are saved under `outputs/buslines/<route>/` by [crawl_busline.py](crawl_busline.py). Notes: what values do we need for the bus schedule and the data format?

### Outputs

- Driving and walking graphs in GraphML and CSV, plus the selected area and POIs, under `outputs/graphs/<map>/`.

- One JSON and CSV request pool (change the word) per run under `outputs/requests/<task>_<map>_<number>/`, such as `outputs/requests/dar_my_area_0001/`.

## Quick start

Use Python 3.12 and `uv` from the repository root. Install the dependencies into the Python environment you will use for the commands below:

```bash
uv pip install --python python -r requirements.txt
python check_dependencies.py
```

### Creating a New Map

To create a new map, run:

```bash
python main.py select-area my_area
```

In the browser, draw the **operation area** to download its road networks. The **service area** initially matches it; adjust the service area inside it if requests and POIs should cover a smaller region. Click **Save**, wait for the download to finish, then stop the area selector with Ctrl+C.

### Adding New Bus Stops and Charging Locations

// TODO: Review this
To choose locations on an existing map's driving graph, run:

```bash
python main.py select-locations my_area (--busline my_route)
```

#### Adding a new bus stop

The location selector has **Bus line** and **Parking and charging** modes. To insert a bus stop, choose its direction, zoom into the route, click a pale graph-node circle, and click **Insert stop** in the popup. The button names the two stops it will go between. Then click **Save changes**. You can also drag a route-line midpoint onto a graph node. Clicking a midpoint alone does nothing, and a drag that misses a stop or graph node leaves the route unchanged. Click a stop to edit its class or GTFS description. The selected order is saved as `selected_stop_ids` in `buslines.json`; imported GTFS trip times remain in their original order.

Caveat: The displayed sequence (especially for newly-added stops) do not change timetable feasibility; new stops need scheduled trip times before requests can board or alight there. In this case, please edit its timetable.

This modification will be saved in `outputs/buslines/<route>/stops.json` and `buslines.json`.

#### Adding a new charging or parking location

In the other mode, click graph nodes to select parking and charging locations; their IDs and coordinates come from the saved graph. Click **Save changes** to write both types to `outputs/graphs/<map>/locations.csv`. When a bus route is selected, bus stop edits are saved separately in the route's `stops.json` and `buslines.json`.

This modification will be saved in `outputs/graphs/<map>/locations.csv`

Every selection, stop edit, route edit, mode change, and save attempt is appended to `outputs/graphs/<map>/select_locations.jsonl` with a UTC timestamp. Edits are logged when they happen, before **Save changes**; each saved state is recorded too.


### Generating Requests

Generate a DAR instance and open the viewer:

```bash
python main.py generate-demand DAR --map my_area
python main.py visualize
```

For SFBS, use a map and route with saved GTFS data. The repository includes map and route `550`:

```bash
python main.py generate-demand SFBS --map 550 --busline 550
```

### Plot a request map

From the repository root, choose a saved map and request instance by folder name. Either command saves one PNG under `visualizations/` showing requests, the road network, POIs, depot, service area, and any saved parking locations or fixed charging stations. SFBS maps also show the selected bus route as straight links between consecutive GTFS stops; the feed snapshot does not store the route's road geometry.

```bash
python visualize_requests.py --map Esch --instance dar_Esch_0001
julia visualize_requests.jl --map Esch --instance dar_Esch_0001
python visualize_requests.py --map 550 --instance sfbs_550_0001
```

For Julia, install `JSON3` and `Luxor` once with `julia -e 'using Pkg; Pkg.add(["JSON3", "Luxor"])'`.

For another route, use [crawl_busline.py](crawl_busline.py) to save its GTFS stops and schedule, then pass `--busline NAME` when selecting an area to display its stops. Add `--times N` to a generation command for N instances. Selecting a new area requires OSM access. The published `reqreate==0.1.1` may fail with NumPy 2.x during generation; see the bundled [patch](src/reqreate/instance_generator.patch).

### [SFBS Only] Importing an Existing Bus Line

The input format follows [GTFS Schedule ZIP](https://gtfs.org/documentation/schedule/reference/) standard. Choose a service date covered by the feed and a route's `route_short_name` or `route_id` from `routes.txt` (`route_type=3` for a standard bus route). From the repository root, run:

```bash
python crawl_busline.py --gtfs-zip path/to/feed.zip --service-date 2026-10-19 --route 12 --name tec-12
```

Replace the example path, date, route, and output name with values from your feed. For a downloadable feed, use `--gtfs-url URL` in place of `--gtfs-zip path/to/feed.zip`. Use `--route-id ID` instead of `--route 12` if the feed has no short name, or add it when several routes share that name. `--name` sets the folder under `outputs/buslines/`; use an operator prefix such as `tec-12` when route numbers may overlap. If omitted, the folder uses the route's short name or ID. For a local ZIP, `--source-url URL` records its original source; `--license TEXT` records the feed's license when known.

The crawler writes `outputs/buslines/<name>/buslines.json` with the selected day's stops, trip times, and route patterns, plus `stops.json` for REQreate. Re-importing a route preserves edited stop classes and graph-node stops already saved in `stops.json`.

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

1. Draws independent Poisson counts for dynamic and prebooked requests. Dynamic requests sample an order placement time; prebooked requests sample an earliest departure time. Lead time connects the two.

[Poisson different arrival rate rush hour]

1. Samples origins and destinations within the service area using OSM POIs, estimates driving time from the directed road graph, and sets pickup and dropoff windows.
2. Keeps requests that meet area, distance, and time limits. SFBS also checks walking and bus timetable feasibility. With `retry_if_filtered = true`, rejected candidates are resampled.

### Time axis

Request times are seconds from service-day midnight. The formulas below show how order placement, pickup, and dropoff times are calculated; `service_time` is sampled per stop and must fit both time windows. This illustrative dynamic request uses a 5-minute lead time, a 15-minute pickup window, 10 minutes of direct driving, a 1.5 detour factor, 30 seconds of stop service, and a 15-minute dropoff window.

```text
Time since service-day midnight →

## Dynamic Requests:

seconds     32400       32700             33600   33630             34530
clock       09:00       09:05             09:20   09:20:30          09:35:30
            │           │                 │       │                 │
            │           │                 │       │                 └─ dropoff_latest = latest_arrival
            │           │                 │       └─ dropoff_earliest
            │           │                 └─ pickup_latest
            │           └─ earliest_departure = pickup_earliest
            └─ order_place_time (order is placed)

pickup window:         [32700 ─────────── 33600]
dropoff window:                                  [33630 ─────────── 34530]

dynamic:   order_place_time          = sampled order placement time  = 32400
           earliest_departure = order_place_time + lead_time        = 32400 + 300 = 32700
pickup:    pickup_earliest         = earliest_departure           = 32700
           pickup_latest           = pickup_earliest + pickup_window  = 32700 + 900 = 33600
drive:     direct_travel_time  = int(direct_distance / vehicle_speed_mps) = 600
dropoff:   dropoff_latest          = pickup_latest + ceil(direct_travel_time × detour_factor) + service_time
                                   = 33600 + ceil(600 × 1.5) + 30 = 34530
           dropoff_earliest        = dropoff_latest - dropoff_window  = 34530 - 900 = 33630
deadline:  latest_arrival      = dropoff_latest                    = 34530

## Prebooked:

Same 09:05 earliest departure, but PREBOOKED with a 10-hour lead time:
           earliest_departure = sampled departure time       = 32700
           order_place_time         = earliest_departure - lead_time = 32700 - 36000 = -3300
           -3300 seconds means 23:05 on the PREVIOUS day.
```

See [Request Outputs](#request-outputs) for the saved field definitions.

## Project structure

| Path | Purpose |
| --- | --- |
| `crawl_busline.py`, `src/crawler/` | Read GTFS; save routes, stops, service areas, OSM graphs, and POIs. |
| `main.py`, `src/reqreate/` | Run demand generation, filters, and calculations; configure them in `*.toml`. |
| `outputs/buslines/` | Saved route timetables and editable stop lists. |
| `outputs/graphs/`, `outputs/requests/` | Saved maps and generated request JSON/CSV with parameters. |
| `interactive_visualizer/` | Browser viewer for generated results. |

# Configurations

Edit these TOML files before running `generate-demand`:

1. [request_gen.toml](src/reqreate/request_gen.toml): Set `simulation.start`, `end`, and `demand_start` as `HH:MM:SS` times. Set the two `rate_per_hour` values for dynamic and prebooked demand. The `lt_*`, `pickup_timewindow`, `dropoff_timewindow`, and `service_time` values are in seconds; `radial_distance` is in metres. For a fixed value, use `type = "uniform"` with `scale = 0`. Set `seed` for repeatable runs and `retry_if_filtered` to choose whether rejected requests are resampled until the number of requests reaches the preset. See [REQreate](https://arxiv.org/abs/2208.12225) for more details.
2. [map_config.toml](src/reqreate/maps/map_config.toml): Choose OSM `poi_tags` to collect when saving a map, set `method_pois.cell_size_m` for the POI sampling grid (500 m by default), and set `locations.depot` with a default name, latitude, and longitude. Add a map name under `[locations.depots]` to override it for one map. After changing `poi_tags` for an existing map, run `python main.py recrawl-pois MAP` to update its saved POIs. Save the area again if you change the depot.
3. [veh_profile.toml](src/reqreate/operation/veh_profile.toml): Use an existing `[profiles.NAME]` or add one with `battery_capacity_kwh`, `passenger_capacity`, and `reference_kwh_per_km`. Add `relative_increase_pct` entries only for temperature cases you intend to select.
4. [operation_profile.toml](src/reqreate/operation/operation_profile.toml): Edit `[dar.attribute]` or `[sfbs.attribute]` for the task you run. Set `vehicle_speed` in m/s, `detour_factor` (at least 1), `num_of_vehicles`, and `profile` to a `NAME` in `veh_profile.toml`. Use `temperature_case = "reference_20_22_c"` for the unadjusted energy rate, or an `at_*_c` key present in that vehicle's `relative_increase_pct`. Request sampling times come from `request_gen.toml`.
5. [c_truck_profile.toml](src/reqreate/operation/c_truck_profile.toml): Define mobile trucks that charge other vehicles. The included placeholder has separate traction and charging battery capacities in kWh, charging output power in kW, and driving energy use in kWh/km. Select it with `charging_truck_profile` and set `num_of_charging_trucks` in each task's `operation_profile.toml` attributes.

See [vehicle profile details](src/reqreate/operation/README.md) for the supplied energy values.

# Outputs

## Saved road graphs

Each `outputs/graphs/<map>/` folder contains the selected `service_area.geojson`, `pois.json`, `depot.json`, and two road networks. `drive.graphml` and `walk.graphml` are the complete OSMnx graphs used by demand generation. The matching csvs are tables of those same graphs for spreadsheet or data-frame use. The graphs (graphml) cover the selected operation area; the GeoJSON boundary is the service area.

The separate `select-locations` command writes `locations.csv` in the graph folder. Its `type,osmid,x,y` columns identify parking or charging sites, using original driving graph node IDs, longitude, and latitude. Bus stop choices and classes go into the selected route's `outputs/buslines/<route>/stops.json`. New graph-node stops use names `Stop_OSM_<osmid>`. If the graph is regenerated, reopen the location selector to review its saved choices against the new nodes.

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

Each `generate-demand` run writes a new numbered directory at `outputs/requests/<task>_<map>_<number>/` (for example, `dar_my_area_0001`). DAR uses the saved map in `outputs/graphs/`; SFBS also uses its route data in `outputs/buslines/`.

| File | What it contains |
| --- | --- |
| `requests.json` | A request pool shaped as `{"num_data:": N, "requests": {"<id>": {...}}}`. The unusual `num_data:` key includes the colon. IDs are strings and can have gaps if filtering removes candidates. |
| `requests.csv` | The same requests, the same as `requests.json` content-wise. |
| `operations.json` | One `dar` or `sfbs` operation setting with the selected operating hours, vehicle settings, and full vehicle profile. |
| `parameters.txt` | The demand and map settings, only the selected task's filter and operation settings, and only its vehicle profile. The task, map, busline, effective seed, and debug setting appear at the top. |

The JSON and CSV request values use the same fields. CSV is UTF-8 with standard quoting; Times and durations are in seconds. Coordinates are `[latitude, longitude]` in decimal degrees.

## Request Outputs

Time fields and their calculations are explained in the [Time axis](#time-axis).

| Field | Meaning |
| --- | --- |
| `reqid`, `is_prebooked` | Request ID (the `requests.json` key); `1` = prebooked, `0` = dynamic. |
| `order_place_time`, `lead_time`, `earliest_departure`, `pickup_*`, `dropoff_*`, `latest_arrival`, `service_time`, `direct_travel_time` | Order placement, lead time, departure, pickup and dropoff windows, deadline, stop service duration, and direct driving time. |
| `origin`, `destination` | Sampled passenger locations, possibly off the road network. |
| `origin_drive_point`, `destination_drive_point`; `originnode_drive`, `destinationnode_drive` | Nearest driving graph nodes to the passenger locations: coordinates for both tasks, node IDs saved only for DAR. SFBS still uses the nodes internally to calculate `direct_distance`. |
| `direct_distance`, `energy_kwh` | Directed shortest road distance between those nodes (metres); estimated energy = `(direct_distance / 1000) × reference_kwh_per_km × (1 + temperature_increase_pct / 100)`. The reference case uses 0% increase. |
| `boarding_stop_id`, `alighting_stop_id`; `boarding_stop_point`, `alighting_stop_point`; `boarding_walk_distance_m`, `alighting_walk_distance_m` | SFBS only: selected GTFS stops, their coordinates, and walking distances (including connectors to the walking graph). The bus stops are separate from the passenger locations and driving graph points. |

Only requests passing area, distance, travel time, and time window checks are saved; SFBS also checks walking access and timetable feasibility. `retry_if_filtered = true` resamples rejected candidates under the same ID up to a maximum of 1,000 times; otherwise they are dropped. `--debug` retains extra sampling fields such as `lt_dynamic` and `lt_prebooked`.

### Operations

`operations.json` has one top-level key, `dar` or `sfbs`. Its `average_speed_mps`, `vehicle_count`, `vehicle_type`, `temperature_case`, and `detour_factor` come from that task's attributes in [operation_profile.toml](src/reqreate/operation/operation_profile.toml). `vehicle` contains the selected profile from [veh_profile.toml](src/reqreate/operation/veh_profile.toml), including battery capacity, passenger capacity, and reference energy consumption. Optional profile fields vary by vehicle.

`charging_trucks` contains the configured truck count, selected type, and the full profile from [c_truck_profile.toml](src/reqreate/operation/c_truck_profile.toml). These values are exported for downstream use; demand generation does not simulate charging.
