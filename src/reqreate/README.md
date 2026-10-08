# Route 550 area demand from REQreate

`generate.py` creates the configured number of seeded candidate requests within the saved Route 550 service
area. `src/reqreate/config_550.toml` sets the service area and stop paths,
output paths and filenames, candidate count, seed, POI grid, temporal
distribution, POI tags, and POI-guided trip-distance distribution.
`filters/filters.toml` sets the minimum trip distance and maximum walking
distance to a Route 550 stop. `data/busline/stops_550.json` contains the stop locations.
The generator uses `area_network.py` for graph routing, `pois.py` for POI caching and sampling zones,
`utils/walking_distance.py` for stop access, and `pool_output.py` for the pool and provenance files.
The area folder must contain
`service_area.geojson`, `drive.graphml`, and `walk.graphml`. REQreate's
`method_pois` algorithm divides the area into a 25 × 25 grid, selects one
endpoint's zone in proportion to its eligible OpenStreetMap point-of-interest
(POI) count, and samples the other endpoint at a configured radial distance.
It randomly reverses the origin and destination roles. Sampling does not use the walking limit.
After generation, requests are kept only when both endpoints are within the configured walking
distance of a stop:
the distance follows the walking graph, with short straight-line links from
the point and stop to their nearest walking nodes. Directed driving distances
follow OSM edge lengths.
Requests below 100 m or with unreachable endpoints are rejected.

The first run downloads the configured POI categories through OSMnx/Overpass,
using the same OSM data source as REQreate's upstream POI retriever. The
`550_pois.json` catalogue beside the request pool records each place's OSM ID,
name, tags, and coordinates; later runs reuse this snapshot while the area,
walk graph, tags, stops, and walking limit stay the same. Changing any of those inputs refreshes the POIs
automatically.
Areas with more eligible POIs have greater selection probability. The
configured radial distance is uniform from 500 m to 15 km; it is an explicit
assumption, not a fit to observed trip distances. POI counts are a spatial
proxy, not measured passenger demand. An Overpass connection is required when
refreshing the snapshot.

The result contains up to the configured candidate count of raw synthetic requests after the walking filter. It has not been screened for Route 550
direction, timetable, corridor, or fleet feasibility. Driving time is estimated
from distance at REQreate's 5.56 m/s rate.

## Filter interface

`filters/filters.py` defines `CandidateFilter[Candidate]`: a callable with
signature `(candidate, net, cfg) -> bool`. `candidate` is a pandas feature row
for POI filters and a generated request dictionary for request filters. `net`
is the loaded `AreaNetwork`; `cfg` is the parsed configuration. Return `True`
to keep the candidate and `False` to reject it. Predicates must not modify
these inputs.

Register each function in `POI_FILTERS` or `REQUEST_FILTERS`. `passes_filters`
calls them in tuple order and stops at the first `False`. For example, a new
request condition follows this form:

```python
def request_has_required_value(req: dict, net: AreaNetwork, cfg: dict) -> bool:
    return req["required_value"] > 0

REQUEST_FILTERS = (*REQUEST_FILTERS, request_has_required_value)
```

Changing `POI_FILTERS` refreshes the POI cache. REQreate also applies the
minimum driving distance and positive travel-time constraints while sampling,
so it can retry candidates before this interface checks retained requests.

## Run

Use the `.instance-generator/` checkout at commit
`48e59a49aa97234d542f5275324a99f7b5cdce01` with Python 3.12. Apply
`instance_generator.patch` to a fresh checkout before installation:

```bash
git -C .instance-generator apply ../src/reqreate/instance_generator.patch
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python src/reqreate/generate.py
.venv/bin/python test/test_reqreate_area.py
```

The local REQreate checkout is installed into `.venv`, so moving its source
directory does not leave an editable install pointing at the old path. Its
Python import is `REQreate` (capitalized); `reqreate` is the CLI command.

The configured output is `data/reqreate/area_550/550_raw_requests.json` with
`550_pois.json` and `550_raw_requests_metadata.json` beside it. The metadata records candidate and retained request counts, the seed,
source hashes, REQreate commit, and package versions. The older
`data/reqreate/550_raw_requests.json` is a historical stop-only pool and is not
written by this command.

For a short run, temporarily set `requests = 20` and `output_dir` in
`config_550.toml`, then run the same command. Paths in the TOML files are
relative to the repository root. The drive and walk GraphML files must sit
beside the configured service-area GeoJSON and describe the same area.
