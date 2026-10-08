# Route 550 area demand from REQreate

`generate.py` creates 8,000 seeded requests within the saved Route 550 service
area. It uses `data/reqreate/service_area_550/service_area.geojson` and the
adjacent `drive.graphml` and `walk.graphml` files by default. The temporal and
minimum-distance settings come from `src/demand_busline/config_550.json`; its
bus-stop locations are ignored. REQreate samples each origin and destination
inside the polygon, within 500 m of a drive node, and snaps them to the road
and walking graphs. Directed driving distances follow OSM edge lengths.
Requests below 100 m or with unreachable endpoints are rejected.

The result is raw synthetic area demand. It has not been screened for Route 550
direction, timetable, corridor, or fleet feasibility. Driving time is estimated
from distance at REQreate's 5.56 m/s rate.

## Run

Use the `.instance-generator/` checkout at commit
`48e59a49aa97234d542f5275324a99f7b5cdce01` with Python 3.12. Apply
`instance_generator.patch` to a fresh checkout before installation:

```bash
git -C .instance-generator apply ../src/reqreate/instance_generator.patch
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
PYTHONPATH=.instance-generator .venv/bin/python src/reqreate/generate.py
.venv/bin/python test/test_reqreate_area.py
```

The default output is `data/reqreate/area_550/550_raw_requests.json` and
`550_raw_requests_metadata.json` beside it. The metadata records the seed,
source hashes, REQreate commit, and package versions. The older
`data/reqreate/550_raw_requests.json` is a historical stop-only pool and is not
written by this command.

Use `--requests 20 --out-dir /tmp/reqreate-smoke` for a short run. The area can
be changed with `--service-area path/to/service_area.geojson`; the adjacent
drive and walk GraphML files must describe that same area. Pass the output
directory to `test/test_reqreate_area.py` to check a custom run.
