# Route 550 corridor and demand inputs

This folder contains reusable Python GTFS and live-departure crawlers and a
Julia corridor, travel-time matrix, demand, and visualization pipeline. Route
550 between Bettembourg and Remich is the first configured line. Passenger
volumes below are generated study scenarios; they are not observed ridership.

## Folder contents

| Path | Purpose |
| --- | --- |
| `src/crawler/python/crawl_gtfs.py` | Extract a selected route and service date from a static GTFS ZIP. It does not classify stops or make demand. |
| `src/crawler/python/crawl_realtime_550.py` | Capture Route 550 HAFAS real-time departure estimates into append-only JSON Lines. |
| `src/crawler/python/crawl_osm_distances.py` | Retrieve a directed physical-stop road-distance matrix from OSM-backed OSRM. |
| `data/distance_matrix_550.json` | Road distances in metres, indexed by original GTFS stop IDs, with routing and snapping provenance. |
| `src/reqreate_gen/generate.jl` | Read inputs, assemble outputs, and write the corridor, timetable, candidate pool, and scenarios. |
| `src/reqreate_gen/demand_config.jl` | Uniform stop dwell, demand seed, candidate count per cell, pickup half-window, booking lead ranges, and scenario request counts. |
| `src/reqreate_gen/types.jl` | Core records used repeatedly in network and demand calculations. One-off JSON envelopes and metadata are named tuples at their construction sites. |
| `src/reqreate_gen/output_adapters/output.jl` | Build network, candidate, and scenario-request records for the JSON schema. |
| `src/reqreate_gen/routes.jl` | Network lookups for route patterns and physical/logical stop IDs. |
| `src/reqreate_gen/input_adapters/network.jl` | Build direction-specific logical stops, stop classes, and scheduled travel times. |
| `src/reqreate_gen/travel_time_matrix.jl` | Build a separate real-time-adjusted travel-time matrix from captured HAFAS estimates. |
| `src/reqreate_gen/demand_generators/eligibility.jl` | Filter sampled passenger preferences using mandatory-corridor timing. |
| `src/reqreate_gen/demand_generators/allocations.jl` | Allocate scenario booking counts, select candidates, and assign electric/conventional service. |
| `src/reqreate_gen/demand_generators/demand.jl` | Sample and filter the candidate pool. |
| `src/utilities/utilities.jl` | Shared file-writing, service-time, and ordered-pair helpers used by the generator. |
| `src/vis/visualize.jl` | Render a separate map for each scenario direction and a six-panel PDF overview. |
| `src/reqreate_gen/stop_classes_550.json` | Reviewable source-stop mapping for mandatory anchors and interchanges. Other stops are optional; pattern terminals are always mandatory. |
| `data/crawled_550.json` | Normalized output from the Python crawler, including every active trip's stop events. |
| `data/realtime_550_{service-date}.jsonl` | Append-only live departure estimates captured by the second Python crawler, split by service date. |
| `data/travel_time_matrix_550.json` | Ordered stop-pair matrix estimated from matched live departure observations. |
| `data/corridor_550.json` | Shared route network and operating parameters without passenger demand. |
| `data/timetable_550.json` | Full trip timetable, route-relevant weekly calendar rules, date exceptions, and active service metadata. |
| `data/candidate_pool_550.json` | Surviving candidates from 8,000 seeded raw attempts (4,000 per route pattern). |
| `data/instances/550_{low,base,high}.json` | 50, 100, and 200 request instances. |
| `visualizations/` | Per-scenario, per-direction PNGs and the overview PDF. |

## Julia naming conventions

Julia function and local variable names use `snake_case`; constants use
`SCREAMING_SNAKE_CASE`. Shared domain terms use the abbreviations below in
functions, parameters, and local variables. Keep established short names such
as `main` and `write_json`. Struct fields that represent JSON schema
fields keep the schema spelling. Input/output JSON keys, file names, and CLI
flags remain unchanged because they are part of the data or command-line
interfaces.

