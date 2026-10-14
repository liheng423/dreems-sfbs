// Run with: node interactive_visualizer/check_sources.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const elements = new Map();
const loaded = [];
const removed = [];
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: id === 'graph-type' ? 'drive' : '', options: [], listeners: {},
    add(option) { this.options.push(option); },
    addEventListener(name, listener) { this.listeners[name] = listener; }
  });
  return elements.get(id);
}
const context = vm.createContext({
  $: element,
  Option: function Option(name, value) { return { name, value }; },
  DOMParser: class {
    parseFromString(html) {
      return { xml: html, querySelectorAll() {
        return [...html.matchAll(/href="([^"]+)"/g)].map((match) => ({ getAttribute: () => match[1] }));
      } };
    }
  },
  fetch: async (url) => {
    if (url === '../outputs/requests/') return { ok: true, text: async () => '<a href="new_run/">new_run/</a>' };
    if (url === '../outputs/requests/new_run/requests.json')
      return { ok: true, json: async () => ({ 'num_data:': 0, requests: {} }) };
    const file_path = path.join(root, decodeURIComponent(url).replace('../', ''));
    if (!fs.existsSync(file_path)) return { ok: false };
    if (fs.statSync(file_path).isDirectory()) {
      const links = fs.readdirSync(file_path, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => `<a href="${entry.name}/">${entry.name}/</a>`).join('');
      return { ok: true, text: async () => links };
    }
    return { ok: true, json: async () => JSON.parse(fs.readFileSync(file_path, 'utf8')),
      text: async () => fs.readFileSync(file_path, 'utf8') };
  },
  map: { removeLayer(layer) { removed.push(layer); }, fitBounds() {} },
  network_layer: { clearLayers() {} }, all_snap_layer: { clearLayers() {} }, snap_layer: { clearLayers() {} },
  graph_nodes: new Map(), graph_kind: '', selected_req: null, show_req() {},
  load_graphml(xml, kind, name) { loaded.push(['graphml', name, kind]); assert.match(xml.xml, /<graphml /); },
  L: { geoJSON() { return { addTo() { return this; }, getBounds() { return {}; } }; } },
  reqs: [],
  busline_layers: new Map(),
  busline_patterns: new Map(),
  busline_stop_names: new Map(),
  energy_segments: new Map(),
  draw_busline_list() {}, update_walking_stops() {},
  load_reqs(data, name) { loaded.push(['requests', name, data['num_data:']]); },
  load_pois(data, name) { loaded.push(['pois', name, data.features.length]); },
  load_busline(data, name) {
    loaded.push(['stops', name, data.length]);
    context.busline_layers.set(name, { layer: {} });
  },
  load_busline_patterns(data, name) { loaded.push(['businfo', name, data.patterns.length]); },
  load_energy(data, name) { loaded.push(['energy', name, data.segments.length]); }
});
vm.runInContext(fs.readFileSync(path.join(__dirname, 'sources.js'), 'utf8'), context);

(async () => {
  await new Promise(setImmediate);
  assert.ok(element('request-folder').options.some((option) => option.value === 'new_run'));
  assert.ok(element('graph-folder').options.some((option) => option.value === '550'));
  assert.ok(element('busline-folder').options.some((option) => option.value === '605'));

  const request = element('request-folder');
  request.value = 'new_run';
  await request.listeners.change({ target: request });
  assert.equal(loaded[0][0], 'requests');
  assert.match(loaded[0][1], /outputs\/requests\/new_run\/requests\.json/);

  const graph = element('graph-folder');
  graph.value = '550';
  await graph.listeners.change({ target: graph });
  assert.match(loaded[1][1], /outputs\/graphs\/550\/pois\.json/);
  assert.match(element('graph-name').textContent, /outputs\/graphs\/550\/service_area\.geojson/);
  assert.ok(loaded.some(([kind, name]) => kind === 'graphml' && name.endsWith('/550/drive.graphml')));
  element('graph-type').value = 'walk';
  await element('graph-type').listeners.change();
  assert.ok(loaded.some(([kind, name]) => kind === 'graphml' && name.endsWith('/550/walk.graphml')));

  const busline = element('busline-folder');
  busline.value = '550';
  await busline.listeners.change({ target: busline });
  assert.deepEqual(loaded.slice(4).map(([kind]) => kind), ['stops', 'businfo', 'energy']);
  busline.value = '605';
  await busline.listeners.change({ target: busline });
  assert.ok(removed.length);
  assert.equal(element('energy-name').textContent, 'No energy.json in this folder');
  console.log('Folder source checks passed.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
