/* Select data folders served from the repository root. */

let graph_layer = null;

/** Read folder names from Python's local directory listing. */
async function folder_names(kind) {
  const response = await fetch(`../data/${kind}/`);
  if (!response.ok) throw new Error(`Cannot list data/${kind}/`);
  const listing = new DOMParser().parseFromString(await response.text(), 'text/html');
  return [...listing.querySelectorAll('a[href]')]
    .map((link) => link.getAttribute('href'))
    .filter((href) => /^[^./][^/]*\/$/.test(href) && (kind !== 'requests' || href !== '_cache/'))
    .map((href) => decodeURIComponent(href.slice(0, -1)))
    .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
}

async function folder_json(kind, folder, file) {
  const response = await fetch(`../data/${kind}/${encodeURIComponent(folder)}/${file}`);
  if (!response.ok) throw new Error(`Cannot load data/${kind}/${folder}/${file}`);
  return response.json();
}

function show_source_error(id, error) {
  $(id).textContent = error.message;
  $(id).hidden = false;
}

/** Load one saved request pool. */
$('request-folder').addEventListener('change', async (event) => {
  const folder = event.target.value;
  if (!folder) return;
  try {
    const pool = await folder_json('requests', folder, 'raw_requests.json');
    if (event.target.value !== folder) return;
    load_reqs(pool, `data/requests/${folder}/raw_requests.json`);
  } catch (error) {
    show_source_error('file-error', error);
  }
});

/** Display the selected graph's boundary and POIs. */
$('graph-folder').addEventListener('change', async (event) => {
  const folder = event.target.value;
  if (graph_layer) map.removeLayer(graph_layer);
  graph_layer = null;
  $('graph-name').textContent = '';
  if (!folder) return;
  try {
    const [area, pois] = await Promise.all([
      folder_json('graphs', folder, 'service_area.geojson'),
      folder_json('graphs', folder, 'pois.json')
    ]);
    if (event.target.value !== folder) return;
    graph_layer = L.geoJSON(area, { style: { color: '#27858a', weight: 2, fillOpacity: .06 } }).addTo(map);
    load_pois(pois, `data/graphs/${folder}/pois.json`);
    $('graph-name').textContent = `data/graphs/${folder}/service_area.geojson`;
    $('graph-error').hidden = true;
    if (!reqs.length) map.fitBounds(graph_layer.getBounds());
  } catch (error) {
    show_source_error('graph-error', error);
  }
});

/** Load stops, route patterns, and optional energy from one busline directory. */
$('busline-folder').addEventListener('change', async (event) => {
  const folder = event.target.value;
  for (const busline of busline_layers.values()) map.removeLayer(busline.layer);
  busline_layers.clear();
  busline_patterns.clear();
  busline_stop_names.clear();
  energy_segments = new Map();
  $('energy-name').textContent = '';
  $('energy-status').textContent = '';
  draw_busline_list();
  update_walking_stops();
  if (!folder) return;
  try {
    const [stops, businfo] = await Promise.all([
      folder_json('buslines', folder, 'stops.json'),
      folder_json('buslines', folder, 'businfo.json')
    ]);
    if (event.target.value !== folder) return;
    load_busline(stops, `stops_${folder}.json`);
    load_busline_patterns(businfo, `crawled_${folder}.json`);
    $('busline-error').hidden = true;
    const response = await fetch(`../data/buslines/${encodeURIComponent(folder)}/energy.json`);
    if (event.target.value !== folder) return;
    if (response.ok) load_energy(await response.json(), `data/buslines/${folder}/energy.json`);
    else $('energy-name').textContent = 'No energy.json in this folder';
  } catch (error) {
    show_source_error('busline-error', error);
  }
});

/** Populate each selector from its matching data directory. */
for (const [kind, select_id, error_id] of [
  ['requests', 'request-folder', 'file-error'],
  ['graphs', 'graph-folder', 'graph-error'],
  ['buslines', 'busline-folder', 'busline-error']
]) {
  folder_names(kind)
    .then((names) => {
      for (const name of names) $(select_id).add(new Option(name, name));
    })
    .catch((error) => show_source_error(error_id, error));
}
