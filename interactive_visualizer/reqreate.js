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
const network_layer = L.layerGroup().addTo(map);
const all_snap_layer = L.layerGroup().addTo(map);
const snap_layer = L.layerGroup().addTo(map);
const book_colors = { 0: '#e69247', 1: '#496cb1' };
const poi_colors = { amenity: '#b95750', shop: '#815ab2', leisure: '#308d6a', tourism: '#cf832f', healthcare: '#b15f83', historic: '#9c6b38', railway: '#385d8a', office: '#4e83a8', building: '#6c797b' };
const $ = (id) => document.getElementById(id);
let reqs = [];
let visible_reqs = [];
let req_by_id = new Map();
let selected_req = null;
let demand_bounds = null;
let walking_stops = [];
let graph_nodes = new Map();
let graph_kind = '';

/** Read OSMnx GraphML coordinates and edge geometry without another dependency. */
function read_graphml(xml) {
  if (xml.getElementsByTagName('parsererror').length) throw new Error('Invalid GraphML XML.');
  const elements = (name) => [...xml.getElementsByTagNameNS('*', name)];
  const keys = new Map(elements('key').map((key) => [key.getAttribute('id'), key.getAttribute('attr.name')]));
  const data = (element) => new Map([...element.getElementsByTagNameNS('*', 'data')]
    .map((item) => [keys.get(item.getAttribute('key')), item.textContent]));
  const nodes = new Map();
  for (const node of elements('node')) {
    const attributes = data(node);
    const lat = Number(attributes.get('y'));
    const lon = Number(attributes.get('x'));
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error(`GraphML node ${node.getAttribute('id')} has no coordinates.`);
    nodes.set(node.getAttribute('id'), [lat, lon]);
  }
  if (!nodes.size) throw new Error('GraphML has no nodes.');
  const edges = [];
  for (const edge of elements('edge')) {
    const from = nodes.get(edge.getAttribute('source'));
    const to = nodes.get(edge.getAttribute('target'));
    if (!from || !to) continue;
    const geometry = data(edge).get('geometry');
    const points = geometry?.match(/^LINESTRING \((.*)\)$/)?.[1]
      .split(/\s*,\s*/).map((pair) => pair.trim().split(/\s+/).map(Number).reverse());
    edges.push(points?.every((point) => point.length === 2 && point.every(Number.isFinite)) ? points : [from, to]);
  }
  return { nodes, edges };
}

function load_graphml(xml, kind, file_name) {
  const graph = read_graphml(xml);
  network_layer.clearLayers();
  graph_nodes = graph.nodes;
  graph_kind = kind;
  if (graph.edges.length) L.polyline(graph.edges, { color: '#607e78', weight: 1.5, opacity: .5, interactive: false }).addTo(network_layer);
  for (const [id, xy] of graph.nodes) {
    L.circleMarker(xy, { radius: 2.5, color: '#315d54', weight: 1, fillColor: '#cce4dc', fillOpacity: .85 })
      .bindPopup(`${kind} graph node ${id}`).addTo(network_layer);
  }
  $('graph-file-name').textContent = `${file_name} · ${graph.nodes.size} nodes · ${graph.edges.length} edges`;
  draw_saved_nodes();
  if (selected_req) show_req(selected_req, false);
  else if (!reqs.length) map.fitBounds(L.latLngBounds([...graph.nodes.values()]));
}

function draw_saved_nodes() {
  all_snap_layer.clearLayers();
  if (!graph_kind) return;
  for (const req of visible_reqs) {
    if (is_sfbs(req)) continue;
    for (const [endpoint, label, color] of [['origin', 'Pickup', '#1769a3'], ['destination', 'Dropoff', '#ac4b35']]) {
      const id = req[`${endpoint}node_${graph_kind}`];
      const xy = graph_nodes.get(String(id));
      if (!xy) continue;
      L.circleMarker(xy, { radius: 4, color: '#fff', weight: 1, fillColor: color, fillOpacity: .85 })
        .bindPopup(`${label} · ${graph_kind} node ${id} · request #${req.reqid}`)
        .on('click', () => show_req(req, false)).addTo(all_snap_layer);
    }
  }
}

function show_saved_nodes(req) {
  snap_layer.clearLayers();
  if (!graph_kind || is_sfbs(req)) return;
  for (const [endpoint, label, color] of [['origin', 'Pickup', '#1769a3'], ['destination', 'Dropoff', '#ac4b35']]) {
    const id = req[`${endpoint}node_${graph_kind}`];
    const xy = graph_nodes.get(String(id));
    if (!xy) continue;
    L.polyline([req[endpoint], xy], { color, weight: 2, dashArray: '3 5' }).addTo(snap_layer);
    L.circleMarker(xy, { radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1 })
      .bindPopup(`${label} · ${graph_kind} node ${id} · request #${req.reqid}`).addTo(snap_layer);
  }
}

