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
| `src/reqreate-gen/generate.jl` | Read inputs, assemble outputs, and write the corridor, timetable, candidate pool, and scenarios. |
| `src/reqreate-gen/demand_config.jl` | Demand seed, candidate count per cell, pickup half-window, booking lead ranges, and scenario request counts. |
| `src/reqreate-gen/types.jl` | Core records used repeatedly in network and demand calculations. One-off JSON envelopes and metadata are named tuples at their construction sites. |
| `src/reqreate-gen/output.jl` | Reconstruct derived network and candidate fields when writing the existing JSON schema. |
| `src/reqreate-gen/directions.jl` | Assign logical stop IDs and shared direction fields for both scheduled and real-time matrices. |
| `src/reqreate-gen/types.jl` | Typed fixed-shape records for the network, demand, and generated JSON documents. |
| `src/reqreate-gen/network.jl` | Build direction-specific logical stops, stop classes, and scheduled travel times. |
| `src/reqreate-gen/travel_time_matrix.jl` | Build a separate real-time-adjusted travel-time matrix from captured HAFAS estimates. |
| `src/reqreate-gen/demand.jl` | Enumerate feasible scheduled trip/stop pairs, sample the candidate pool, and allocate scenarios. |
| `src/utilities/utilities.jl` | Shared JSON conversion, file-writing, service-time, and ordered-pair helpers used by the generator. |
| `src/vis/visualize.jl` | Render a separate map for each scenario direction and a six-panel PDF overview. |
| `src/reqreate-gen/stop_classes_550.json` | Reviewable source-stop mapping for mandatory anchors and interchanges. Stops absent from this mapping are optional. |
| `data/crawled_550.json` | Normalized output from the Python crawler, including every active trip's stop events. |
| `data/realtime_550_{service-date}.jsonl` | Append-only live departure estimates captured by the second Python crawler, split by service date. |
| `data/travel_time_matrix_550.json` | Ordered stop-pair matrix estimated from matched live departure observations. |
| `data/corridor_550.json` | Shared route network and operating parameters without passenger demand. |
| `data/timetable_550.json` | Full trip timetable, route-relevant weekly calendar rules, date exceptions, and active service metadata. |
| `data/candidate_pool_550.json` | Seeded 8,000-request candidate pool (2,000 per booking-type/direction cell) used to sample scenarios. |
| `data/instances/550_{low,base,high}.json` | 50, 100, and 200 request instances. |
| `visualizations/` | Per-scenario, per-direction PNGs and the overview PDF. |

## Julia naming conventions

Julia function and local variable names use `snake_case`; constants use
`SCREAMING_SNAKE_CASE`. Shared domain terms use the abbreviations below in
functions, parameters, and local variables. Keep established short names such
as `main`, `asdict`, and `write_json`. Struct fields that represent JSON schema
fields keep the schema spelling. Input/output JSON keys, file names, and CLI
flags remain unchanged because they are part of the data or command-line
interfaces.

