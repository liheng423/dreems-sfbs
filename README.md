# DREEMS-SFBS

## Overview

This repository prepares and explores synthetic passenger demand for Luxembourg bus Route. It combines scheduled timetable and stop data from GTFS with OpenStreetMap road and service-area data, then uses REQreate to generate requests within the saved service area. Browser-based viewers show the requests alongside bus routes, stops, points of interest, and estimated trip energy. The repository also contains the source scripts, data snapshots, and checks used to produce and inspect these outputs.

## Repository structure
Brief guide to src/, data/, interactive_visualizer/, test/, and visualizations/.

## Prerequisites and installation
Python and Julia versions, dependencies, and the local REQreate checkout.

## Quick start

From the repository root, use the Python environment with the installed project dependencies:

```bash
.venv/bin/python main.py select-area
.venv/bin/python main.py generate-demand
```

`select-area` opens a local browser map and saves the chosen boundary and drive/walk graphs. It requires `data/crawled_550.json`. `generate-demand` reads the saved service area and writes the raw REQreate requests.

To explore the generated data, run `python3 -m http.server 8000` and open `http://localhost:8000/interactive_visualizer/`.

## Data pipeline
GTFS and OSM collection → service area → request generation → outputs.

## Visualization
What each viewer shows, how to launch it, and a link to interactive_visualizer/README.md.

## Configuration and outputs
Key TOML files, input data, generated files, and their units/formats.

## Checks and tests
Dependency check, Python tests, and visualizer checks.

## Data sources and limitations

- **GTFS:** Timetables and stops come from the Administration des transports publics' [Luxembourg GTFS dataset](https://data.public.lu/fr/datasets/horaires-et-arrets-des-transport-publics-gtfs/). The crawler uses the [1 October 2026 feed archive](https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20261001-055928/gtfs-20260930-20261212.zip).
- **REQreate:** Synthetic passenger requests are generated with [REQreate](https://github.com/michellqueiroz-ua/instance-generator) using the project's [local patch](src/reqreate/instance_generator.patch).

GTFS describes scheduled service; the generated passenger requests are synthetic rather than observed ridership.
