/* REQreate requests, GTFS stops, and bus energy are loaded from their source files. */
const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView([49.52, 6.23], 11);
L.control.zoom({ position: 'topright' }).addTo(map);
L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
}).addTo(map);

const stop_layer = L.layerGroup().addTo(map);
const flow_layer = L.layerGroup().addTo(map);
const walk_layer = L.layerGroup().addTo(map);
const poi_layer = L.layerGroup().addTo(map);
const sel_layer = L.layerGroup().addTo(map);
const book_colors = { 0: '#e69247', 1: '#496cb1' };
const poi_colors = { amenity: '#b95750', shop: '#815ab2', leisure: '#308d6a', tourism: '#cf832f', office: '#4e83a8', building: '#6c797b' };
const $ = (id) => document.getElementById(id);
let reqs = [];
let visible_reqs = [];
let req_by_id = new Map();
let selected_req = null;
let demand_bounds = null;
let walking_stops = [];
let energy_segments = new Map();

/** Use the nearest loaded bus stop for an estimated straight-line walking link. */
function nearest_walk_stop(xy) {
  let nearest = walking_stops[0];
  let nearest_distance_m = walk_distance_m(xy, nearest);
  for (const stop of walking_stops.slice(1)) {
    const distance_m = walk_distance_m(xy, stop);
    if (distance_m < nearest_distance_m) {
      nearest = stop;
      nearest_distance_m = distance_m;
    }
  }
  return nearest;
}

/** Pick the walk-access pair with the shortest combined straight-line distance on a forward pattern. */
function estimated_bus_trip(req) {
  const origin_distance = new Map(walking_stops.map((stop) => [stop.name, walk_distance_m(req.origin, stop)]));
  const destination_distance = new Map(walking_stops.map((stop) => [stop.name, walk_distance_m(req.destination, stop)]));
  let best = null;
  for (const patterns of busline_patterns.values()) {
    for (const pattern of patterns) {
      for (let boarding_index = 0; boarding_index < pattern.stop_ids.length - 1; boarding_index++) {
        for (let alighting_index = boarding_index + 1; alighting_index < pattern.stop_ids.length; alighting_index++) {
          const boarding_name = `Stop_${pattern.stop_ids[boarding_index]}`;
          const alighting_name = `Stop_${pattern.stop_ids[alighting_index]}`;
          if (!origin_distance.has(boarding_name) || !destination_distance.has(alighting_name)) continue;
          const distance_m = origin_distance.get(boarding_name) + destination_distance.get(alighting_name);
          if (!best || distance_m < best.distance_m) {
            best = { pattern, boarding_index, alighting_index, boarding_name, alighting_name, distance_m };
          }
        }
      }
    }
  }
  return best;
}

/** Use the shortest forward bus trip when available, otherwise the nearest stops. */
function walk_access(req) {
  const trip = estimated_bus_trip(req);
  const boarding = trip
    ? walking_stops.find((stop) => stop.name === trip.boarding_name)
    : nearest_walk_stop(req.origin);
  const alighting = trip
    ? walking_stops.find((stop) => stop.name === trip.alighting_name)
    : nearest_walk_stop(req.destination);
  return { trip, boarding, alighting };
}

function walk_distance_m(xy, stop) {
  const latitude = xy[0] * Math.PI / 180;
  const stop_latitude = stop.lat * Math.PI / 180;
  const lat_delta = stop_latitude - latitude;
  const lon_delta = (stop.lon - xy[1]) * Math.PI / 180;
  const haversine = Math.sin(lat_delta / 2) ** 2 +
    Math.cos(latitude) * Math.cos(stop_latitude) * Math.sin(lon_delta / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(haversine));
}

/** Sum bus vehicle energy across the selected pattern's directed stop segments. */
function req_energy_kwh(trip) {
  if (!trip || !energy_segments.size) return null;
  let energy_kwh = 0;
  for (let index = trip.boarding_index; index < trip.alighting_index; index++) {
    const segment_kwh = energy_segments.get(`${trip.pattern.pattern_id}|${index}`);
    if (segment_kwh === undefined) return null;
    energy_kwh += segment_kwh;
  }
  return energy_kwh;
}

