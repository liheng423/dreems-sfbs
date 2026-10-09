# DREEMS-SFBS

## Overview

This repository prepares synthetic passenger demand for Luxembourg bus routes, with Route 550 as the current example. It combines a dated GTFS timetable with OpenStreetMap (OSM) roads and points of interest, generates requests with REQreate, and provides a browser map for inspecting the results. Requests are simulated; they are not observed ridership.

## Repository structure

| Path | Purpose |
| --- | --- |
| `src/crawler/busline/` | Extract a route's GTFS timetable and optionally query OSRM road distances. |
| `src/crawler/service_area/` | Select a polygon and save OSM drive and walk graphs. |
| `src/reqreate/` | Configure, generate, filter, and save synthetic requests. |
| `src/busline/` | Estimate bus route energy; see the [method notes](src/busline/README.md). |
| `src/output_adapters.py` | Define the shared data paths and output filenames. |
| `data/buslines/<route>/` | Route timetable (`businfo.json`), REQreate stops, and optional road distance and energy files. |
| `data/graphs/<name>/` | Service area GeoJSON, drive/walk GraphML files, and POIs. |
| `data/requests/<busline>_<graph>_<number>/` | A generated request pool and provenance metadata. |
| `interactive_visualizer/` | Static Route 550 request viewer and Node.js checks. |
| `test/` | Python checks for crawlers, request generation, and energy. |

The current workspace may contain Route 550 data examples; generate or supply the required inputs when they are absent.

## Prerequisites and installation

Use Python 3.12 and `uv` from the repository root. The commands below assume `python` points to your chosen Python 3.12 environment. Node.js is needed for the viewer checks. Install the published REQreate package and the other dependencies:

```bash
uv pip install --python python -r requirements.txt
python check_dependencies.py
```

The published `reqreate==0.1.1` does not include the fixes in the archived [local patch](src/reqreate/instance_generator.patch). A clean package-only installation succeeds, but `generate-demand` fails during REQreate's integer sampling with NumPy 2.x. The existing local environment may have those fixes applied; check the installed REQreate code before relying on it for generation.

## Quick start

From the repository root, create a Route 550 timetable and stop snapshot. The crawler downloads its configured GTFS archive unless `--gtfs-zip` points to a local copy:

```bash
python crawl_busline.py --route 550
python main.py select-area 550
```

The `select-area` argument names the saved map. For a separate map name, use `python main.py select-area test --busline 550` to display Route 550 stops, or omit `--busline` to draw without stops. In the browser page, draw a polygon and click **Save**. This writes `service_area.geojson`, `drive.graphml`, `walk.graphml`, and `pois.json` under `data/graphs/<map>/`. Stop the area-selection server with Ctrl+C after saving. To generate requests, run:

```bash
python main.py generate-demand --map 550 --requests 200
```

`--map` selects a saved map in `data/graphs/`; `550` is only the example map name. Without `--busline <route>`, the command lists available buslines and offers `0. Skip`, even when no buslines are available. Skipping keeps the area, minimum driving distance, and positive travel time filters; it disables only bus stop walking and scheduled-bus filters. Output uses `no_bus` in directory names and records `null` for the busline in metadata. Omit `--requests` to use the 20,000 candidate default. Each run creates a new directory such as `data/requests/550_550_0001/` with `raw_requests.json` and `raw_requests_metadata.json`. POIs are saved with the map, so request generation makes no Overpass call. Area selection requires OSM access. Existing maps need `pois.json` before generating requests. See the REQreate installation limitation above before starting generation.

To calculate Route 550's optional bus energy after saving the drive graph, run:

```bash
python src/busline/energy.py --route 550
```

This reads `data/buslines/550/businfo.json`, `data/graphs/550/drive.graphml`, and `src/busline/energy.toml`, then writes `data/buslines/550/energy.json`.

To launch the [interactive visualizer](interactive_visualizer/index.html) and open it in your browser, run:

```bash
python main.py visualize
```

Choose folders from `data/requests/`, `data/graphs/`, and `data/buslines/` in the page; it loads the matching files automatically. Stop the server with Ctrl+C. The visualizer needs no extra Python or Node.js packages; it loads Leaflet and map tiles from the internet.

## Data pipeline