| Abbreviation | Meaning | Example |
| --- | --- | --- |
| `s2m` | convert seconds to a whole minute | `s2m` |
| `sec` | second(s) | `trav_sec` |
| `val` / `vals` | value(s) | `asdict(val)`, `med_min(vals)` |
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
| `elig` | eligible | `elig_sched_pairs` |
| `sched` | scheduled | `elig_sched_pairs` |
| `cand` | candidate | `build_cand_pool` |
| `meta` | metadata | `cand_meta` |
| `book` | booking type | `book_type` |
| `prebook` | pre-booked | `prebook_count` |
| `dyn` | dynamic | `dyn_count` |
| `scen` | scenario | `scen_allocs`, `scen_reqs` |
| `alloc` / `allocs` | allocation(s) | `scen_allocs` |
| `inst` | instance | `inst_reqs` |
| `req` / `reqs` | request(s) | `inst_reqs`, `draw_reqs!` |
| `obs` | observation | `read_obs`, `closest_obs_by_evt` |
| `evt` / `evts` | event(s) | `closest_obs_by_evt` |
| `dist` | distance | `dist_by_evt` |
| `sel` | selected | `sel_obs` |
| `samp` / `samps` | sample(s) | `samp_counts`, `trav_samps` |
| `trav` | travel | `trav_times`, `trav_sec` |
| `logi` | logical | `logi_stops_by_pat` |
| `pat` | pattern | `logi_stops_by_pat` |
| `mat` | matrix | `build_mat`, `write_mat` |
| `xy` | coordinate pair | `stop_xy` |
| `dir` | direction | `dir_title`, `plot_dir` |
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
| `eligible_scheduled_pairs` | `elig_sched_pairs` |
| `build_candidate_pool` | `build_cand_pool` |
| `scenario_allocations` | `scen_allocs` |
| `instance_requests` | `inst_reqs` |
| `read_observations` | `read_obs` |
| `closest_observation_by_event` | `closest_obs_by_evt` |
| `logical_stops_by_pattern` | `build_dirs` |
| `build_matrix` | `build_mat` |
| `write_matrix` | `write_mat` |
| `point_for` | `stop_xy` |
| `scenario_requests` | `scen_reqs` |
| `direction_title` | `dir_title` |
| `draw_requests!` | `draw_reqs!` |
| `plot_direction` | `plot_dir` |

The bang suffix marks functions that mutate an existing object.

Variable examples include `input_path` → `in_path`, `output_dir` → `out_dir`,
`logical_stops` → `logi_stops`, `origin_index` → `org_idx`,
`destination_index` → `dst_idx`, `request_id` → `req_id`, and
`plot_object` → `plt`.

`ColorPalette` in `src/vis/visualize.jl` declares the fixed route, booking, and
stop-category colors as struct fields instead of a string-keyed dictionary.

Schema keys such as `"origin"`, `"destination"`, and `"request_time"` remain
unchanged in generated JSON.

`types.jl` defines fixed-shape records for service periods, directions,
networks, candidates, requests, scenario allocations, and generated JSON
documents. JSON3 writes those structs using their declared field names;
ID-indexed lookup tables remain dictionaries because their keys vary with the
feed or sampled requests.

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
high instances contain 50, 100, and 200 requests respectively, split evenly
between pre-booked and dynamic requests and balanced across directions. The
generator samples seeded, feasible scheduled trip/stop pairs, uses pickup
windows of desired time ±5 minutes, gives pre-booked requests 1–3 days of lead
time and dynamic requests 5–30 minutes, and nests the scenario samples using
seed 42. The detailed eligibility and allocation rules follow under Demand
scenario assumptions.

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
path. Pass `--route-id` if the feed has more than one route with that short
name. The crawler records the archive name, SHA-256, source URL, feed date
range, selected services, and route ID in its JSON output.

Julia 1.9 or later builds demand and visualizations. Install the dependencies
once and run the scripts from the repository root:

```bash
julia --project=. -e 'using Pkg; Pkg.instantiate()'
julia --project=. src/reqreate-gen/generate.jl
julia --project=. src/vis/visualize.jl
```

The generator accepts optional positional input and output directories:

