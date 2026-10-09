/* Stop locations come from busline files; crawled route patterns supply their order. */
const busline_colors = ['#ba4f79', '#27858a', '#9a682d', '#7655a0', '#417f46'];
const busline_layers = new Map();
const busline_patterns = new Map();
const busline_stop_names = new Map();

/** Draw one straight segment between each pair of consecutive pattern stops. */
function draw_busline_lines(file_name) {
  const busline = busline_layers.get(file_name);
  const patterns = busline_patterns.get(file_name);
  if (!busline || !patterns) return;
  for (const line of busline.lines) busline.layer.removeLayer(line);
  busline.lines = patterns.map((pattern, index) => {
    const coordinates = pattern.stop_ids.map((id) => {
      const stop = busline.stops.get(`Stop_${id}`);
      if (!stop) throw new Error(`${file_name} is missing route stop Stop_${id}.`);
      return [stop.lat, stop.lon];
    });
    const line = L.polyline(coordinates, { color: busline.color, weight: 3, opacity: .8,
      dashArray: index ? '7 6' : undefined });
    line.bindPopup(pattern.label);
    line.addTo(busline.layer);
    return line;
  });
}

/** Match route patterns with the stops loaded from the same busline folder. */
function load_busline_patterns(data, file_name) {
  if (!Array.isArray(data.stops) || !Array.isArray(data.patterns) || !data.patterns.every((pattern) =>
    typeof pattern.label === 'string' && Array.isArray(pattern.stop_ids) &&
    pattern.stop_ids.length > 1 && pattern.stop_ids.every((id) => typeof id === 'string'))) {
    throw new Error(`${file_name} must contain stops and route patterns with ordered stop IDs.`);
  }
  const stop_file_name = file_name.replace(/^crawled_/, 'stops_');
  busline_patterns.set(stop_file_name, data.patterns);
  for (const stop of data.stops) busline_stop_names.set(stop.stop_id, stop.stop_name);
  draw_busline_lines(stop_file_name);
  if (typeof update_walking_stops === 'function') update_walking_stops();
}

/** Add or replace one stop file; keep each busline independently switchable. */
function load_busline(stops, file_name) {
  if (!Array.isArray(stops) || !stops.every((stop) =>
    typeof stop.name === 'string' && stop.type === 'location' &&
    ['mandatory', 'optional'].includes(stop.class) &&
    Number.isFinite(stop.lat) && Number.isFinite(stop.lon))) {
    throw new Error(`${file_name} must contain busline stops with names, classes, and coordinates.`);
  }

  const previous = busline_layers.get(file_name);
  if (previous) map.removeLayer(previous.layer);
  const color = previous?.color || busline_colors[busline_layers.size % busline_colors.length];
  const layer = L.layerGroup();
  for (const stop of stops) {
    const popup = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = stop.name;
    const details = document.createElement('div');
    details.textContent = `${file_name} · ${stop.class} stop`;
    popup.append(name, details);
    L.circleMarker([stop.lat, stop.lon], {
      radius: stop.class === 'mandatory' ? 6 : 4,
      color: '#fff', weight: 2, fillColor: color, fillOpacity: .95
    }).bindPopup(popup).addTo(layer);
  }
  busline_layers.set(file_name, { layer, color, count: stops.length,
    stops: new Map(stops.map((stop) => [stop.name, stop])), lines: [] });
  draw_busline_lines(file_name);
  layer.addTo(map);
  draw_busline_list();
  if (typeof update_walking_stops === 'function') update_walking_stops();
  document.getElementById('busline-error').hidden = true;
}

function draw_busline_list() {
  const list = document.getElementById('busline-list');
  list.replaceChildren();
  let count = 0;
  for (const [file_name, busline] of busline_layers) {
    count += busline.count;
    const label = document.createElement('label');
    const toggle = document.createElement('input');
    toggle.type = 'checkbox';
    toggle.checked = map.hasLayer(busline.layer);
    toggle.addEventListener('change', () => {
      if (toggle.checked) busline.layer.addTo(map);
      else map.removeLayer(busline.layer);
    });
    const key = document.createElement('i');
    key.className = 'busline-key';
    key.style.background = busline.color;
    key.style.boxShadow = `0 0 0 1px ${busline.color}`;
    const name = document.createElement('span');
    name.textContent = file_name;
    const total = document.createElement('small');
    total.textContent = `${busline.count} stops`;
    label.append(toggle, key, name, total);
    list.append(label);
  }
  document.getElementById('busline-count').textContent = `${count} stops`;
}