1. `crawl_busline.py --route <route>` extracts the route's stops, patterns, and trips from GTFS into `data/buslines/<route>/businfo.json` and `stops.json`. Its default archive and service date are 1 and 6 October 2026, respectively; use `--gtfs-url` or `--gtfs-zip` and `--service-date` to select other inputs.
2. `main.py select-area <map> [--busline <route>]` shows optional route stops and saves the drawn boundary, OSM drive/walk graphs, and POIs in `data/graphs/<map>/`.
3. `main.py generate-demand --map <map> [--busline <route>]` samples requests using the saved map and POIs, applies area and trip filters, adds bus filters when a busline is selected, and saves a numbered request instance with metadata.

The GTFS and OSRM crawlers access external services unless given a local GTFS ZIP or routing server. The area selector also needs OSM access.

## Visualization

| Page | Input | What it shows |
| --- | --- | --- |
| [Request explorer](interactive_visualizer/index.html) | Selected folders under `data/requests/`, `data/graphs/`, and `data/buslines/` | Request locations, booking and time filters, origin–destination flows, service area, walking links, and estimated bus energy. |

The request explorer lists available folders from the local server. A selected request folder supplies `raw_requests.json`; a graph folder supplies `service_area.geojson` and `pois.json`; a busline folder supplies `stops.json`, `businfo.json`, and optional `energy.json`. Click a request point to see its estimated route and bus energy; shared locations list each request. It uses Leaflet and online OSM map tiles.

## Configuration and outputs

| File | Main settings or contents |
| --- | --- |
| [`src/reqreate/request_gen.toml`](src/reqreate/request_gen.toml) | Seed, candidate count, time distributions, and request attributes. |
| [`src/reqreate/maps/map_config.toml`](src/reqreate/maps/map_config.toml) | POI tags and spatial sampling grid. |
| [`src/reqreate/filters/filters.toml`](src/reqreate/filters/filters.toml) | Maximum walk distance, walk speed, and minimum trip distance. |
| [`src/busline/energy.toml`](src/busline/energy.toml) | Bus profile and temperature case for the illustrative energy calculation. |
| `data/requests/<busline>_<graph>_<number>/raw_requests.json` | Raw pool; `num_data:` is the retained count and `requests` is keyed by request ID. |
| `data/requests/<busline>_<graph>_<number>/raw_requests_metadata.json` | Selected busline and graph, package versions, seed, input hashes, and provenance. |

Request coordinate arrays use latitude/longitude; GeoJSON uses longitude/latitude. Road and walking distances are metres, request times are seconds relative to the service day, and energy is kWh.

## Checks and tests

```bash
python check_dependencies.py
python test/test_service_area.py
python test/test_reqreate_area.py
python test/test_busline_energy.py
node interactive_visualizer/check_reqreate.js
node interactive_visualizer/check_busline.js
```

The saved-request and viewer checks need their corresponding Route 550 data files. The area and energy checks above use small temporary graphs. Other focused checks live in `test/`.

## Abbreviations and naming

Use these spellings in new names and documentation. In Python, use lower-case `snake_case` and include units in a name when they matter, as in `walking_distance_m` and `travel_time_s`.

| Short form | Meaning | Naming example |
| --- | --- | --- |
| `cfg` | Configuration | `filter_cfg` |
| `req` | Passenger request | `req_id`, `reqs` |
| `net` | Road or service-area network | `area_net` |
| `GTFS` / `gtfs` | General Transit Feed Specification | `gtfs_json` |
| `OSM` / `osm` | OpenStreetMap | `osm_id` |
| `OSRM` / `osrm` | Open Source Routing Machine | `osrm_url` |
| `POI` / `poi` | Point of interest | `poi_path`, `pois` |
| `OD` / `od` | Origin–destination | `od_pair` |
| `m`, `mps`, `s`, `kwh` | Metres, metres per second, seconds, kilowatt-hours | `max_walking_distance_m`, `walking_speed_mps` |

## Data sources and limitations

- **GTFS:** Timetables and stops come from the Administration des transports publics' [Luxembourg GTFS dataset](https://data.public.lu/fr/datasets/horaires-et-arrets-des-transport-publics-gtfs/). The crawler uses the [1 October 2026 feed archive](https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20261001-055928/gtfs-20260930-20261212.zip).
- **REQreate:** Synthetic passenger requests use the published [REQreate package](https://pypi.org/project/reqreate/). The archived [local patch](src/reqreate/instance_generator.patch) is not applied to it.
- **OSM/OSRM:** Roads and POIs come from OSM. OSRM's routing profile may route cars differently from buses, and roads queried later than the GTFS archive can represent a different date.
- **Energy:** The selected bus profile is illustrative, not an identified vehicle for the selected route; see the [energy notes](src/busline/README.md).