function load_energy(data, file_name) {
  if (data.schema_version !== 2 || !Array.isArray(data.segments) ||
      data.segments.some((segment) => !Number.isFinite(segment.energy_kwh))) {
    throw new Error('Choose a schema-version-2 bus energy JSON with segment energy_kwh.');
  }
  energy_segments = new Map();
  const segments_by_pattern = new Map();
  for (const segment of data.segments) {
    if (!segments_by_pattern.has(segment.pattern_id)) segments_by_pattern.set(segment.pattern_id, []);
    const segments = segments_by_pattern.get(segment.pattern_id);
    energy_segments.set(`${segment.pattern_id}|${segments.length}`, segment.energy_kwh);
    segments.push(segment);
  }
  $('energy-name').textContent = file_name;
  $('energy-status').textContent = data.status;
  $('energy-error').hidden = true;
  if (selected_req) show_req(selected_req);
  draw_list();
  show_initial_req();
}

function update_walking_stops() {
  walking_stops = [...busline_layers.values()].flatMap((busline) => [...busline.stops.values()]);
  draw_map();
  show_initial_req();
}

/** Fill the panel as soon as the three inputs needed for an estimate are ready. */
function show_initial_req() {
  if (!selected_req && reqs.length && walking_stops.length && busline_patterns.size && energy_segments.size) {
    show_req(reqs[0], false);
  }
}

function walk_stop_label(stop) {
  return busline_stop_names.get(stop.name.slice(5)) || stop.name;
}

