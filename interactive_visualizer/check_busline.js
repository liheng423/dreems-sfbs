// Run with: node interactive_visualizer/check_busline.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    children: [], style: {}, listeners: {}, hidden: false,
    addEventListener(name, listener) { this.listeners[name] = listener; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; }
  };
}

const elements = new Map();
const shown = new Set();
const map = { hasLayer(layer) { return shown.has(layer); }, removeLayer(layer) { shown.delete(layer); } };
const L = {
  layerGroup() { return { markers: [], lines: [], addTo() { shown.add(this); return this; },
    removeLayer(line) { this.lines.splice(this.lines.indexOf(line), 1); } }; },
  circleMarker(xy, options) {
    return { xy, options, bindPopup() { return this; }, addTo(layer) { layer.markers.push(this); } };
  },
  polyline(coordinates, options) {
    return { coordinates, options, bindPopup() { return this; }, addTo(layer) { layer.lines.push(this); return this; } };
  }
};
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element
};
const context = vm.createContext({ document, L, map, location: { protocol: 'file:' } });
vm.runInContext(fs.readFileSync(path.join(__dirname, 'busline.js'), 'utf8'), context);
const stops = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'buslines', '550', 'stops.json'), 'utf8'));
const crawled = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'buslines', '550', 'businfo.json'), 'utf8'));
context.stops = stops;
context.crawled = crawled;
vm.runInContext('load_busline_patterns(crawled, "crawled_550.json")', context);
vm.runInContext('load_busline(stops, "stops_550.json")', context);
assert.equal(Number(elements.get('busline-count').textContent.split(' ')[0]), stops.length);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers.length', context), stops.length);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers[0].xy[0]', context), stops[0].lat);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers[0].options.radius', context), 6);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines.length', context), 2);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[0].coordinates.length', context), crawled.patterns[0].stop_ids.length);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[0].coordinates[0][0]', context),
  stops.find((stop) => stop.name === `Stop_${crawled.patterns[0].stop_ids[0]}`).lat);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[1].options.dashArray', context), '7 6');
vm.runInContext('load_busline(stops.slice(0, 2), "stops_other.json")', context);
assert.equal(elements.get('busline-list').children.length, 2);
assert.equal(elements.get('busline-count').textContent, `${stops.length + 2} stops`);
const toggle = elements.get('busline-list').children[1].children[0];
toggle.checked = false;
toggle.listeners.change();
assert.equal(vm.runInContext('map.hasLayer(busline_layers.get("stops_other.json").layer)', context), false);
context.invalid = [{ ...stops[0], lat: '49.5' }];
assert.throws(() => vm.runInContext('load_busline(invalid, "invalid.json")', context), /coordinates/);
console.log('Busline viewer checks passed.');
