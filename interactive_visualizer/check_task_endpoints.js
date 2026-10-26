// Run with: node interactive_visualizer/check_task_endpoints.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const elements = new Map();
const element = () => ({ checked: true, value: 86400, children: [], style: {}, dataset: {},
  classList: { toggle() {} }, addEventListener() {}, append(...items) { this.children.push(...items); },
  replaceChildren(...items) { this.children = items; } });
const document = { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element, createDocumentFragment: element, querySelectorAll() { return []; } };
const layer = () => ({ addTo(group) { group?.layers?.push(this); return this; }, bindPopup(value) { this.popup = value; return this; }, on() { return this; } });
const layerGroup = () => ({ layers: [], addTo() { return this; }, clearLayers() { this.layers = []; } });
const map = { setView() { return this; }, fitBounds() {}, hasLayer() { return true; }, removeLayer() {} };
const L = { map: () => map, control: { zoom: layer, scale: layer }, tileLayer: layer,
  layerGroup, circleMarker: layer, polyline: layer, latLngBounds: () => ({ pad() { return this; } }) };
const context = vm.createContext({ document, L });
for (const file of ['reqreate.js', 'busline.js'])
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
const read = (folder) => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'requests', folder, 'requests.json')));
const sfbs = read('sfbs_550_0001');
const darp = read('darp_Esch_0001');
context.sfbs = sfbs;
context.darp = darp;
assert.equal(vm.runInContext('read_reqs(sfbs).length', context), 21);
assert.equal(vm.runInContext('read_reqs(darp).length', context), 95);
assert.equal(vm.runInContext('is_sfbs(sfbs.requests[1])', context), true);
assert.equal(vm.runInContext('is_sfbs(Object.values(darp.requests)[0])', context), false);
vm.runInContext('show_req(sfbs.requests[1], false)', context);
assert.match(elements.get('req-details').textContent, /Board at .*Alight at/s);
assert.doesNotMatch(elements.get('req-details').textContent, /drive pickup node/);
const stops = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'outputs', 'buslines', '550', 'stops.json')));
context.stops = stops;
vm.runInContext('load_busline(stops, "stops_550.json"); show_req(sfbs.requests[1], false)', context);
assert.ok(vm.runInContext('sel_layer.layers.length', context) >= 7);
assert.match(elements.get('req-details').textContent, /Estimated walk:/);
vm.runInContext('show_req(Object.values(darp.requests)[0], false)', context);
assert.match(elements.get('req-details').textContent, /Node \d+.*Node \d+/s);
assert.doesNotMatch(elements.get('req-details').textContent, /Estimated walk:/);
console.log('DARP and SFBS endpoint checks passed.');