/** Format seconds on the service-day axis, including previous-day bookings. */
function sec_label(sec) {
  const day = Math.floor(sec / 86400);
  const remainder = sec - day * 86400;
  const hour = Math.floor(remainder / 3600);
  const minute = Math.floor((remainder % 3600) / 60);
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}${day ? ` ${day > 0 ? '+' : ''}${day}d` : ''}`;
}

function coord_key(xy) {
  return xy.join(',');
}

function place_label(req, endpoint) {
  return `Node ${req[`${endpoint}node_drive`]}`;
}

/** Keep only the fields this view uses and check the REQreate file boundary. */
function read_reqs(data) {
  if (!data.requests || !Number.isInteger(data['num_data:']) ||
      Object.keys(data.requests).length !== data['num_data:']) {
    throw new Error('Choose a REQreate raw requests JSON with num_data: and requests.');
  }
  return Object.entries(data.requests).map(([key, req]) => {
    if (!Number.isInteger(req.reqid) || Number(key) !== req.reqid || ![0, 1].includes(req.is_prebooked) ||
        !['origin', 'destination'].every((endpoint) => Array.isArray(req[endpoint]) &&
          req[endpoint].length === 2 && req[endpoint].every(Number.isFinite)) ||
        !['originnode_drive', 'destinationnode_drive', 'earliest_departure', 'latest_arrival', 'time_stamp', 'lead_time',
          'direct_distance', 'direct_travel_time'].every((field) => Number.isFinite(req[field]))) {
      throw new Error(`Request ${key} does not match the REQreate output format.`);
    }
    return req;
  });
}

/** A POI can have several OSM tags; use the most descriptive one for its map color. */
function poi_type(poi) {
  return Object.keys(poi_colors).find((type) => type !== 'building' && type in poi.tags) || 'building';
}

function load_pois(data, file_name) {
  if (!Array.isArray(data.features) || !data.features.every((poi) =>
    Number.isFinite(poi.lat) && Number.isFinite(poi.lon) && poi.tags &&
    Object.keys(poi.tags).some((type) => type in poi_colors))) {
    throw new Error('The selected POIs JSON needs features, coordinates, and OSM tags.');
  }
  poi_layer.clearLayers();
  const counts = new Map();
  const tag_counts = new Map();
  for (const poi of data.features) {
    const type = poi_type(poi);
    counts.set(type, (counts.get(type) || 0) + 1);
    const details = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = poi.name || `OSM ${poi.osm_type} ${poi.osm_id}`;
    details.append(name);
    for (const [tag, value] of Object.entries(poi.tags)) {
      const label = `${tag}: ${value}`;
      tag_counts.set(label, (tag_counts.get(label) || 0) + 1);
      const row = document.createElement('div');
      row.textContent = label;
      details.append(row);
    }
    const walkability = document.createElement('div');
    walkability.textContent = poi.walkable ? 'Walkable' : 'Not walkable';
    details.append(walkability);
    L.circleMarker([poi.lat, poi.lon], { radius: 5, color: '#fff', weight: 1,
      fillColor: poi_colors[type], fillOpacity: .95 })
      .bindPopup(details).addTo(poi_layer);
  }
  $('poi-count').textContent = `${data.features.length} POIs`;
  const types = $('poi-types');
  types.replaceChildren();
  for (const [type, color] of Object.entries(poi_colors)) {
    const row = document.createElement('div');
    const key = document.createElement('i');
    key.className = 'poi-key';
    key.style.background = color;
    const label = document.createElement('span');
    label.textContent = type;
    const count = document.createElement('strong');
    count.textContent = counts.get(type) || 0;
    row.append(key, label, count);
    types.append(row);
  }
  const tags = $('poi-tags');
  tags.replaceChildren();
  for (const [label, count] of [...tag_counts].sort(([left], [right]) => left.localeCompare(right))) {
    const row = document.createElement('div');
    row.textContent = `${label} · ${count}`;
    tags.append(row);
  }
  $('poi-tag-count').textContent = `(${tag_counts.size})`;
  $('poi-file-name').textContent = file_name;
  $('poi-file-error').hidden = true;
}

function show_req(req, fit_map = true) {
  selected_req = req;
  sel_layer.clearLayers();
  const color = book_colors[req.is_prebooked];
  L.polyline([req.origin, req.destination], { color, weight: 4, dashArray: '7 6' }).addTo(sel_layer);
  L.circleMarker(req.origin, { radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1, interactive: false })
    .addTo(sel_layer);
  L.circleMarker(req.destination, { radius: 8, color: '#fff', weight: 2, fillColor: '#17342f', fillOpacity: 1, interactive: false })
    .addTo(sel_layer);
  let walk_details = '';
  let trip = null;
  let energy_kwh = null;
  const bounds = [req.origin, req.destination];
  if (walking_stops.length) {
    const access = walk_access(req);
    trip = access.trip;
    const { boarding, alighting } = access;
    const boarding_distance_m = walk_distance_m(req.origin, boarding);
    const alighting_distance_m = walk_distance_m(req.destination, alighting);
    const boarding_xy = [boarding.lat, boarding.lon];
    const alighting_xy = [alighting.lat, alighting.lon];
    L.polyline([req.origin, boarding_xy], { color: '#ba4f79', weight: 4, dashArray: '4 6' })
      .bindPopup(`Estimated walk to ${walk_stop_label(boarding)}: ${Math.round(boarding_distance_m)} m straight line`)
      .addTo(sel_layer);
    L.polyline([alighting_xy, req.destination], { color: '#ba4f79', weight: 4, dashArray: '4 6' })
      .bindPopup(`Estimated walk from ${walk_stop_label(alighting)}: ${Math.round(alighting_distance_m)} m straight line`)
      .addTo(sel_layer);
    if (trip) {
      const stops = new Map(walking_stops.map((stop) => [stop.name, stop]));
      const ride_xy = trip.pattern.stop_ids.slice(trip.boarding_index, trip.alighting_index + 1)
        .map((id) => stops.get(`Stop_${id}`)).map((stop) => [stop.lat, stop.lon]);
      L.polyline(ride_xy, { color: '#246b59', weight: 5, opacity: .85 })
        .bindPopup('Estimated bus ride between the selected stops').addTo(sel_layer);
    }
    bounds.push(boarding_xy, alighting_xy);
    walk_details = `\nEstimated walk: ${Math.round(boarding_distance_m)} m to ${walk_stop_label(boarding)}; ` +
      `${Math.round(alighting_distance_m)} m from ${walk_stop_label(alighting)} (straight line)`;
    if (trip) walk_details += `\nEstimated route: ${trip.pattern.label} · ` +
      `${walk_stop_label(boarding)} → ${walk_stop_label(alighting)}`;
    energy_kwh = req_energy_kwh(trip);
    if (energy_segments.size) walk_details += `\nEstimated bus trip energy: ${energy_kwh === null ? 'unavailable' : `${energy_kwh.toFixed(2)} kWh`}`;
  }
  $('energy-request').textContent = `Request #${req.reqid}`;
  $('selected-energy').textContent = energy_kwh === null ? '—' : energy_kwh.toFixed(2);
  $('selected-energy-note').textContent = !energy_segments.size ? 'Load the bus energy JSON to calculate this value.' :
    !trip ? 'No forward bus route matches this request.' :
    energy_kwh === null ? 'No energy segment matches this estimated bus trip.' :
    'Vehicle energy over the estimated boarding-to-alighting interval.';
  $('req-details').hidden = false;
  $('req-details').textContent =
    `Request #${req.reqid} · ${req.is_prebooked ? 'Pre-booked' : 'Dynamic'}\n` +
    `${place_label(req, 'origin')} → ${place_label(req, 'destination')}\n` +
    `Earliest departure ${sec_label(req.earliest_departure)} · Latest arrival ${sec_label(req.latest_arrival)}\n` +
    `Booked ${sec_label(req.time_stamp)} · Lead ${Math.round(req.lead_time / 60)} min\n` +
    `Direct distance ${(req.direct_distance / 1000).toFixed(1)} km · ` +
    `Direct travel ${Math.round(req.direct_travel_time / 60)} min` + walk_details;
  if (fit_map) map.fitBounds(L.latLngBounds(bounds).pad(.35), { maxZoom: 14 });
  document.querySelectorAll('.req-item').forEach((button) =>
    button.classList.toggle('active', Number(button.dataset.reqId) === req.reqid));
}