/** Find a route pattern containing the saved SFBS boarding and alighting stops. */
function estimated_bus_trip(req) {
  for (const patterns of busline_patterns.values()) {
    for (const pattern of patterns) {
      const boarding_index = pattern.stop_ids.indexOf(req.boarding_stop_id);
      const alighting_index = pattern.stop_ids.indexOf(req.alighting_stop_id, boarding_index + 1);
      if (boarding_index >= 0 && alighting_index > boarding_index)
        return { pattern, boarding_index, alighting_index };
    }
  }
  return null;
}

function is_sfbs(req) {
  return 'boarding_stop_id' in req && 'alighting_stop_id' in req;
}

/** SFBS uses its saved stop pair; DARP has no bus access stops. */
function walk_access(req) {
  if (!is_sfbs(req)) return { trip: null, boarding: null, alighting: null };
  const boarding = walking_stops.find((stop) => stop.name === `Stop_${req.boarding_stop_id}`);
  const alighting = walking_stops.find((stop) => stop.name === `Stop_${req.alighting_stop_id}`);
  const trip = boarding && alighting ? estimated_bus_trip(req) : null;
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

function load_energy(data, file_name) {
  if (data.schema_version !== 2 || !Array.isArray(data.segments) ||
      data.segments.some((segment) => !Number.isFinite(segment.energy_kwh))) {
    throw new Error('Choose a schema-version-2 bus energy JSON with segment energy_kwh.');
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

/** Show a request as soon as its saved data is loaded. */
function show_initial_req() {
  if (!selected_req && reqs.length) show_req(reqs[0], false);
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
  if (!is_sfbs(req)) return `Node ${req[`${endpoint}node_drive`]}`;
  const id = req[endpoint === 'origin' ? 'boarding_stop_id' : 'alighting_stop_id'];
  return `${endpoint === 'origin' ? 'Board' : 'Alight'} at ${walk_stop_label({ name: `Stop_${id}` })}`;
}

function draw_req_timeline(req) {
  const timeline = $('req-timeline');
  timeline.hidden = false;
  if (req.pickup_from === undefined) {
    timeline.innerHTML = `<h3>Request timeline</h3><div class="timeline-track" role="img" aria-label="Order placed ${sec_label(req.order_place_time)}; earliest departure ${sec_label(req.earliest_departure)}; latest arrival ${sec_label(req.latest_arrival)}"><span class="timeline-order"></span></div>
      <div class="timeline-axis"><span>Order placed<br><strong>${sec_label(req.order_place_time)}</strong></span><span>Latest arrival<br><strong>${sec_label(req.latest_arrival)}</strong></span></div>
      <p>Pickup and dropoff windows are absent from this saved instance. Regenerate demand to include them.</p>`;
    return;
  }
  const { order_place_time: booked, pickup_from, pickup_to, dropoff_from, dropoff_to, service_time } = req;
  const broken = pickup_from - booked > 3 * (dropoff_to - pickup_from);
  const position = (second) => broken && second > pickup_from
    ? 28 + 72 * (second - pickup_from) / (dropoff_to - pickup_from)
    : broken ? 28 * (second - booked) / (pickup_from - booked)
      : 100 * (second - booked) / (dropoff_to - booked);
  timeline.innerHTML = `
    <h3>Request timeline</h3>
    <div class="timeline-track" role="img" aria-label="Order placed ${sec_label(booked)}. Pickup allowed ${sec_label(pickup_from)} to ${sec_label(pickup_to)}. Dropoff allowed ${sec_label(dropoff_from)} to ${sec_label(dropoff_to)}. Boarding and alighting service ${service_time} seconds each.">
      <span class="timeline-order"></span>
      <span class="timeline-pickup" style="left:${position(pickup_from)}%;width:${position(pickup_to) - position(pickup_from)}%"></span>
      <span class="timeline-dropoff" style="left:${position(dropoff_from)}%;width:${position(dropoff_to) - position(dropoff_from)}%"></span>
      ${broken ? '<span class="timeline-break" aria-hidden="true">//</span>' : ''}
    </div>
    <div class="timeline-axis"><span>Order placed<br><strong>${sec_label(booked)}</strong></span><span>Latest dropoff<br><strong>${sec_label(dropoff_to)}</strong></span></div>
    <div class="timeline-window"><i class="timeline-key pickup"></i><span>Pickup window</span><strong>${sec_label(pickup_from)}–${sec_label(pickup_to)}</strong></div>
    <div class="timeline-window"><i class="timeline-key dropoff"></i><span>Dropoff window</span><strong>${sec_label(dropoff_from)}–${sec_label(dropoff_to)}</strong></div>
    <p>Boarding and alighting service: ${service_time} s each, within their windows.${broken ? ' // marks a compressed booking lead interval.' : ''}</p>`;
}

/** Keep only the fields this view uses and check the REQreate file boundary. */
function read_reqs(data) {
  if (!data.requests || !Number.isInteger(data['num_data:']) ||
      Object.keys(data.requests).length !== data['num_data:']) {
    throw new Error('Choose a REQreate raw requests JSON with num_data: and requests.');
  }
  return Object.entries(data.requests).map(([key, req]) => {
    if (!Number.isInteger(req.reqid) || Number(key) !== req.reqid || ![0, 1].includes(req.is_prebooked) ||
        ('energy_kwh' in req && !Number.isFinite(req.energy_kwh)) ||
        !['origin', 'destination'].every((endpoint) => Array.isArray(req[endpoint]) &&
          req[endpoint].length === 2 && req[endpoint].every(Number.isFinite)) ||
        !['earliest_departure', 'latest_arrival', 'order_place_time', 'lead_time',
          'direct_distance', 'direct_travel_time'].every((field) => Number.isFinite(req[field]))) {
      throw new Error(`Request ${key} does not match the REQreate output format.`);
    }
    if (('boarding_stop_id' in req) !== ('alighting_stop_id' in req) || (is_sfbs(req)
      ? !['boarding_stop_id', 'alighting_stop_id'].every((field) => typeof req[field] === 'string' && req[field])
      : !['originnode_drive', 'destinationnode_drive'].every((field) => Number.isFinite(req[field])))) {
      throw new Error(`Request ${key} has invalid task endpoints.`);
    }
    const window_fields = ['pickup_from', 'pickup_to', 'dropoff_from', 'dropoff_to', 'service_time'];
    if (window_fields.some((field) => field in req) &&
        (!window_fields.every((field) => Number.isFinite(req[field])) ||
          req.pickup_from !== req.earliest_departure || req.dropoff_to !== req.latest_arrival ||
          req.pickup_from > req.pickup_to || req.dropoff_from > req.dropoff_to ||
          req.service_time < 0 || req.pickup_to - req.pickup_from < req.service_time ||
          req.dropoff_to - req.dropoff_from < req.service_time)) {
      throw new Error(`Request ${key} has invalid pickup or dropoff windows.`);
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
  show_saved_nodes(req);
  const color = book_colors[req.is_prebooked];
  L.polyline([req.origin, req.destination], { color, weight: 4, dashArray: '7 6' }).addTo(sel_layer);
  L.circleMarker(req.origin, { radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1, interactive: false })
    .addTo(sel_layer);
  L.circleMarker(req.destination, { radius: 8, color: '#fff', weight: 2, fillColor: '#17342f', fillOpacity: 1, interactive: false })
    .addTo(sel_layer);
  let walk_details = '';
  let trip = null;
  const energy_kwh = Number.isFinite(req.energy_kwh) ? req.energy_kwh : null;
  const bounds = [req.origin, req.destination];
  if (is_sfbs(req) && walking_stops.length) {
    const access = walk_access(req);
    trip = access.trip;
    const { boarding, alighting } = access;
    if (boarding && alighting) {
      const boarding_distance_m = walk_distance_m(req.origin, boarding);
      const alighting_distance_m = walk_distance_m(req.destination, alighting);
      const boarding_xy = [boarding.lat, boarding.lon];
      const alighting_xy = [alighting.lat, alighting.lon];
      for (const [stop, label, fillColor] of [[boarding, 'Board', '#1769a3'], [alighting, 'Alight', '#ac4b35']]) {
        L.circleMarker([stop.lat, stop.lon], { radius: 9, color: '#fff', weight: 2, fillColor, fillOpacity: 1 })
          .bindPopup(`${label} · saved bus stop ${stop.name.slice(5)} · request #${req.reqid}`).addTo(sel_layer);
      }
      L.polyline([req.origin, boarding_xy], { color: '#ba4f79', weight: 4, dashArray: '4 6' })
        .bindPopup(`Estimated walk to ${walk_stop_label(boarding)}: ${Math.round(boarding_distance_m)} m straight line`)
        .addTo(sel_layer);
      L.polyline([alighting_xy, req.destination], { color: '#ba4f79', weight: 4, dashArray: '4 6' })
        .bindPopup(`Estimated walk from ${walk_stop_label(alighting)}: ${Math.round(alighting_distance_m)} m straight line`)
        .addTo(sel_layer);
      if (trip) {
        const stops = new Map(walking_stops.map((stop) => [stop.name, stop]));
        const selected_order = trip.pattern.selected_stop_ids || trip.pattern.stop_ids;
        const boarding = selected_order.indexOf(req.boarding_stop_id);
        const alighting = selected_order.indexOf(req.alighting_stop_id, boarding + 1);
        const ride_ids = alighting > boarding && boarding >= 0
          ? selected_order.slice(boarding, alighting + 1)
          : trip.pattern.stop_ids.slice(trip.boarding_index, trip.alighting_index + 1);
        const ride_xy = ride_ids
          .map((id) => stops.get(`Stop_${id}`)).map((stop) => [stop.lat, stop.lon]);
        L.polyline(ride_xy, { color: '#246b59', weight: 5, opacity: .85 })
          .bindPopup('Estimated bus ride between the selected stops').addTo(sel_layer);
      }
      bounds.push(boarding_xy, alighting_xy);
      walk_details = `\nEstimated walk: ${Math.round(boarding_distance_m)} m to ${walk_stop_label(boarding)}; ` +
        `${Math.round(alighting_distance_m)} m from ${walk_stop_label(alighting)} (straight line)`;
      if (trip) walk_details += `\nEstimated route: ${trip.pattern.label} · ` +
        `${walk_stop_label(boarding)} → ${walk_stop_label(alighting)}`;
    }
  }
  $('energy-request').textContent = `Request #${req.reqid}`;
  $('selected-energy').textContent = energy_kwh === null ? '—' : energy_kwh.toFixed(2);
  $('selected-energy-note').textContent = energy_kwh === null ? 'This request has no saved energy_kwh value.' :
    'Saved energy estimate for this request.';
  $('req-details').hidden = false;
  $('req-details').textContent =
    `${is_sfbs(req) ? 'SFBS' : 'DARP'} request #${req.reqid} · ${req.is_prebooked ? 'Pre-booked' : 'Dynamic'}\n` +
    `${place_label(req, 'origin')} → ${place_label(req, 'destination')}\n` +
    `Earliest departure ${sec_label(req.earliest_departure)} · Latest arrival ${sec_label(req.latest_arrival)}\n` +
    `Booked ${sec_label(req.order_place_time)} · Lead ${Math.round(req.lead_time / 60)} min\n` +
    `Direct distance ${(req.direct_distance / 1000).toFixed(1)} km · ` +
    `Direct travel ${Math.round(req.direct_travel_time / 60)} min` +
    (!is_sfbs(req) && graph_kind ? `\n${graph_kind} pickup node ${req[`originnode_${graph_kind}`] ?? 'unavailable'} · ` +
      `dropoff node ${req[`destinationnode_${graph_kind}`] ?? 'unavailable'}` : '') + walk_details;
  draw_req_timeline(req);
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
    const energy_kwh = Number.isFinite(req.energy_kwh) ? req.energy_kwh : null;
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
  title.textContent = `${stop.node == null ? 'Passenger location' : `Node ${stop.node}`} · ${stop.endpoints.length} request${stop.endpoints.length === 1 ? '' : 's'}`;
  popup.append(title);
  for (const { req, endpoint } of stop.endpoints) {
    const trip = is_sfbs(req) && walking_stops.length ? walk_access(req).trip : null;
    const energy_kwh = Number.isFinite(req.energy_kwh) ? req.energy_kwh : null;
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
  snap_layer.clearLayers();
  if (!reqs.length) return;
  const until_sec = Number($('time-range').value);
  visible_reqs = reqs.filter((req) =>
    $(req.is_prebooked ? 'prebooked-check' : 'dynamic-check').checked &&
    req.earliest_departure <= until_sec);
  draw_saved_nodes();
  const stops = new Map();
  const pairs = new Map();
  for (const req of visible_reqs) {
    for (const endpoint of ['origin', 'destination']) {
      const xy = req[endpoint];
      const key = coord_key(xy);
      if (!stops.has(key)) stops.set(key, { xy, node: is_sfbs(req) ? null : req[`${endpoint}node_drive`], board: 0, alight: 0, endpoints: [] });
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
      if (!is_sfbs(req)) continue;
      const { boarding, alighting } = walk_access(req);
      if (!boarding || !alighting) continue;
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
    $('req-timeline').hidden = true;
    $('energy-request').textContent = 'No request selected';
    $('selected-energy').textContent = '—';
    $('selected-energy-note').textContent = 'Select a request to see its saved energy.';
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
  $('map-title').textContent = `${reqs[0] && is_sfbs(reqs[0]) ? 'SFBS' : 'DARP'} requests`;
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
