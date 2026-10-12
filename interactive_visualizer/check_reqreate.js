// Run with: node interactive_visualizer/check_reqreate.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    value: '', checked: true, children: [], dataset: {}, style: {}, classList: { toggle() {} }, listeners: {},
    addEventListener(name, listener) { this.listeners[name] = listener; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; }
  };
}
function layer() {
  return { listeners: {}, addTo(target) { if (target?.layers) target.layers.push(this); return this; },
    bindPopup(content) { this.popup = content; return this; },
    on(name, listener) { this.listeners[name] = listener; return this; } };
}
function layerGroup() {
  return { ...layer(), layers: [], clearLayers() { this.layers = []; } };
}
const elements = new Map();
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element, createDocumentFragment: element, querySelectorAll() { return []; }
};
const map = { setView() { return this; }, fitBounds() {}, hasLayer() { return true; }, removeLayer() {} };
const L = {
  map() { return map; }, control: { zoom: layer, scale: layer }, tileLayer: layer,
  layerGroup, polyline: layer, circleMarker: layer,
  latLngBounds() { return { pad() { return this; } }; }
};
const context = vm.createContext({ document, L, location: { protocol: 'file:' } });
vm.runInContext(fs.readFileSync(path.join(__dirname, 'reqreate.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, 'busline.js'), 'utf8'), context);
const area_dir = path.join(__dirname, '..', 'data', 'requests', '550');
const data = JSON.parse(fs.readFileSync(path.join(area_dir, 'raw_requests.json'), 'utf8'));
const pois = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'graphs', '550', 'pois.json'), 'utf8'));
context.data = data;
context.pois = pois;
vm.runInContext('load_reqs(data, "550_raw_requests.json")', context);
vm.runInContext('load_pois(pois, "550_pois.json")', context);
assert.equal(elements.get('poi-count').textContent, '540 POIs');
assert.equal(vm.runInContext('poi_layer.layers.length', context), 540);
assert.equal(elements.get('poi-types').children.length, 6);
assert.equal(elements.get('poi-types').children.reduce((sum, row) => sum + Number(row.children[2].textContent), 0), 540);
assert.equal(elements.get('poi-tags').children.length, new Set(pois.features
  .flatMap((poi) => Object.entries(poi.tags).map(([tag, value]) => `${tag}: ${value}`))).size);
assert.equal(Number(elements.get('req-count').textContent), data['num_data:']);
assert.equal(Number(elements.get('stop-count').textContent), new Set(Object.values(data.requests)
  .flatMap((req) => [req.origin.join(','), req.destination.join(',')])).size);
assert.equal(vm.runInContext('req_by_id.size', context), data['num_data:']);
assert.equal(elements.get('req-list').children[0].children.length, 200);
elements.get('dynamic-check').checked = false;
vm.runInContext('draw_map()', context);
assert.equal(Number(elements.get('req-count').textContent), Object.values(data.requests)
  .filter((req) => req.is_prebooked === 1).length);
elements.get('time-range').value = 43200;
vm.runInContext('draw_map()', context);
assert.equal(Number(elements.get('req-count').textContent), data.requests && Object.values(data.requests)
  .filter((req) => req.is_prebooked === 1 && req.earliest_departure <= 43200).length);
elements.get('flows-check').checked = true;
vm.runInContext('draw_map()', context);
assert.ok(vm.runInContext('flow_layer.layers.length', context) > 0);
vm.runInContext('show_req(reqs.find((req) => req.is_prebooked))', context);
assert.match(elements.get('req-details').textContent, /-3d|\-2d|\-1d/);
assert.match(elements.get('req-details').textContent, /Direct distance/);
assert.match(elements.get('req-timeline').innerHTML, /windows are absent/);
context.windowReq = { ...vm.runInContext('selected_req', context), pickup_from: 36000,
  pickup_to: 36900, dropoff_from: 37500, dropoff_to: 38400, service_time: 30,
  earliest_departure: 36000, latest_arrival: 38400 };