function draw_list() {
  const list = $('req-list');
  list.replaceChildren();
  $('list-count').textContent = `${visible_reqs.length} visible`;
  const fragment = document.createDocumentFragment();
  for (const req of [...visible_reqs].sort((left, right) => left.earliest_departure - right.earliest_departure).slice(0, 200)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'req-item';
    button.dataset.reqId = req.reqid;
    const type = document.createElement('span');
    type.className = `req-type ${req.is_prebooked ? 'prebooked' : 'dynamic'}`;
    const main = document.createElement('span');
    main.className = 'req-main';
    main.textContent = `#${req.reqid}  ${place_label(req, 'origin')} → ${place_label(req, 'destination')}`;
    const time = document.createElement('span');
    time.className = 'req-time';
    const energy_kwh = walking_stops.length ? req_energy_kwh(estimated_bus_trip(req)) : null;
    time.textContent = `${sec_label(req.earliest_departure)}${energy_kwh === null ? '' : ` · ${energy_kwh.toFixed(2)} kWh`}`;
    button.append(type, main, time);
    button.addEventListener('click', () => show_req(req));
    fragment.append(button);
  }
  list.append(fragment);
  if (visible_reqs.length > 200) {
    const note = document.createElement('p');
    note.className = 'hint';
    note.textContent = 'Showing the earliest 200. Enter an ID to inspect any request.';
    list.append(note);
  }
}

/** Show the requests sharing one map location, with their route and energy. */
function request_point_popup(stop) {
  const popup = document.createElement('div');
  popup.className = 'request-point-popup';
  const title = document.createElement('strong');
  title.textContent = `Node ${stop.node} · ${stop.endpoints.length} request${stop.endpoints.length === 1 ? '' : 's'}`;
  popup.append(title);
  for (const { req, endpoint } of stop.endpoints) {
    const trip = walking_stops.length ? estimated_bus_trip(req) : null;
    const energy_kwh = req_energy_kwh(trip);
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = `#${req.reqid} · ${endpoint}\n` +
      `${trip ? trip.pattern.label : 'Route unavailable'}\n` +
      `${energy_kwh === null ? 'Energy unavailable' : `${energy_kwh.toFixed(2)} kWh`}`;
    button.addEventListener('click', () => show_req(req, false));
    popup.append(button);
  }
  return popup;
}