| Abbreviation | Meaning | Example |
| --- | --- | --- |
| `s2m` | convert seconds to a whole minute | `s2m` |
| `sec` | second(s) | `trav_sec` |
| `val` / `vals` | value(s) | `write_json(path, val)`, `med_min(vals)` |
| `in` / `out` | input / output | `in_path`, `out_dir` |
| `min` | whole minute(s) | `med_min` |
| `med` | median | `med_min` |
| `od` | origin/destination pair | `od_key` |
| `org` | origin | `org_idx` |
| `dst` | destination | `dst_idx` |
| `arr` | arrival | `arr_min` |
| `des` | desired | `des_min` |
| `dur` | duration | `dur_min` |
| `src` | source | `src_stop_idx` |
| `idx` | index | `src_stop_idx` |
| `net` | network | `build_net` |
| `cand` | candidate | `build_cand_pool` |
| `meta` | metadata | `cand_meta` |
| `book` | booking type | `book_type` |
| `prebook` | pre-booked | `prebook_count` |
| `dyn` | dynamic | `dyn_count` |
| `scen` | scenario | `scen_reqs` |
| `alloc` / `allocs` | allocation(s) | `bus_allocs` |
| `inst` | instance | `inst_cfg` |
| `req` / `reqs` | request(s) | `draw_reqs!` |
| `obs` | observation | `read_obs`, `closest_obs_by_evt` |
| `evt` / `evts` | event(s) | `closest_obs_by_evt` |
| `dist` | distance | `dist_by_evt` |
| `sel` | selected | `sel_obs` |
| `samp` / `samps` | sample(s) | `samp_counts`, `trav_samps` |
| `trav` | travel | `trav_times`, `trav_sec` |
| `logi` | logical | `logi_ids` |
| `mat` | matrix | `build_mat`, `write_mat` |
| `xy` | coordinate pair | `stop_xy` |
| `dir` | source direction | `src_dir_id` |
| `cfg` | configuration | `class_cfg` |
| `params` | parameters | `params` |
| `hrs` | hours | `hrs` |
| `mand` | mandatory | `mand_ids` |
| `opt` | optional | `opt_ids` |
| `term` | terminal | `term_ids` |
| `plt` | plot object | `draw_reqs!` |
| `svc` | service | `svc_date` |
| `lbl` | label | `lbl_stops` |
| `pos` | positional | `pos_args` |
| `ovw` | overview | `ovw_plot` |

The renamed function map is:

| Previous name | Current name |
| --- | --- |
| `seconds_to_minute` | `s2m` |
| `pair_key` | `od_key` |
| `whole_minute_median` | `med_min` |
| `build_network` | `build_net` |
| `build_candidate_pool` | `build_cand_pool` |
| `read_observations` | `read_obs` |
| `closest_observation_by_event` | `closest_obs_by_evt` |
| `logical_stops_by_pattern` | `build_net` |
| `build_matrix` | `build_mat` |
| `write_matrix` | `write_mat` |
| `point_for` | `stop_xy` |
| `scenario_requests` | `scen_reqs` |
| `direction_title` | `pattern_title` |
| `draw_requests!` | `draw_reqs!` |
| `plot_direction` | `plot_pattern` |

The bang suffix marks functions that mutate an existing object.

Variable examples include `input_path` → `in_path`, `output_dir` → `out_dir`,
`logical_stops` → `logi_stops`, `origin_index` → `org_idx`,
`destination_index` → `dst_idx`, `request_id` → `req_id`, and
`plot_object` → `plt`.

`COLORS` in `src/vis/visualize.jl` stores the fixed route, booking, and
stop-category colors in a named tuple.

Schema keys such as `"origin"`, `"destination"`, and `"request_time"` remain
unchanged in generated JSON.

`types.jl` defines fixed-shape records for service periods, route patterns,
networks, and candidates. Output adapters expand network and
candidate records into named tuples; `requests_output` builds scenario request
named tuples and the ID-keyed dictionaries required by the JSON schema.

## Directed routes and network stop mapping (schema version 2)

An internal `route_id` is `<GTFS route_id>_<GTFS direction_id>`: the two
orientations of a bus line are separate routes. `source_route_id` and
`source_direction_id` retain the original feed identity. A route can contain
multiple `pattern_id` values for branches and short turns. Pattern IDs are
scoped to their directed route, not assumed globally unique.

`network.routes` lists directed routes and their pattern IDs. `network.patterns`
stores ordered logical stop occurrences and service windows. Each occurrence
has its own logical ID, including repeated visits to one physical stop.
`network.source_stop_ids` owns the logical-to-GTFS mapping. Use
`src_stop_id(net, logi_id)` to resolve a source ID, `logi_stop_ids(net, src_id)`
to find all occurrences, and `stop_pattern(net, logi_id)` to obtain route context.
No source-stop map is copied into the internal route patterns or requests.
Raw source trip events remain in the timetable for provenance.