vm.runInContext('draw_req_timeline(windowReq)', context);
assert.match(elements.get('req-timeline').innerHTML, /Pickup window.*10:00–10:15/s);
assert.match(elements.get('req-timeline').innerHTML, /Dropoff window.*10:25–10:40/s);
assert.match(elements.get('req-timeline').innerHTML, /Boarding and alighting service: 30 s/);
context.newPool = { 'num_data:': 1, requests: { [context.windowReq.reqid]: context.windowReq } };
assert.equal(vm.runInContext('read_reqs(newPool).length', context), 1);
assert.match(elements.get('selected-energy-note').textContent, /Load the bus energy JSON/);
const stops = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'buslines', '550', 'stops.json'), 'utf8'));
const businfo = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'buslines', '550', 'businfo.json'), 'utf8'));
const energy = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'buslines', '550', 'energy.json'), 'utf8'));
context.stops = stops;
context.businfo = businfo;
context.energy = energy;
vm.runInContext('load_busline(stops, "stops_550.json"); load_busline_patterns(businfo, "crawled_550.json"); load_energy(energy, "energy.json")', context);
vm.runInContext('show_req(req_by_id.get(3423))', context);
assert.match(elements.get('selected-energy').textContent, /^\d+\.\d\d$/);
assert.ok(Number(elements.get('selected-energy').textContent) > 0);
assert.match(elements.get('req-details').textContent, /Bettembourg|Hellange|Frisange|Aspelt|Altwies|Mondorf|Remich/);
assert.match(elements.get('req-list').children[0].children[0].children[2].textContent, /kWh/);
elements.get('walks-check').checked = true;
vm.runInContext('draw_map()', context);
assert.equal(vm.runInContext('walk_layer.layers.length', context), vm.runInContext('visible_reqs.length * 2', context));
vm.runInContext('show_req(reqs.find((req) => req.is_prebooked))', context);
assert.match(elements.get('req-details').textContent, /Estimated walk:.*Estimated bus trip energy: \d+\.\d\d kWh/s);
assert.match(elements.get('selected-energy').textContent, /^\d+\.\d\d$/);
assert.match(elements.get('energy-request').textContent, /^Request #\d+$/);
assert.ok(vm.runInContext('sel_layer.layers.length', context) >= 5);
context.bad = { ...data, 'num_data:': 1 };
assert.throws(() => vm.runInContext('read_reqs(bad)', context), /REQreate raw requests/);
vm.runInContext('load_reqs(data, "550_raw_requests.json")', context);
assert.match(elements.get('selected-energy').textContent, /^\d+\.\d\d$/);
const point = vm.runInContext('stop_layer.layers[0]', context);
point.listeners.click();
assert.match(elements.get('energy-request').textContent, /^Request #\d+$/);
assert.match(elements.get('req-details').textContent, /Estimated route:.*Estimated bus trip energy: \d+\.\d\d kWh/s);
assert.match(point.popup().children[1].textContent, /\d+\.\d\d kWh/);
const shared = vm.runInContext(`request_point_popup({node: 1, endpoints: [
  {req: reqs[0], endpoint: 'origin'}, {req: reqs[1], endpoint: 'destination'}
]})`, context);
assert.equal(shared.children.length, 3);
shared.children[2].listeners.click();
assert.equal(elements.get('energy-request').textContent, `Request #${vm.runInContext('reqs[1].reqid', context)}`);

const first = Object.values(data.requests)[0];
const xmlItem = (attrs, children = [], textContent = '') => ({
  getAttribute(name) { return attrs[name]; }, textContent,
  getElementsByTagNameNS(name, tag) { return tag === 'data' ? children : []; }
});
const graphXml = {
  getElementsByTagName() { return []; },
  getElementsByTagNameNS(name, tag) {
    if (tag === 'key') return [
      xmlItem({ id: 'x', 'attr.name': 'x' }), xmlItem({ id: 'y', 'attr.name': 'y' }),
      xmlItem({ id: 'g', 'attr.name': 'geometry' })
    ];
    if (tag === 'node') return [
      xmlItem({ id: String(first.originnode_drive) }, [xmlItem({ key: 'x' }, [], '6.1'), xmlItem({ key: 'y' }, [], '49.5')]),
      xmlItem({ id: String(first.destinationnode_drive) }, [xmlItem({ key: 'x' }, [], '6.2'), xmlItem({ key: 'y' }, [], '49.6')])
    ];
    if (tag === 'edge') return [xmlItem({ source: String(first.originnode_drive), target: String(first.destinationnode_drive) },
      [xmlItem({ key: 'g' }, [], 'LINESTRING (6.1 49.5, 6.15 49.55, 6.2 49.6)')])];
    return [];
  }
};
context.graphXml = graphXml;
vm.runInContext('load_graphml(graphXml, "drive", "drive.graphml"); show_req(reqs[0], false)', context);
assert.equal(vm.runInContext('network_layer.layers.length', context), 3);
assert.equal(vm.runInContext('all_snap_layer.layers.length', context), Object.values(data.requests)
  .flatMap((req) => [req.originnode_drive, req.destinationnode_drive])
  .filter((id) => id === first.originnode_drive || id === first.destinationnode_drive).length);
assert.equal(vm.runInContext('snap_layer.layers.length', context), 4);
assert.match(elements.get('graph-file-name').textContent, /2 nodes · 1 edges/);
assert.match(elements.get('req-details').textContent, /drive pickup node/);
console.log('REQreate viewer checks passed.');
