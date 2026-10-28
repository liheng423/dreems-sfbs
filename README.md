# DREEMS Instance Generator

DREEMS-InstanceGenerator generates synthetic passenger requests for Semi-Flex Bus (SFBS) and Dial-a-Ride (DAR, also known as Dynamic Ride Sharing, DRS) services.

- 🗺️ Draw an area on an OpenStreetMap (OSM) map to download its driving and walking road graphs and points of interest (POIs).
- 🚌 Import bus stops and timetables from GTFS feeds for SFBS, and edit stops, parking, and charging locations on the map.
- 🎲 Generate POI-based requests with REQreate ([paper](https://arxiv.org/abs/2208.12225)), checked against the bus timetable for SFBS or unconstrained by routes for DAR.
- ⚙️ Tune demand, filters, and vehicle settings in TOML configuration files.
- 🔎 Explore requests in an interactive browser viewer or plot them to PNG.
- 📤 Export graphs and request instances as GraphML, JSON, and CSV for downstream optimization.

## Workflow

| Step | Command | Writes to |
| --- | --- | --- |
| 1. Create a map | `python main.py select-area MAP` | `outputs/graphs/MAP/` |
| 2. [Optional] Import a bus line (SFBS only) | `python crawl_busline.py ...` | `outputs/buslines/ROUTE/` |
| 3. [Optional] Edit stops and locations | `python main.py select-locations MAP [--busline ROUTE]` | `outputs/graphs/MAP/`, `outputs/buslines/ROUTE/` |
| 4. Generate requests | `python main.py generate-demand {DAR,SFBS} --map MAP [--busline ROUTE]` | `outputs/requests/<task>_MAP_<number>/` |
| 5. Inspect results | `python main.py visualize` or `python visualize_requests.py ...` | `visualizations/` |

Bundled maps: `Esch`, `550` (Luxembourg route 550 corridor), and `leuven`. Bundled bus routes: `550 `and `605` (Luxembourg) and `delijn-2-out` (Leuven).

## Installation

### Environment Setup
Use Python 3.12 and [`uv`](https://docs.astral.sh/uv/). From the repository root, create and activate a virtual environment, then install the dependencies:

> New to `uv`? Follow the [installation guide](https://docs.astral.sh/uv/getting-started/installation/) first. It takes a minute.

```bash
uv venv --python 3.12
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
python check_dependencies.py
```

### Patch for REQreate 

> This patch is already included in the repo. If the `check_dependencies.py` warns about the missing patch, do the following steps, otherwise, skip them. 

The published `reqreate==0.1.1` must be patched before generating requests. The [patch](src/reqreate/instance_generator.patch) adds the `mandatory` and `optional` stop classes used by every `stops.json` (SFBS fails without it) and fixes indexing errors under NumPy 2.x. Apply it once to the installed package:

```bash
patch -p1 -d "$(python -c 'import REQreate, pathlib; print(pathlib.Path(REQreate.__file__).parents[1])')" \
  < src/reqreate/instance_generator.patch
python check_dependencies.py
```

On Windows, `patch` is not available by default, but [Git for Windows](https://git-scm.com/download/win) includes it. Use the block that matches your shell. Variable syntax differs between shells, so running the PowerShell block in Command Prompt fails with `can't change to directory '$reqreate'`.

In **PowerShell** (the prompt starts with `PS`):

```powershell
$reqreate = python -c "import REQreate, pathlib; print(pathlib.Path(REQreate.__file__).parents[1])"
& "C:\Program Files\Git\usr\bin\patch.exe" -p1 -d "$reqreate" -i src\reqreate\instance_generator.patch
python check_dependencies.py
```

In **Command Prompt** or **Anaconda Prompt** (cmd.exe):

```bat
for /f "delims=" %d in ('python -c "import REQreate, pathlib; print(pathlib.Path(REQreate.__file__).parents[1])"') do set "REQREATE=%d"
"C:\Program Files\Git\usr\bin\patch.exe" -p1 -d "%REQREATE%" -i src\reqreate\instance_generator.patch
python check_dependencies.py
```

Alternatively, run the bash commands above unchanged in Git Bash.

Re-apply the patch whenever REQreate is reinstalled. Selecting a new area or importing a GTFS feed from a URL requires internet access.


## Usage

### 1. Create a map

```bash
python main.py select-area myarea
```

In the browser, draw the **operation area**; its road networks will be downloaded. The **service area**, where POIs and request endpoints are placed, initially matches the operation area; shrink it if requests should cover a smaller region. Click **Save**, wait for the download to finish, then stop the selector with Ctrl+C. Add `--busline ROUTE` to display an imported route's stops while drawing.

> [NOTE]
> The depot may lie outside the service area, so the operation area is larger to ensure the fleet can always reach and leave the depot.

> [!WARNING]
> For SFBS, keep the selected region a narrow strip along the bus line. If it is too large, REQreate may fail to generate valid requests along the line.

### 2. [Optional] Import a bus line (SFBS only)

Bus lines are read from a [GTFS Schedule ZIP](https://gtfs.org/documentation/schedule/reference/). Choose a service date covered by the feed and a route from `routes.txt` (`route_type=3` is a standard bus route). For example, to import Luxembourg route 550:

```bash
python crawl_busline.py \
  --gtfs-url "https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20261015-054835/gtfs-20261014-20261212.zip" \
  --service-date 2026-10-19 \
  --route 550 \
  --name lu-550 \
  --license "Creative Commons Attribution 4.0"
```

Dated feed URLs like this one expire once the feed's validity period ends (here 2026-12-12). Take the current ZIP from the [data portal page](https://data.public.lu/en/datasets/horaires-et-arrets-des-transport-publics-gtfs/). This example writes to `outputs/buslines/lu-550/`. The bundled route `550` used in later examples came from an earlier version of the same feed and kept the default name.

| Option | Meaning |
| --- | --- |
| `--gtfs-url URL` / `--gtfs-zip PATH` | Download the feed, or read a local ZIP. |
| `--service-date YYYY-MM-DD` | Day whose trips are imported. |
| `--route NAME` / `--route-id ID` | Select by `route_short_name` or `route_id`. Use `--route-id` when the feed has no short name, or together with `--route` when several routes share a name. |
| `--name NAME` | Output folder under `outputs/buslines/`. Letters, digits, and hyphens only (no underscores). Defaults to the route's short name or ID; an operator prefix such as `tec-12` avoids collisions. |
| `--mandatory-stop-id ID` | Mark a GTFS stop as `mandatory` in addition to the route terminals. Repeat for several stops. |
| `--source-url URL`, `--license TEXT` | Record the original source of a local ZIP and the feed's license. |
| `--output PATH`, `--stops-output PATH` | Write `buslines.json` or `stops.json` somewhere else. |

The crawler writes `buslines.json` (the selected day's stops, trip times, and route patterns) and `stops.json` (stops for REQreate). Each stop in `stops.json` has a `class`:

- `mandatory`: the bus always serves the stop. Route terminals and any `--mandatory-stop-id` stops get this class.
- `optional`: the bus serves the stop only on demand. All other stops get this class.

Demand generation treats both classes the same: either can be a boarding or alighting stop. The class is exported for downstream SFBS optimization. Re-importing a route keeps stop classes and graph-node stops already edited in `stops.json`.

#### GTFS feeds

| Region | Operator | GTFS ZIP | Notes |
| --- | --- | --- | --- |
| Luxembourg | All operators | [data.public.lu](https://data.public.lu/en/datasets/horaires-et-arrets-des-transport-publics-gtfs/) | Dated URL; see the example above. |
| Wallonia, Belgium | TEC | `https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip` | Fixed URL that always serves the current feed. Short names repeat across TEC's five regional agencies, so pass `--route-id` (for example `C0001-21650` for Charleroi line 1). |
| Flanders, Belgium (including Leuven) | De Lijn | `https://gtfs.flatturtle.cloud/delijn/delijn-gtfs_YYYY-MM-DD.zip` | Daily mirror; pick a current file from the [folder listing](https://gtfs.flatturtle.cloud/delijn/). The official feed requires a license request on the [De Lijn Open Data portal](https://data.delijn.be/). Each direction is a separate route, so pass `--route-id` and import each direction under its own `--name`. |
| Brussels, Belgium | STIB-MIVB | `https://gtfs.flatturtle.cloud/stib-mivb/stib-mivb-gtfs_YYYY-MM-DD.zip` | Daily mirror; see the [folder listing](https://gtfs.flatturtle.cloud/stib-mivb/). |

More feeds are listed on [Belgian Mobility Open Data](https://data.belgianmobility.io/en/data.html) and the [Mobility Database](https://mobilitydatabase.org/). The large De Lijn feed takes about 10 seconds and 1 GB of memory to import; download it once and reuse it with `--gtfs-zip`.

For example, to import De Lijn line 2 between Leuven station and the KU Leuven Campus Arenberg in Heverlee, outbound direction:

```bash
python crawl_busline.py \
  --gtfs-url "https://gtfs.flatturtle.cloud/delijn/delijn-gtfs_2026-10-28.zip" \
  --service-date 2026-10-29 \
  --route-id 30020 \
  --name delijn-2-out
```

Each mirror file covers a limited date range, so replace the date in the URL with a current file from the folder listing and choose a `--service-date` inside its range. De Lijn route IDs can also change between feed versions; if `30020` is not found, look up the current ID in `routes.txt`.

Use `--route-id 30021` for the return direction. Other De Lijn routes serving KU Leuven campuses: `12` (Leuven Station ⇄ Heverlee Campus Arenberg; IDs `30120`, `30121`), `43` (Gasthuisberg Campus ⇄ Haasrode; `30430`, `30431`), and `4a`/`4b` (via Campus Vesalius; `30040`, `30041`, `30080`, `30081`). To find routes for other stops, search `stops.txt` for the stop name, then follow `stop_times.txt` → `trips.txt` → `routes.txt`.

### 3. Edit bus stops and charging locations

```bash
python main.py select-locations myarea [--busline my_route]
```

Without `--busline`, the selector opens the route with the same name as the map, if one exists. Otherwise only the **Parking and charging** mode is available.

The selector has two modes: **Bus line** and **Parking and charging**. Click **Save changes** to write edits in either mode.

**Bus stops.** Choose a direction, zoom into the route, click a pale graph-node circle, and click **Insert stop**; the button names the two stops the new one will go between. Alternatively, drag a route-line midpoint onto a graph node (clicking a midpoint does nothing, and a drag that misses a node leaves the route unchanged). Click a stop to change its class (`mandatory` or `optional`, see [step 2](#2-import-a-bus-line-sfbs-only)) or its GTFS description. A new stop is named `Stop_OSM_<osmid>` in `stops.json`, and its stop ID is `OSM_<osmid>`. Edits are saved to `outputs/buslines/<route>/stops.json`. The stop order is saved to `patterns[].selected_stop_ids` in `outputs/buslines/<route>/buslines.json`.

> [!WARNING]
> Adding a stop changes only the displayed sequence, not the timetable. Timetable feasibility is checked against `patterns[].trips[].stop_times` in `outputs/buslines/<route>/buslines.json`, so passengers cannot board or alight at a new stop until each trip that serves it has an entry there. Add the entry at the stop's position in the list, with `stop_id` (`OSM_<osmid>`), `stop_sequence`, `arrival_time` (`H:MM:SS`), `departure_time`, `departure_seconds`, `pickup_type: "0"`, and `drop_off_type: "0"`. A boarding stop only counts if it comes before the alighting stop in `stop_times`.

> [!WARNING]
> The data format of the semi-flex bus still needs to be discussed to decide, since not all the current fields in `busline.json` and `stops.json` are useful.

**Parking and charging.** Click graph nodes to select parking and charging locations. Both types are saved to `outputs/graphs/<map>/locations.csv`.

Every selection, edit, mode change, and save attempt is logged with a UTC timestamp to `outputs/graphs/<map>/select_locations.jsonl`, as it happens and before saving.

### 4. Generate requests

```bash
python main.py generate-demand DAR --map myarea
python main.py generate-demand SFBS --map 550 --busline 550
python main.py generate-demand SFBS --map leuven --busline delijn-2-out
```

SFBS needs a map and an imported bus route; DAR rejects `--busline`. Add `--debug` to keep extra sampling fields. Add `--times N` to generate N instances in N new folders. Instance *k* (counting from 0) uses `seed + k`, where `seed` comes from `request_gen.toml`, so the whole batch is repeatable. Adjust the [configuration](#configuration) first.

### 5. Inspect results

Open the interactive viewer:

```bash
python main.py visualize
```

Or save a PNG of one instance under `visualizations/`, showing requests, road network, POIs, depot, service area, and any parking or charging locations:

```bash
python visualize_requests.py --map Esch --instance dar_Esch_0001
python visualize_requests.py --map 550 --instance sfbs_550_0001
julia visualize_requests.jl --map Esch --instance dar_Esch_0001
```

For SFBS, the bus route is drawn as straight links between consecutive stops, since the GTFS snapshot does not store road geometry. The Julia version needs `JSON3` and `Luxor`: `julia -e 'using Pkg; Pkg.add(["JSON3", "Luxor"])'`.

## Configuration

Edit these TOML files before running `generate-demand`:

| File | Settings |
| --- | --- |
| [request_gen.toml](src/reqreate/request_gen.toml) | `simulation.start`, `end`, and `demand_start` (`HH:MM:SS`); `rate_per_hour` for dynamic and prebooked demand; `lt_*`, `pickup_timewindow`, `dropoff_timewindow`, and `service_time` (seconds); `radial_distance`, the distance from the POI-sampled endpoint to the other endpoint (metres, `uniform` or `normal`); `radial_direction`, that endpoint's bearing clockwise from north (degrees, `loc` to `loc + scale`); `seed` for repeatable runs; `retry_if_filtered` to resample rejected requests. For a fixed value, use `type = "uniform"` with `scale = 0`. |
| [map_config.toml](src/reqreate/maps/map_config.toml) | OSM `poi_tags` to collect; `method_pois.cell_size_m` for the POI sampling grid (default 500 m); the default `locations.depot` (name, latitude, longitude), overridable per map under `[locations.depots]`. After changing `poi_tags`, run `python main.py recrawl-pois MAP`; after changing the depot, save the area again. |
| [filters.toml](src/reqreate/filters/filters.toml) | Per task: `max_walking_distance_m` and `walking_speed_mps` (used by the SFBS walking and timetable checks), `min_distance` (metres), and an on/off switch for each filter under `[dar.enabled]` or `[sfbs.enabled]`. See [Filters](#filters). |
| [operation_profile.toml](src/reqreate/operation/operation_profile.toml) | Per task, under `[dar.attribute]` or `[sfbs.attribute]`: `vehicle_speed` (m/s), `detour_factor` (≥ 1), `num_of_vehicles`, `profile` (a name from `veh_profile.toml`), `temperature_case` (`reference_20_22_c` for the unadjusted rate, or an `at_*_c` key from the vehicle's `relative_increase_pct`), `charging_truck_profile`, and `num_of_charging_trucks`. |
| [veh_profile.toml](src/reqreate/operation/veh_profile.toml) | Vehicle profiles `[profiles.NAME]` with `battery_capacity_kwh`, `passenger_capacity`, `reference_kwh_per_km`, and optional `relative_increase_pct` per temperature case. |
| [c_truck_profile.toml](src/reqreate/operation/c_truck_profile.toml) | Mobile charging trucks: traction and charging battery capacities (kWh), charging power (kW), and driving consumption (kWh/km). The included profile is a placeholder. |

## How requests are generated

### REQreate in brief

[REQreate](https://arxiv.org/abs/2208.12225) (Queiroz, Lucas, and Sörensen, 2022) builds request instances for on-demand transport problems from real OSM data:

1. **Network.** Download the area's driving and walking graphs from OSM and compute shortest-path travel times between nodes.
2. **Locations.** Collect POIs, bus stops, schools, and zones in the area to anchor origins and destinations.
3. **Parameters.** Define the request attributes in a configuration (time windows, lead time, walking limits, and so on). An attribute can be a fixed value, a random draw, or a formula of other attributes.
4. **Sampling.** Draw request times from a temporal distribution and origins and destinations from a spatial distribution (random, clustered, POI-based, or zone-based).
5. **Constraints.** Reject requests that break the configured constraints and draw replacements.
6. **Output.** Write the requests, network, and travel-time data as an instance, with optional replicas and metrics such as dynamism, urgency, and geographic dispersion.

This project uses REQreate's network, POI retrieval, and POI-based sampling, and replaces the time sampling and constraints with its own Poisson counts and filters:

1. **Count.** Draw independent Poisson counts of dynamic and prebooked requests. Dynamic requests sample an order placement time; prebooked requests sample an earliest departure time. The lead time links the two.
2. **Sample.** Pick origins and destinations from OSM POIs in the service area, estimate driving time on the directed road graph, and set pickup and dropoff windows.
3. **Filter.** Keep only requests that pass every [filter](#filters). With `retry_if_filtered = true`, a rejected request is resampled under the same ID (generation stops with an error after 1,000 failed attempts); otherwise it is dropped, so IDs may have gaps.

> [!NOTE]
> POI density drives where demand appears. The service area is split into a grid of `method_pois.cell_size_m` cells, and only cells containing POIs can be chosen. Each cell is weighted by its share of all POIs (`density_pois`). The set of `poi_tags` collected and the grid size therefore shape the spatial demand directly.

> [!WARNING]
> A retried request does not keep its Poisson-sampled time. Each retry draws a new time uniformly over the request's window (`simulation.start`–`end` for dynamic, `demand_start`–`end` for prebooked). With many retries, the times in the output are no longer a Poisson process. Set `retry_if_filtered = false` if the arrival distribution matters for your analysis.

### Filters

The filters are defined in [filters.py](src/reqreate/filters/filters.py) and applied in [generate.py](src/reqreate/generate.py) (`filter_requests`). Their settings are in [filters.toml](src/reqreate/filters/filters.toml). A request is kept only if it passes every check, in this order:

| Filter | Task | Rejects a request when |
| --- | --- | --- |
| Time limits | Both | `earliest_departure` is outside `simulation.demand_start`–`end`; `latest_arrival` is after `simulation.end`; or a prebooked request's `order_place_time` is not before `simulation.start`. |
| `request_within_area` | Both | The origin or destination lies outside the service area. |
| `request_has_min_driving_distance` | Both | `direct_distance` < `min_distance`. |
| `request_has_positive_travel_time` | Both | `direct_travel_time` is 0. |
| `request_within_walking_distance` | SFBS | The origin or destination has no stop within `max_walking_distance_m` on the walking graph. |
| `request_not_walk_dominated` | SFBS | Walking directly from origin to destination is no longer than walking to and from the nearest stops combined. |
| `request_has_feasible_scheduled_bus` | SFBS | No scheduled trip lets the passenger walk to a boarding stop after `earliest_departure`, ride, and walk from the alighting stop by `latest_arrival`. Walking time is distance / `walking_speed_mps`. |

To turn a filter off, set it to `false` under `[dar.enabled]` or `[sfbs.enabled]` in [filters.toml](src/reqreate/filters/filters.toml); a filter left out stays on. Turning off `request_has_min_driving_distance` or `request_has_positive_travel_time` also stops REQreate from resampling such trips. The time limits always apply. For SFBS, a kept request with no feasible stop pair (possible when the walking or timetable filter is off) has no boarding or alighting stop fields.

Because of the time limits, requests with long trips that start close to `simulation.end` are always rejected. For SFBS, the kept stop pair is the one with the least total walking, then the earliest arrival.

### Definitions: Types of Time

All times are seconds since service-day midnight. Example dynamic request: 5-minute lead time, 15-minute pickup window, 10 minutes of direct driving, detour factor 1.5, 30 s of stop service, and a 15-minute dropoff window.
> [!WARNING]
> Make sure your markdown render window wide enough to ensure the following diagram is more readable.
```text
seconds     32400       32700             33600   33630             34530
clock       09:00       09:05             09:20   09:20:30          09:35:30
            │           │                 │       │                 │
            │           │                 │       │                 └─ dropoff_latest = latest_arrival
            │           │                 │       └─ dropoff_earliest
            │           │                 └─ pickup_latest
            │           └─ earliest_departure = pickup_earliest
            └─ order_place_time

pickup window:          [32700 ─────────── 33600]
dropoff window:                                  [33630 ─────────── 34530]

order_place_time    = sampled                                         = 32400
earliest_departure  = order_place_time + lead_time                    = 32400 + 300 = 32700
pickup_earliest     = earliest_departure                              = 32700
pickup_latest       = pickup_earliest + pickup_window                 = 32700 + 900 = 33600
direct_travel_time  = int(direct_distance / vehicle_speed_mps)        = 600
dropoff_latest      = pickup_latest + ceil(direct_travel_time × detour_factor) + service_time
                                                                      = 33600 + 900 + 30 = 34530
dropoff_earliest    = dropoff_latest - dropoff_window                 = 34530 - 900 = 33630
latest_arrival      = dropoff_latest                                  = 34530
```

A prebooked request samples `earliest_departure` instead and subtracts the lead time. With the same 09:05 departure and a 10-hour lead time, `order_place_time = 32700 - 36000 = -3300`, i.e. 23:05 on the previous day.

`service_time` is sampled per stop and must fit both time windows.

## Outputs

### Road graphs: `outputs/graphs/<map>/`

| File | Contents |
| --- | --- |
| `drive.graphml`, `walk.graphml` | Complete OSMnx graphs of the operation area, used for demand generation. |
| `drive_nodes.csv`, `drive_edges.csv`, `walk_nodes.csv`, `walk_edges.csv` | The same graphs as tables. Regenerated whenever the map is saved. |
| `service_area.geojson`, `pois.json`, `depot.json` | Service area boundary, POIs, and depot. |
| `locations.csv` | Parking and charging sites from `select-locations`: `type,osmid,x,y` (driving graph node ID, longitude, latitude). |
| `select_locations.jsonl` | Edit log of the location selector. |

Nodes and edges use original OSM node IDs: a node's `osmid` matches its GraphML ID and the `u`/`v` endpoints of edges. These IDs are very large, so re-enumerate them for downstream tasks. If a graph is regenerated, reopen the location selector to check saved locations against the new nodes.

Columns used for routing:

| File | Columns | Meaning |
| --- | --- | --- |
| Nodes | `osmid`, `x`, `y`, `geometry` | Node ID; longitude and latitude (decimal degrees); WKT point. |
| Edges | `u`, `v`, `key`, `length`, `geometry` | Source and target node IDs; parallel-edge key (`(u, v, key)` identifies an edge); length in metres; WKT path. |
| Edges, when present | `highway`, `maxspeed`, `access`, `oneway` | Road class, posted speed, access restrictions, OSM direction tag. Direction is already encoded by `u` → `v`. |

To get an edge's endpoint coordinates, join `u` and `v` to `osmid` in the matching nodes file.

<details>
<summary>Other OSMnx columns</summary>

- Nodes: `street_count` is the number of physical streets meeting at the node.
- Edges: `osmid` is the OSM way ID, or a list if a simplified edge merges several ways. `name` and `ref` give the road name and route reference; `reversed` shows whether OSMnx reversed the way's direction. Optional attributes such as `lanes`, `bridge`, `tunnel`, `width`, `junction`, and `service` may hold a single value or a list.

</details>

### Request instances: `outputs/requests/<task>_<map>_<number>/`

Each `generate-demand` run creates a new numbered folder, such as `dar_myarea_0001`.

| File | Contents |
| --- | --- |
| `requests.json` | `{"num_data:": N, "requests": {"<id>": {...}}}`. Note that the key `num_data:` includes the colon. IDs are strings. |
| `requests.csv` | The same requests as UTF-8 CSV with standard quoting. |
| `operations.json` | Operating settings and vehicle profile for the task (see below). |
| `parameters.txt` | Task, map, bus line, effective seed, and debug flag, followed by the demand, map, filter, operation, and vehicle settings used. |

#### Request fields

Times and durations are in seconds; coordinates are `[latitude, longitude]` in decimal degrees.

> [!IMPORTANT]
> Request files use `[latitude, longitude]`, but the graph CSVs and `locations.csv` use `x` = longitude and `y` = latitude, as does Shapely's `Point(x, y)`. Check the order whenever you combine the two.

| Field | Meaning |
| --- | --- |
| `reqid` | Request ID (the `requests.json` key). |
| `is_prebooked` | `1` = prebooked, `0` = dynamic. |
| `order_place_time`, `lead_time`, `earliest_departure`, `latest_arrival`, `service_time`, `direct_travel_time` | See [Time axis](#time-axis). |
| `pickup_earliest`, `pickup_latest` | Pickup time window. |
| `dropoff_earliest`, `dropoff_latest` | Dropoff time window. |
| `origin`, `destination` | Sampled passenger locations, possibly off the road network. |
| `origin_drive_point`, `destination_drive_point` | Coordinates of the nearest driving graph nodes. |
| `originnode_drive`, `destinationnode_drive` | IDs of those nodes (DAR only). |
| `direct_distance` | Shortest directed road distance between those nodes, in metres. |
| `energy_kwh` | `(direct_distance / 1000) × reference_kwh_per_km × (1 + temperature_increase_pct / 100)`; the reference case uses 0%. |
| `boarding_stop_id`, `alighting_stop_id`, `boarding_stop_point`, `alighting_stop_point` | SFBS only: selected GTFS stops and their coordinates. |
| `boarding_walk_distance_m`, `alighting_walk_distance_m` | SFBS only: walking distance to and from the stops, including connectors to the walking graph. |

With `--debug`, extra sampling fields such as `lt_dynamic` and `lt_prebooked` are kept.

#### `operations.json`

The single top-level key is `dar` or `sfbs`.

- `average_speed_mps`, `vehicle_count`, `vehicle_type`, `temperature_case`, `detour_factor`: from the task's attributes in [operation_profile.toml](src/reqreate/operation/operation_profile.toml).
- `vehicle`: the selected profile from [veh_profile.toml](src/reqreate/operation/veh_profile.toml) (battery capacity, passenger capacity, reference consumption, and optional fields).
- `charging_trucks`: truck count, type, and full profile from [c_truck_profile.toml](src/reqreate/operation/c_truck_profile.toml). Exported for downstream use only; demand generation does not simulate charging.

## Project structure

| Path | Purpose |
| --- | --- |
| `main.py`, `src/reqreate/` | CLI, demand generation, filters, and TOML configuration. |
| `crawl_busline.py`, `src/crawler/` | GTFS import, service areas, OSM graphs, and POIs. |
| `src/locations/` | Bus stop, parking, and charging location selector. |
| `src/output_adapters.py` | Output folder and file names. |
| `interactive_visualizer/` | Browser viewer for generated results. |
| `shared/` | Route drawing code shared by the selector and the viewer. |
| `visualize_requests.py`, `visualize_requests.jl`, `visualizations/` | Static PNG plots of request instances. |
| `test/` | Standalone test scripts. |
| `outputs/graphs/`, `outputs/buslines/`, `outputs/requests/` | Saved maps, bus routes, and generated instances. |
