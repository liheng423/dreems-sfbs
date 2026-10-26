const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const html = readFileSync(join(__dirname, '../src/locations/select_locations.html'), 'utf8');
const shared = readFileSync(join(__dirname, '../shared/sfbs_route.js'), 'utf8');
assert.match(html, /<script src="\/sfbs_route\.js"><\/script>/);
assert.match(html, /addVertexOn: 'dragstart'/);
assert.match(html, /#map \.marker-icon-middle \{\s*opacity: 0 !important;/);
const source = html.match(/  function nearestSegment[\s\S]*?(?=\n  function nodePopup)/)[0];
const stops = new Map(['A', 'B', 'C', 'D'].map((id, lon) =>
  [`Stop_${id}`, {name: `Stop_${id}`, class: 'mandatory', lat: 0, lon}]));
const map = {latLngToContainerPoint: ([y, x]) => ({x, y})};
const L = {LineUtil: {pointToSegmentDistance: (point, from, to) =>
  Math.abs(point.x - (from.x + to.x) / 2)}};
const nearestSegment = runInNewContext(`${source}\nnearestSegment`, {stops, map, L});
const segment = nearestSegment([0, 1.6], {stop_ids: ['A', 'B', 'C', 'D']});

assert.equal(segment.index, 1);
assert.equal(segment.from.name, 'Stop_B');
assert.equal(segment.to.name, 'Stop_C');

const drawSource = html.match(/  function drawSequence[\s\S]*?(?=\n  patternSelect\.onchange)/)[0];
const events = new Map();
const lines = [];
const line = {pm: {enable() {}}, addTo() { return this; },
  on(name, handler) { events.set(name, handler); }};
let opened = null;
const stopMarkers = new Map(['A', 'B'].map(id => [`Stop_${id}`, {
  bringToFront() {}, openPopup() { opened = id; },
  bindTooltip(label, options) { this.sequence = label; this.tooltip = {options}; },
  getTooltip() { return this.tooltip || null; },
  setTooltipContent(label) { this.sequence = label; }, closeTooltip() {},
  unbindTooltip() { this.sequence = undefined; this.tooltip = null; }
}]));
stops.get('Stop_B').class = 'optional';
runInNewContext(`${shared}\n${drawSource}\ndrawSequence()`, {
  sequenceLine: null, sequenceSegments: [], patterns: [{stop_ids: ['A', 'B']}],
  patternSelect: {selectedIndex: 0}, mode: {value: 'busline'},
  stops, stopMarkers, L: {polyline(coordinates, options) {
    lines.push({coordinates, options}); return options.opacity === 0 ? line : {addTo() { return this; }};
  }}, map: {}
});
events.get('pm:vertexclick')({indexPath: 1});
assert.equal(opened, 'B');
assert.equal(lines[0].options.dashArray, '7 6');
assert.equal(stopMarkers.get('Stop_A').sequence, '1');
assert.equal(stopMarkers.get('Stop_B').sequence, '2');
assert.equal(stopMarkers.get('Stop_A').tooltip.options.className, 'sfbs-sequence sfbs-mandatory');
assert.equal(stopMarkers.get('Stop_B').tooltip.options.className, 'sfbs-sequence sfbs-optional');

const route = runInNewContext(`${shared}\nsfbsRoute(['A', 'B', 'C'], new Map([
  ['Stop_A', {name: 'Stop_A', class: 'mandatory', lat: 0, lon: 0}],
  ['Stop_B', {name: 'Stop_B', class: 'optional', lat: 0, lon: 1}],
  ['Stop_C', {name: 'Stop_C', class: 'mandatory', lat: 0, lon: 2}]
]))`);
assert.deepEqual([...route.points.map(point => point.number)], [1, 2, 3]);
assert.deepEqual([...route.segments.map(segment => segment.dashArray)], ['7 6', '7 6']);
assert.equal(runInNewContext(`${shared}\nsfbsRoute(['A', 'C'], new Map([
  ['Stop_A', {name: 'Stop_A', class: 'mandatory', lat: 0, lon: 0}],
  ['Stop_C', {name: 'Stop_C', class: 'mandatory', lat: 0, lon: 2}]
])).segments[0].dashArray`), undefined);
