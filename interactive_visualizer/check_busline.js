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
    return { xy, options, bindPopup() { return this; },
      bindTooltip(label, tooltipOptions) { this.sequence = label; this.tooltip = {options: tooltipOptions}; return this; },
      getTooltip() { return this.tooltip || null; },
      setTooltipContent(label) { this.sequence = label; return this; },
      closeTooltip() { return this; },
      unbindTooltip() { this.sequence = undefined; this.tooltip = null; return this; },
      bringToFront() { return this; },
      addTo(layer) { layer.markers.push(this); return this; } };
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
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'shared', 'sfbs_route.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, 'busline.js'), 'utf8'), context);
const stops = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'outputs', 'buslines', '550', 'stops.json'), 'utf8'));
const crawled = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'outputs', 'buslines', '550', 'buslines.json'), 'utf8'));
context.stops = stops;
context.crawled = crawled;
vm.runInContext('load_busline_patterns(crawled, "crawled_550.json")', context);
vm.runInContext('load_busline(stops, "stops_550.json")', context);
assert.equal(Number(elements.get('busline-count').textContent.split(' ')[0]), stops.length);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers.length', context), stops.length);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers[0].xy[0]', context), stops[0].lat);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers[0].options.fillColor', context), '#174b9b');
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers[1].options.dashArray', context), '3 2');
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.markers[1].tooltip.options.className', context), 'sfbs-sequence sfbs-optional');
const pairs = crawled.patterns.flatMap(pattern => pattern.stop_ids.slice(1).map((id, index) =>
  [id, pattern.stop_ids[index]].sort().join('|')));
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines.length', context),
  new Set(pairs).size);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[0].coordinates.length', context), 2);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[0].coordinates[0][0]', context),
  stops.find((stop) => stop.name === `Stop_${crawled.patterns[0].stop_ids[0]}`).lat);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[0].options.dashArray', context),
  stops.find(stop => stop.name === `Stop_${crawled.patterns[0].stop_ids[0]}`).class === 'optional' ||
  stops.find(stop => stop.name === `Stop_${crawled.patterns[0].stop_ids[1]}`).class === 'optional' ? '7 6' : undefined);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").markers.get(`Stop_${crawled.patterns[0].stop_ids[0]}`).sequence', context),
  `1 / ${crawled.patterns[1].stop_ids.indexOf(crawled.patterns[0].stop_ids[0]) + 1}`);
const selected = structuredClone(crawled);
selected.patterns[0].selected_stop_ids = [...selected.patterns[0].stop_ids].reverse();
context.selected = selected;
vm.runInContext('load_busline_patterns(selected, "crawled_550.json")', context);
assert.equal(vm.runInContext('busline_layers.get("stops_550.json").layer.lines[0].coordinates[0][0]', context),
  stops.find((stop) => stop.name === `Stop_${selected.patterns[0].selected_stop_ids[0]}`).lat);
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