function draw_map() {
  stop_layer.clearLayers();
  flow_layer.clearLayers();
  walk_layer.clearLayers();
  sel_layer.clearLayers();
  if (!reqs.length) return;
  const until_sec = Number($('time-range').value);
  visible_reqs = reqs.filter((req) =>
    $(req.is_prebooked ? 'prebooked-check' : 'dynamic-check').checked &&
    req.earliest_departure <= until_sec);
  const stops = new Map();
  const pairs = new Map();
  for (const req of visible_reqs) {
    for (const endpoint of ['origin', 'destination']) {
      const xy = req[endpoint];
      const key = coord_key(xy);
      if (!stops.has(key)) stops.set(key, { xy, node: req[`${endpoint}node_drive`], board: 0, alight: 0, endpoints: [] });
      const stop = stops.get(key);
      stop[endpoint === 'origin' ? 'board' : 'alight']++;
      stop.endpoints.push({ req, endpoint });
    }
    const od_key = `${coord_key(req.origin)}|${coord_key(req.destination)}|${req.is_prebooked}`;
    if (!pairs.has(od_key)) pairs.set(od_key, { origin: req.origin, destination: req.destination,
      book_type: req.is_prebooked, count: 0 });
    pairs.get(od_key).count++;
  }
  if ($('flows-check').checked) {
    for (const pair of pairs.values()) {
      L.polyline([pair.origin, pair.destination], {
        color: book_colors[pair.book_type], weight: Math.min(7, 1 + Math.sqrt(pair.count) / 2), opacity: .38
      }).bindPopup(`${pair.count} ${pair.book_type ? 'pre-booked' : 'dynamic'} requests`).addTo(flow_layer);
    }
  }
  if ($('walks-check').checked && walking_stops.length) {
    for (const req of visible_reqs) {
      const { boarding, alighting } = walk_access(req);
      L.polyline([req.origin, [boarding.lat, boarding.lon]], { color: '#ba4f79', weight: 2, opacity: .35, dashArray: '4 6' })
        .on('click', () => show_req(req)).addTo(walk_layer);
      L.polyline([[alighting.lat, alighting.lon], req.destination], { color: '#ba4f79', weight: 2, opacity: .35, dashArray: '4 6' })
        .on('click', () => show_req(req)).addTo(walk_layer);
    }
  }
  for (const stop of stops.values()) {
    const total = stop.board + stop.alight;
    L.circleMarker(stop.xy, { radius: 4 + Math.sqrt(total), color: '#fff', weight: 2,
      fillColor: '#e79b50', fillOpacity: .8 })
      .bindPopup(() => request_point_popup(stop))
      .on('click', () => show_req(stop.endpoints[0].req, false))
      .addTo(stop_layer);
  }
  $('req-count').textContent = visible_reqs.length;
  $('stop-count').textContent = stops.size;
  $('pair-count').textContent = new Set(visible_reqs.map((req) => `${coord_key(req.origin)}|${coord_key(req.destination)}`)).size;
  $('time-value').textContent = sec_label(until_sec);
  $('map-kicker').textContent = `${visible_reqs.length} OF ${reqs.length} REQUESTS`;
  draw_list();
  if (selected_req && visible_reqs.includes(selected_req)) show_req(selected_req);
  else {
    selected_req = null;
    $('req-details').hidden = true;
    $('energy-request').textContent = 'No request selected';
    $('selected-energy').textContent = '—';
    $('selected-energy-note').textContent = 'Select a request to see its bus trip energy.';
  }
}

function load_reqs(data, file_name) {
  const parsed = read_reqs(data);
  reqs = parsed;
  req_by_id = new Map(reqs.map((req) => [req.reqid, req]));
  selected_req = null;
  demand_bounds = L.latLngBounds(reqs.flatMap((req) => [req.origin, req.destination]));
  $('time-range').max = Math.ceil(Math.max(...reqs.map((req) => req.earliest_departure)) / 3600) * 3600;
  $('time-range').value = $('time-range').max;
  $('time-range').disabled = false;
  $('req-id').disabled = false;
  $('req-id').value = '';
  $('prebooked-check').checked = true;
  $('dynamic-check').checked = true;
  $('flows-check').checked = false;
  $('walks-check').checked = false;
  $('fit-button').disabled = false;
  $('file-name').textContent = file_name;
  $('file-error').hidden = true;
  $('map-title').textContent = 'REQreate raw requests';
  draw_map();
  show_initial_req();
  map.fitBounds(demand_bounds.pad(.12));
}

for (const id of ['prebooked-check', 'dynamic-check', 'flows-check', 'walks-check', 'time-range']) {
  $(id).addEventListener(id === 'time-range' ? 'input' : 'change', draw_map);
}
$('req-id').addEventListener('change', () => {
  const req = req_by_id.get(Number($('req-id').value));
  if (req) show_req(req);
});
$('fit-button').addEventListener('click', () => map.fitBounds(demand_bounds.pad(.12)));
