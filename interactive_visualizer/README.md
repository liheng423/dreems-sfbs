# Luxembourg bus demand explorer

Open `index.html` in a browser, then choose a scenario file such as `../data/instances/550_base.json`. No server or build step is needed. The page reads the selected file locally; it does not upload the JSON.

Use the route, booking type, and desired pickup time controls to filter demand. Circle size represents boardings plus alightings at each logical stop. Turn on origin–destination flows to see each request's straight line between its two stops. Select a stop or a request for details; drag and scroll the map to move and zoom.

To view road distances, choose the matching `data/distance_matrix_550.json`, then click **Show road distances**. The labels show directed road distances between consecutive stops in the selected route and direction. In **All routes**, a shared segment is labeled once; choose a direction to see its exact value. Selecting a request also shows its origin-to-destination road distance. Click **Hide road distances** to remove the labels. The labels come from the matrix's road routing estimates; the map still connects stops with straight lines.

The **Generator checks** section audits the loaded instance for request counts and IDs, per-pattern allocations, forward stop order, pickup windows, service-period bounds, and booking leads. Click an issue to inspect its request or candidate on the map; **Show flagged requests only** filters the map and request list. Selecting a request shows its lead time and matrix travel time.

For a deeper check, choose the matching `data/candidate_pool_*.json`. The viewer then checks every candidate's lead, stop order, source-stop mapping, pickup window, and scheduled travel-time feasibility. It rebuilds the scenario's selected candidate prefixes and request-ID order, then shows each selected candidate's ID, source trip, source stop IDs, destination departure time, and travel slack. Choose the matching `data/timetable_*.json` to compare each candidate's trip ID, stop IDs, and departure minutes with the source trip events. All three files stay local. Without a candidate pool, lead checks use the current generator defaults (pre-booked: 1–3 whole days; dynamic: 5–30 minutes).

Run `node interactive_visualizer/check.js` to check the viewer against the included low/base/high scenarios and injected generator faults.

Leaflet and OpenStreetMap map tiles load from the internet. The JSON file remains local. This viewer accepts schema-version-2 instance JSONs produced by `src/reqreate_gen/generate.jl` (including multi-line networks); it does not change or replace the Julia PDF script.