```bash
julia --project=. src/reqreate-gen/generate.jl \
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
julia --project=. src/reqreate-gen/travel_time_matrix.jl \
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

## Input fields and time units

Internal records avoid storing values that can be derived from the network:
`Direction` keeps its stop sequence without copying source IDs or terminal IDs;
`NetworkData` keeps direction sequences and mandatory IDs without separate all-stop,
optional-stop, or terminal lists. `ServicePeriod` stores seconds only, preserving
precision while minute bounds are calculated as needed. `SchedPair` and `Candidate`
keep logical stop IDs and trip-specific provenance; source stop IDs, candidate
directions, pickup windows, and dynamic lead limits are derived when needed.
Trip IDs and scheduled arrival times remain because aggregate network travel
times cannot reconstruct a particular trip. `Request` also derives its direction
and pickup window at output time; `output.jl` assembles the unchanged JSON schema.

The corridor and scenario files retain the reference instance sections
`config`, `network`, `requests`, and `parameters`. There is intentionally no
`fleet` section: the first deliverable describes corridor and demand inputs;
fleet composition, energy consumption, charging infrastructure, and vehicle
availability are separate extensions identified in the first-step email.

| Field | Meaning |
| --- | --- |
| `network.stops` | Ordered logical stop IDs. Each physical GTFS stop gets a separate logical ID in each direction. |
| `network.directions` | Direction ID, GTFS pattern, label, ordered logical/source stop IDs, terminal IDs, and direction-specific operating period. |
| `network.coordinates` | Logical stop ID → `[longitude, latitude]` from `stops.txt`. |
| `network.source_stop_ids`, `network.stop_names` | Maps logical IDs back to the GTFS stop ID and name. |
| `network.mandatory_stops`, `network.optional_stops` | Complete, non-overlapping logical stop classification. |
| `network.class_reasons` | Reason for every mandatory/optional assignment. Mandatory source-stop choices are editable in `src/reqreate-gen/stop_classes_550.json`. |
| `network.travel_times` | `"origin_id,destination_id"` → scheduled whole minutes. Only forward-ordered pairs within one direction are present; cross-direction pairs have no route meaning. |
| `network.dwell_times` | Logical stop ID → median GTFS dwell, floored to whole minutes. A negative source dwell is an input error. |
| `timetable_550.service_calendar` | Weekly GTFS rules and date exceptions for the service IDs used by the selected route, plus the active IDs for the selected date. |
| `requests.prebooked`, `requests.dynamic` | Maps from request ID to the KU Leuven request fields plus `direction`. |
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

## Demand scenario assumptions

Edit `src/reqreate-gen/demand_config.jl` to change demand-generation settings,
then rerun `generate.jl`. Lead-time metadata and scenario counts are derived
from these settings. Pre-booking leads use whole days; dynamic leads and pickup
half-windows use minutes. Scenario totals must be even and their per-cell
allocations must fit the candidate pool. Booking types and directions 0/1
remain evenly balanced. The values below describe the default settings.

The Julia-native pool is REQreate-inspired and samples only from the crawled
corridor and timetable; Python does not generate demand. Julia first enumerates
active trip and ordered origin/destination combinations whose scheduled run
covers the journey and whose ±5-minute pickup window lies within the
direction's operating hours. Dynamic combinations also need room for at least
a 5-minute booking lead after service starts. For each direction and booking
type, it draws 2,000 candidates uniformly from the eligible combinations.
Scheduled departure density and the number of feasible pairs shape the
desired-time distribution. The pool can contain repeated trip/OD combinations;
each candidate has a stable ID for request ordering.

| Scenario | Requests | Pre-booked | Dynamic | Direction split |
| --- | ---: | ---: | ---: | --- |
| Low | 50 | 25 | 25 | 25 each; booking/direction cells are balanced 12/13 deterministically |
| Base | 100 | 50 | 50 | 50 each; 25 in every booking/direction cell |
| High | 200 | 100 | 100 | 100 each; 50 in every booking/direction cell |

Pre-booked lead times are sampled uniformly from 1–3 days. Dynamic lead times
are sampled uniformly from 5–30 minutes and remain within service hours.
Every pickup window is desired time ±5 minutes. Candidate samples are
nested across scenarios and selected without replacement within each
booking/direction cell. This makes the three demand levels comparable while
keeping the total assumptions explicit. The fixed seed is 42.

The candidate pool stores source trip and source stop IDs so its provenance
can be inspected. It does not claim to estimate passenger behavior, demand
rates, transfers, accessibility, or ridership. Those assumptions should be
replaced when observed or survey-based data becomes available.