The generator accepts either the existing single-route crawler object or a
JSON array of those objects. All objects must come from the same GTFS feed and
service date, with each source route included once. Crawl each bus line using
`--route-short-name`, then combine its normalized snapshot into the array.
The live crawler remains specific to line 550; this refactor does not add
multi-line live capture or transfer journeys.

```bash
julia --project=. src/reqreate_gen/generate.jl \
  data/crawled_network.json data/network src/reqreate_gen/stop_classes_550.json
```

The optional third argument supplies the source-stop classification file for
that network. Pattern terminals are mandatory even without a configured source
stop entry. Single-line filenames use its short name (e.g. `550_low.json`);
multi-line filenames use `network` (e.g. `network_low.json`).

Candidate pools use `(route_id, pattern_id)` internally and contain unlabeled
OD/pickup preferences. The JSON pool is an array of pattern objects with a
`candidates` array. Booking types are assigned during scenario allocation. Allocation metadata is an array named `route_pattern_booking_allocations`
with a `count` per cell. Requests replace the old `direction` field with
`route_id` and `pattern_id`. Equal allocation is by pattern, so a route with
more patterns receives more requests; this is a synthetic scenario assumption.
For remainders, pre-booked allocation starts at the first pattern and dynamic
allocation starts halfway through the pattern list. Both use fixed cyclic
orders so larger scenarios retain smaller scenarios' candidate prefixes.
Snapshot/pattern order determines logical numbering and seeded draw order.

These changes replace the version-1 JSON layout; regenerate datasets before
using the updated visualizer. Demand now uses sample-then-filter preferences; see Demand scenario assumptions.

Checks: `julia --project=. test/requests.jl`,
`julia --project=. test/routes.jl`, and
`julia --project=. test/fleet.jl`.

## Sources and provenance

