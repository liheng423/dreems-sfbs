/* REQreate's raw JSON is the viewer input; no corridor instance is required. */
const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView([49.52, 6.23], 11);
L.control.zoom({ position: 'topright' }).addTo(map);
L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
}).addTo(map);

const stop_layer = L.layerGroup().addTo(map);
const flow_layer = L.layerGroup().addTo(map);
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
    throw new Error('Choose the area_550 POIs JSON with features, coordinates, and OSM tags.');
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

function show_req(req) {
  selected_req = req;
  sel_layer.clearLayers();
  const color = book_colors[req.is_prebooked];
  L.polyline([req.origin, req.destination], { color, weight: 4, dashArray: '7 6' }).addTo(sel_layer);
  L.circleMarker(req.origin, { radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1 })
    .addTo(sel_layer);
  L.circleMarker(req.destination, { radius: 8, color: '#fff', weight: 2, fillColor: '#17342f', fillOpacity: 1 })
    .addTo(sel_layer);
  $('req-details').hidden = false;
  $('req-details').textContent =
    `Request #${req.reqid} · ${req.is_prebooked ? 'Pre-booked' : 'Dynamic'}\n` +
    `${place_label(req, 'origin')} → ${place_label(req, 'destination')}\n` +
    `Earliest departure ${sec_label(req.earliest_departure)} · Latest arrival ${sec_label(req.latest_arrival)}\n` +
    `Booked ${sec_label(req.time_stamp)} · Lead ${Math.round(req.lead_time / 60)} min\n` +
    `Direct distance ${(req.direct_distance / 1000).toFixed(1)} km · ` +
    `Direct travel ${Math.round(req.direct_travel_time / 60)} min`;
  map.fitBounds(L.latLngBounds([req.origin, req.destination]).pad(.35), { maxZoom: 14 });
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
    time.textContent = sec_label(req.earliest_departure);
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

function draw_map() {
  stop_layer.clearLayers();
  flow_layer.clearLayers();
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
      if (!stops.has(key)) stops.set(key, { xy, node: req[`${endpoint}node_drive`], board: 0, alight: 0 });
      stops.get(key)[endpoint === 'origin' ? 'board' : 'alight']++;
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
  for (const stop of stops.values()) {
    const total = stop.board + stop.alight;
    L.circleMarker(stop.xy, { radius: 4 + Math.sqrt(total), color: '#fff', weight: 2,
      fillColor: '#e79b50', fillOpacity: .8 })
      .bindPopup(`Node ${stop.node}<br>${stop.board} origins · ${stop.alight} destinations`)
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
  $('fit-button').disabled = false;
  $('file-name').textContent = file_name;
  $('file-error').hidden = true;
  $('map-title').textContent = 'REQreate raw requests';
  draw_map();
  map.fitBounds(demand_bounds.pad(.12));
}

$('inst-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    load_reqs(JSON.parse(await file.text()), file.name);
  } catch (error) {
    $('file-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('file-error').hidden = false;
  }
});
$('poi-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    load_pois(JSON.parse(await file.text()), file.name);
  } catch (error) {
    $('poi-file-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('poi-file-error').hidden = false;
  }
});
for (const id of ['prebooked-check', 'dynamic-check', 'flows-check', 'time-range']) {
  $(id).addEventListener(id === 'time-range' ? 'input' : 'change', draw_map);
}
$('req-id').addEventListener('change', () => {
  const req = req_by_id.get(Number($('req-id').value));
  if (req) show_req(req);
});
$('fit-button').addEventListener('click', () => map.fitBounds(demand_bounds.pad(.12)));

/** Load the area_550 pair automatically when the page is served over HTTP. */
if (location.protocol !== 'file:') {
  fetch('../data/reqreate/area_550/550_raw_requests.json')
    .then((response) => response.json())
    .then((data) => load_reqs(data, 'area_550/550_raw_requests.json'))
    .catch((error) => { $('file-error').textContent = error.message; $('file-error').hidden = false; });
  fetch('../data/reqreate/area_550/550_pois.json')
    .then((response) => response.json())
    .then((data) => load_pois(data, 'area_550/550_pois.json'))
    .catch((error) => { $('poi-file-error').textContent = error.message; $('poi-file-error').hidden = false; });
} else {
  $('file-name').textContent = 'Choose data/reqreate/area_550/550_raw_requests.json';
  $('poi-file-name').textContent = 'Choose data/reqreate/area_550/550_pois.json';
}