The schedule source is the [official Luxembourg public transport GTFS
dataset](https://data.public.lu/en/datasets/horaires-et-arrets-des-transport-publics-gtfs/).
The crawler pins the archive URL below instead of following a moving “latest”
download. The archive is distributed under Creative Commons Attribution 4.0.

```text
https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20261001-055928/gtfs-20260930-20261212.zip
SHA-256: 8b4ea53d9c315dce3ca45d6610a624ebaa58f0069abcec9ce4523c8b43583876
```

The requested service date is Tuesday, 6 October 2026. The crawler resolves
`calendar.txt` and `calendar_dates.txt` for that date before selecting trips.
The crawled snapshot and timetable sidecar retain the Route 550 weekly rules
and all of its date exceptions alongside the selected active service IDs.
The snapshot contains 25 active trips in each direction. Direction 0 runs
Bettembourg → Remich (28 stops); direction 1 runs Remich → Bettembourg (27
stops). The return timetable has a final arrival at 00:01 on the following
clock day; GTFS writes this as 24:01, and this project preserves it as minute
1442 on the service-day time axis.

The September 2026 local Route 550 timetable PDF was checked against stop
order and representative trips. It agrees on the Bettembourg-to-Remich 04:45
departure and 22:15 final departure (22:51 arrival), plus the Remich-to-
Bettembourg 05:25 first departure and 23:25 final departure (00:01 arrival).
GTFS includes one inbound-only Altwies stop, Bourgässel, which remains in the
directional corridor as an optional stop. Reference PDF: `.ref/docs/550.pdf`.

The [ATP mobiliteit.lu API](https://data.public.lu/en/datasets/6048b5ee58974d5771b858e0/)
provides a live HAFAS departure board and requires a personal API key. Its
published API description does not offer a historical query or an archive of
past real-time observations. The new crawler therefore collects future live
snapshots only; it cannot recreate September 2026 actual bus times. Its
`rtTime` values are HAFAS real-time estimates, not confirmed final vehicle
arrival/departure records.

## Route 550 scenario definition

This baseline uses the active Route 550 timetable for Tuesday, 6 October 2026.
The ordered stop sequences below are the scheduled patterns; the corridor JSON
assigns direction-specific logical IDs to them.

- **Bettembourg → Remich (28 stops):** Bettembourg: Gare routière → Café du
  Stadion → Parc Merveilleux → Mosselter; Hellange: Beeteburgerstrooss → Kierch
  → Hoëner Halt; Frisange: Op der Kräizong → Ennescht Duerf; Aspelt: Op der
  Gare → Am Grëndchen; Altwies: Beckeschmillen → An der Kaatz → Millbaach;
  Mondorf-les-Bains: Kleng Gare → Bei der Douane → Christophorus → Casino 2000
  → Réimecherstrooss → Stade John Grün; Ellange: Ellenger Gare → Martialis;
  Erpeldange (Bous): Emeringerhaff → Scheierbierg → Kräizgaass; Remich: Op der
  Kopp → Schoul → Gare routière.
- **Remich → Bettembourg (27 stops):** Remich: Gare routière → Schoul → Op der
  Kopp; Erpeldange (Bous): Kräizgaass → Scheierbierg → Emeringerhaff; Ellange:
  Martialis → Ellenger Gare; Mondorf-les-Bains: Réimecherstrooss → Casino 2000
  → Christophorus → Bei der Douane → Kleng Gare; Altwies: Millbaach →
  Bourgässel → Beckeschmillen; Aspelt: Am Grëndchen → Op der Gare; Frisange:
  Ennescht Duerf → Op der Kräizong; Hellange: Hoëner Halt → Kierch →
  Beeteburgerstrooss; Bettembourg: Mosselter → Parc Merveilleux → Café du
  Stadion → Gare routière.

Scheduled travel times are calculated separately for every forward-ordered
stop pair within each direction: take the median active-trip departure-to-
arrival duration in seconds and floor it to whole minutes. Across the active
trips, terminal-to-terminal runs take 36:53–39:51 toward Remich and 36:50–39:15
toward Bettembourg. The matrix in `data/corridor_550.json` contains the
pairwise values; it is based on scheduled GTFS times, not live observations.

| Direction | First departure | Final scheduled trip |
| --- | --- | --- |
| Bettembourg → Remich | 04:45 | 22:15 departure; 22:51:53 arrival |
| Remich → Bettembourg | 05:25 | 23:25 departure; 00:01:50 arrival on 7 October |

The service window runs from each direction's first departure through its last
arrival. Times use the GTFS service-day axis, so the final inbound arrival is
24:01:50 (minute 1442 after rounding the window end up to a whole minute).

Demand is synthetic and scenario-based, not observed ridership. Low, base, and
high instances contain 50, 100, and 200 requests respectively, split by the configured booking share
between pre-booked and dynamic requests and balanced across directions. The
generator samples stop pairs and normally distributed desired pickup times
independently of scheduled departures, filters corridor timing, uses ±5-minute
pickup windows, and nests scenario samples with seed 42. Pre-booking leads
are 1–3 days; dynamic leads are 5–30 minutes. See Demand scenario assumptions.

## Rebuild the corridor and demand files

Python 3.9 or later is sufficient; the crawler uses only the standard library.
Use the pinned ZIP to reproduce the checked-in crawl without relying on a
network request:

```bash
python3 src/crawler/python/crawl_gtfs.py \
  --gtfs-zip /path/to/gtfs-20260930-20261212.zip \
  --service-date 2026-10-06 \
  --route-short-name 550 \
  --output data/crawled_550.json
```

If no `--gtfs-zip` is supplied, Python downloads the pinned archive URL. For
another bus line, pass `--route-short-name`, `--service-date`, and an output
path. The crawler requires equal arrival and departure times at each stop.
Pass `--route-id` if the feed has more than one route with that short
name. The crawler records the archive name, SHA-256, source URL, feed date
range, selected services, and route ID in its JSON output.

Julia 1.9 or later builds demand and visualizations. Install the dependencies
once and run the scripts from the repository root:

```bash
julia --project=. -e 'using Pkg; Pkg.instantiate()'
julia --project=. src/reqreate_gen/generate.jl
julia --project=. src/vis/visualize.jl
```

The generator accepts optional positional input and output directories:

```bash
julia --project=. src/reqreate_gen/generate.jl \
  data/crawled_550.json data
```

The visualizer also accepts an instance directory and output directory. Add
`--label-stops` to the command to annotate each map with its sequence number.
Re-running the generator with the same input and seed 42 reproduces the same
JSON content in the same Julia environment.

## Capture live Route 550 departures and build a matrix

Request a personal ATP key using the contact on the API dataset page. Before
capturing, rebuild `crawled_550.json` for the current Luxembourg service date;
the live crawler checks this so it cannot silently match today's departures
against a different day's timetable. With the static GTFS ZIP already
downloaded, for example:

```bash
python3 src/crawler/python/crawl_gtfs.py \
  --gtfs-zip /path/to/gtfs-20260930-20261212.zip \
  --service-date 2026-10-05 \
  --route-short-name 550 \
  --output data/crawled_550.json
```

Set the key in the shell, then leave the crawler running while the buses
operate. It looks up ATP stop IDs from stop coordinates, polls each Route 550
stop once per sweep, and appends only board entries with a real-time departure
estimate. Use `--cycles 1` to capture one sweep, or omit it for continuous
capture. Adjust `--poll-seconds` to control the interval between sweeps.

```bash
export ATP_API_KEY='your-personal-key'
python3 src/crawler/python/crawl_realtime_550.py --poll-seconds 60
```

After collecting observations, create the separate matrix:

```bash
julia --project=. src/reqreate_gen/travel_time_matrix.jl \
  data/crawled_550.json data/realtime_550_2026-10-05.jsonl data/travel_time_matrix_550.json
```

For each trip and stop, Julia keeps the capture closest to the scheduled
departure within 15 minutes. Each origin/destination sample starts with the
scheduled origin-departure-to-destination-arrival duration and adjusts it by
the difference between HAFAS's estimated delay at the two stops. The output
stores median whole minutes and a sample count for each ordered pair. It omits
pairs without matched live estimates and does not fall back to the scheduled
matrix. This is an estimate derived from the live departure feed; the API does
not provide historical observations or confirmed arrival times for this
workflow. The result is separate from `corridor_550.json` and does not replace
the scheduled `network.travel_times` field.

## Crawl OpenStreetMap road distances

Run the separate standard-library crawler on the existing normalized GTFS file:

```bash
python3 src/crawler/python/crawl_osm_distances.py \
  --gtfs-json data/crawled_550.json \
  --output data/distance_matrix_550.json
python3 test/crawl_osm_distances.py
```

The [OSRM Table API](https://project-osrm.org/docs/v5.24.0/api/#table-service)
returns distances along the fastest routed paths on the OpenStreetMap road
network, in metres. These are neither Euclidean distances nor minimum-distance
paths. The default public endpoint uses car access rules, so these are road
estimates, not measured bus mileage or a reconstruction of the exact line 550
itinerary. For bus-specific restrictions, use `--osrm-url` with a server
preprocessed for the intended vehicle; changing `--profile` alone does not
change a server's prepared graph.

`distances_m[i][j]` is the directed distance from `stop_ids[i]` to `stop_ids[j]`.
Both axes include all physical stops, including reverse and cross-pattern
journeys. Stop IDs remain strings with leading zeros. Unreachable pairs are
`null`, never a straight-line fallback or a zero-distance journey. The crawler
also accepts an array of route snapshots from the same feed and deduplicates
shared physical stops. It makes one table request; larger networks exceeding
the server's coordinate limit will need batched requests or a larger server
limit. API failures abort the crawl before writing output.

The output retains input coordinates, snapped source/destination locations and
snap distances, the request URL, retrieval timestamp, input SHA-256, and the OSM
data version when the server supplies it (`null` otherwise). Inspect snapping
before interpreting small distance savings: a stop may snap to a different
road or carriageway. OSM data is credited to
[OpenStreetMap contributors under ODbL](https://www.openstreetmap.org/copyright).
The retrieval date does not imply that the OSM graph matches the GTFS service date.

To use the matrix with generated scenarios, resolve logical IDs through
`network.source_stop_ids`, then find those source IDs in `stop_ids`. For an
ordered vehicle itinerary, sum entries for **consecutive visited stops**,
including repositioning/depot legs if their coordinates are included in your
input. Do not use only the terminal-to-terminal entry for the fixed-line
baseline: it may shortcut intermediate stops. Summing consecutive GTFS stops
is a baseline approximation, not proof of the exact scheduled road alignment.

With a common consumption rate `c` in kWh/km, estimated energy savings are
`(baseline_distance_m - proposed_distance_m) / 1000 * c`. Different vehicle
types require separate consumption rates for each itinerary. Distance alone
does not capture acceleration, idling, gradient, passenger load, or HVAC.
The generator now reads this distance file when writing instances. It sums
consecutive GTFS stop-to-stop distances for each scheduled bus trip and
multiplies by the selected profile's kWh/km rate. `trip_energy` in each instance
contains the source trip ID, directed route and pattern, distance in km, and
estimated energy in kWh. It does not represent a passenger request's marginal
energy or the optimized semi-flexible itinerary. The distance file does not
alter scheduled travel times.

Choose the bus type when generating instances:

```bash
julia --project=. src/reqreate_gen/generate.jl --fleet-type=electric
julia --project=. src/reqreate_gen/generate.jl --fleet-type=conventional
```

Edit `src/reqreate_gen/fleet_config.jl` to change the fleet defaults. The
electric default is a 12 m eCitaro with 396 kWh installed battery capacity,
88-passenger capacity, hybrid heating, and 0.87 kWh/km median consumption at
20–22 °C (Jablonski et al., NEIS 2023, Table 1). The conventional default is
4.44 kWh/km of **fuel energy equivalent**, the midpoint of the 3.90–4.98
kWh/km range cited from other studies in that paper's introduction. It is not
a measured Route 550 bus and is not a monetary cost. Override either rate with
`--energy-rate-kwh-per-km=NUMBER`. The selected type and rate are recorded in
`config.fleet_type` and `fleet`; the default electric files keep their existing
paths, while conventional files go in `data/instances/conventional/`.

These estimates exclude depot legs, charging, usable battery limits, weather,
passenger load, topography, and the actual bus road alignment. The OSRM matrix
uses a car access profile, so replace or calibrate it before treating the
estimates as bus operating measurements.

## Input fields and time units

Internal records avoid storing values that can be derived from the network:
`RoutePattern` keeps its stop sequence without copying source IDs or terminal IDs;
`NetworkData` keeps route pattern sequences and mandatory IDs without separate all-stop,
optional-stop, or terminal lists. `ServicePeriod` stores seconds only, preserving
precision while minute bounds are calculated as needed. `Candidate` stores
sampled passenger preferences independently of scheduled
trips. Source stop IDs, routes, patterns, and pickup windows are derived for
output. The timetable sidecar retains original GTFS trips for provenance;
candidates do not claim a source trip or scheduled arrival.

The corridor retains the reference instance sections `config`, `network`,
`requests`, and `parameters`. Scenario files also include `fleet` and
`trip_energy` for the user-selected bus type. Charging infrastructure and
vehicle availability remain separate extensions identified in the first-step
email.

| Field | Meaning |
| --- | --- |
| `network.stops` | Ordered logical stop IDs. Each physical GTFS stop gets a separate logical ID in each direction. |
| `network.patterns` | Directed route ID, GTFS pattern, label, logical stop IDs, terminal IDs, and pattern-specific operating period. |
| `network.coordinates` | Logical stop ID → `[longitude, latitude]` from `stops.txt`. |
| `network.source_stop_ids`, `network.stop_names` | Maps logical IDs back to the GTFS stop ID and name. |
| `network.mandatory_stops`, `network.optional_stops` | Complete, non-overlapping logical stop classification. |
| `network.class_reasons` | Reason for every mandatory/optional assignment. Mandatory source-stop choices are editable in `src/reqreate_gen/stop_classes_550.json`. |
| `network.travel_times` | `"origin_id,destination_id"` → scheduled whole minutes. Only forward-ordered pairs within one direction are present; cross-direction pairs have no route meaning. |
| `network.dwell_times` | Logical stop ID → configured `DWELL_MIN` whole minutes (default 0). This service assumption is independent of the GTFS stop timestamps. |
| `timetable_550.service_calendars` | Weekly GTFS rules and date exceptions for the service IDs used by the selected route, plus the active IDs for the selected date. |
| `requests.prebooked`, `requests.dynamic` | Maps from request ID to the KU Leuven request fields plus `route_id` and `pattern_id`. |
| `parameters.operating_hours` | `[start, end]` in minutes from GTFS service-day start. End may exceed 1440 for trips after midnight. |
| `parameters.promise_window` | Early and late pickup allowances, both 5 minutes. |
| `generation`, `metadata` | Seed, candidate construction, scenario allocations, provenance, and explicit scope notes. |

Request `desired_time`, `time_window`, and `request_time` all use integer
minutes from the service-day start (minute 360 means 06:00). Pre-booked
requests can have negative `request_time` because they are made one to three
days before service.

## Stop classification assumptions

Both terminal stops are mandatory. In addition, one locality anchor is
mandatory for each intermediate town: Hellange/Kierch, Frisange/Op der
Kräizong, Aspelt/Op der Gare, Altwies/Millbaach, Mondorf-les-Bains/Kleng
Gare, Ellange/Ellenger Gare, and Erpeldange (Bous)/Kräizgaass. Aspelt/Op der
Gare and Mondorf-les-Bains/Christophorus are also marked for their interchange
role. Other stops, including the additional inbound Altwies/Bourgässel stop,
are optional. The reasons are recorded per logical stop in
`network.class_reasons`; update the source-ID mapping and rerun Julia to review
alternative choices.

## Configured stop dwell

Set `DWELL_MIN` in `src/reqreate_gen/demand_config.jl` to a nonnegative whole
number of minutes per stop (default `0`; use `1` for Leuven's dwell assumption).
Run `julia --project=. src/reqreate_gen/generate.jl` to update the network and
requests, then `julia --project=. src/vis/visualize.jl` to refresh the maps.

The value is written to every logical stop's `network.dwell_times` and used by
the mandatory-corridor demand filter. It does not modify GTFS timestamps or
subtract dwell from the scheduled travel-time matrix. The live-matrix builder
uses the same configuration when constructing its network.

## Demand scenario assumptions

The generator draws one shared, unlabeled pool per directed route pattern.
`CAND_COUNT_PER_PATTERN = 4_000` gives 8,000 raw attempts for Route 550, with
seed 42. Each draw chooses two distinct logical stops uniformly, orders them
forward, and samples desired pickup time from a normal distribution. Its mean
is the service-period midpoint and its standard deviation is one-sixth of the
period; `DES_MEAN_FRACTION` and `DES_STD_FRACTION` configure these values.

Candidates contain only an ID, origin, destination, and desired pickup time.
They have no booking type, submission timestamp, bus type, or source trip.
Corridor timing rejects impossible pickup preferences, then shuffles survivors
once per pattern. The filter uses mandatory-stop travel and configured dwell,
a five-minute terminal buffer, and a full ±5-minute pickup window within
service hours. It does not establish destination-detour or fleet feasibility.

## Booking and bus-type allocation

`demand_generators/allocations.jl` selects shared candidates and assigns labels.
Configure `PREBOOK_SHARE` and `ELECTRIC_SHARE` in `demand_config.jl` (both default
to 0.5). Dynamic and conventional shares are the complements. Shares range
from 0 to 1; counts round to the nearest integer, ties up. Odd totals work.

For each scenario request slot, cumulative rounding assigns a booking label.
Each booking category cycles across patterns, with dynamic allocation starting
halfway through the pattern list. Allocation consumes the next unused candidate
from that pattern's shared pool, then samples the booking lead: 1–3 whole days
for pre-booked, or 5–30 whole minutes for dynamic. The request timestamp is the
desired pickup minus the lead. A dynamic booking before service opening is
rejected; allocation tries the next candidate for the same slot, without
relabeling the failed candidate or shortening its lead. Pool exhaustion raises
an explicit error. A raw candidate is used at most once per scenario.

Restarting allocation with the same seed and larger total preserves selected
candidates, booking labels, and timestamps. Default low/base/high totals remain
50/100/200. Requests are sorted by booking time and numbered from zero.
Electric/conventional labels are assigned by cumulative rounding in that output
order; electric share applies to the whole scenario. Bus labels can change
between nested scenarios because output positions can change. They represent
service types, not vehicle dispatch, capacity, battery, or charging feasibility.

Each final request retains booking `type` and `bus_type`. Scenario config
records proportions and realized counts. Allocation metadata records counts
for each booking type, route, and pattern. Candidate-pool JSON now has no
booking-type field or request timestamps: regenerate data and visualizations
after this change.

## Rejected-candidate debug output

The global `DEBUG = true` switch writes
`data/debug/rejected_candidates_550.debug.json`, explicitly labeled `debug: true`.
`rejected_candidates` contains raw preferences rejected by corridor timing,
including reasons and bounds. `rejected_allocations` separately records failed
dynamic assignments with scenario, candidate details, booking type, timestamp,
service start, and reason. The same failed draw can appear for several scenarios
because each scenario restarts allocation from the same seeded sequence.

Setting `DEBUG = false` skips debug capture and writing, and removes the previous
debug file for this dataset on the next completed generator run. Accepted
requests are identical with debug on or off.
