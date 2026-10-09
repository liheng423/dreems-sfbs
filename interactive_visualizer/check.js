// Run with: node interactive_visualizer/check.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    value: '', checked: true, children: [], dataset: {}, style: {}, attributes: {}, listeners: {}, classList: { toggle() {} },
    addEventListener(name, listener) { this.listeners[name] = listener; },
    setAttribute(name, value) { this.attributes[name] = value; },
    getAttribute(name) { return this.attributes[name]; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; }, add(child) { this.children.push(child); }
  };
}

const tooltips = [];
function layer() {
  return { addTo(target) { if (target?.layers) target.layers.push(this); return this; }, on() { return this; }, bindPopup() { return this; },
    bindTooltip(label) { tooltips.push(label); return this; }, openPopup() { return this; }, clearLayers() {} };
}
function layerGroup() {
  return { ...layer(), layers: [], clearLayers() { this.layers = []; } };
}

const elements = new Map();
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element,
  createDocumentFragment: element,
  querySelectorAll() { return []; }
};
const map = { setView() { return this; }, fitBounds() {} };
const L = {
  map() { return map; }, control: { zoom: layer, scale: layer }, tileLayer: layer,
  layerGroup, polyline: layer, circleMarker: layer,
  latLngBounds() { return { pad() { return this; } }; }
};
const context = vm.createContext({ document, L, Option: function (label, value) { return { label, value }; } });
vm.runInContext(fs.readFileSync(path.join(__dirname, 'viewer.js'), 'utf8'), context);

for (const [scen, count] of [['low', 50], ['base', 100], ['high', 200]]) {
  const file = path.join(__dirname, '..', 'data', 'instances', `550_${scen}.json`);
  context.data = JSON.parse(fs.readFileSync(file, 'utf8'));
  vm.runInContext('load_inst(data, "instance.json")', context);
  assert.equal(Number(elements.get('req-count').textContent), count);
  assert.equal(Number(elements.get('pattern-count').textContent), 2);
  assert.ok(Number(elements.get('stop-count').textContent) > 0);
}

assert.equal(vm.runInContext('minute_label(-962)', context), '07:58 -1d');
elements.get('flows-check').checked = true;
vm.runInContext('draw_map(); show_req(visible_reqs[0])', context);

elements.get('dynamic-check').checked = false;
vm.runInContext('draw_map()', context);
assert.equal(Number(elements.get('req-count').textContent), 100);
elements.get('pattern-select').value = '2483_0|0-00';
vm.runInContext('draw_map()', context);
assert.equal(Number(elements.get('req-count').textContent), 50);
elements.get('time-range').value = 0;
vm.runInContext('draw_map()', context);
assert.equal(Number(elements.get('req-count').textContent), 0);

context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'instances', '550_base.json'), 'utf8'));
vm.runInContext('load_inst(data, "550_base.json")', context);
context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'candidate_pool_550.json'), 'utf8'));
vm.runInContext('cand_pool = data; audit_inst(); draw_map()', context);
assert.equal(vm.runInContext('issues.length', context), 0);
assert.equal(vm.runInContext('req_cands.size', context), 99);
context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'timetable_550.json'), 'utf8'));
vm.runInContext('timetable = data; audit_inst()', context);
assert.equal(vm.runInContext('issues.length', context), 0);

vm.runInContext('reqs[0].time_window[0]++; audit_inst(); draw_map()', context);
assert.match(vm.runInContext('issues.find(issue => issue.req_id === reqs[0].id).message', context), /pickup window/);
vm.runInContext('reqs[0].desired_time++; audit_inst()', context);
assert.ok(vm.runInContext('issues.some(issue => issue.message.includes("no matching raw pool candidate"))', context));
elements.get('issues-check').checked = true;
vm.runInContext('draw_map()', context);
assert.equal(Number(elements.get('req-count').textContent), 1);

vm.runInContext('cand_pool.candidate_pool[0].candidates[0].source_origin_stop_id = "wrong"; audit_inst()', context);
assert.ok(vm.runInContext('issues.some(issue => issue.message.includes("source stop ID"))', context));
vm.runInContext('timetable.service_date = "wrong"; audit_inst()', context);
assert.ok(vm.runInContext('issues.some(issue => issue.message.includes("Timetable service date"))', context));
vm.runInContext('show_cand(issues.find(issue => issue.cand).cand)', context);
assert.match(elements.get('req-details').innerHTML, /Candidate/);
for (const scen of ['low', 'high']) {
  context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'instances', `550_${scen}.json`), 'utf8'));
  vm.runInContext('load_inst(data, "instance.json")', context);
  context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'candidate_pool_550.json'), 'utf8'));
  vm.runInContext('cand_pool = data', context);
  context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'timetable_550.json'), 'utf8'));
  vm.runInContext('timetable = data; audit_inst()', context);
  assert.equal(vm.runInContext('issues.length', context), 0);
}
async function check_distances() {
  context.data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'instances', '550_base.json'), 'utf8'));
  vm.runInContext('load_inst(data, "550_base.json")', context);
  const matrix = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'distance_matrix_550.json'), 'utf8'));
  await elements.get('dist-file').listeners.change({ target: { files: [{ name: 'distance_matrix_550.json', text: async () => JSON.stringify(matrix) }] } });
  assert.equal(elements.get('dist-button').disabled, false);
  const org = matrix.stop_ids.indexOf(context.data.network.source_stop_ids['1']);
  const dst = matrix.stop_ids.indexOf(context.data.network.source_stop_ids['3']);
  assert.equal(vm.runInContext('dist_m(1, 3)', context), matrix.distances_m[org][dst]);
  elements.get('dist-button').listeners.click();
  assert.equal(elements.get('dist-button').getAttribute('aria-pressed'), 'true');
  assert.ok(tooltips.length > 0);
  vm.runInContext('show_req(reqs[0])', context);
  assert.match(elements.get('req-details').innerHTML, /Road distance/);
  elements.get('dist-button').listeners.click();
  assert.equal(elements.get('dist-button').getAttribute('aria-pressed'), 'false');
  assert.doesNotMatch(elements.get('req-details').innerHTML, /Road distance/);

  elements.get('debug-mode-check').checked = true;
  elements.get('debug-mode-check').listeners.change();
  const debug = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'debug', 'rejected_candidates_550.debug.json'), 'utf8'));
  await elements.get('debug-file').listeners.change({ target: { files: [{ name: 'rejected_candidates_550.debug.json', text: async () => JSON.stringify(debug) }] } });
  assert.equal(vm.runInContext('visible_debug.length', context), 31);
  assert.equal(vm.runInContext('[...debug_findings.values()].filter(items => items.length).length', context), 0);
  assert.equal(vm.runInContext('debug_layer.layers.length', context), 62);
  vm.runInContext('show_debug(visible_debug[0])', context);
  assert.match(elements.get('req-details').innerHTML, /Feasible/);
  assert.match(elements.get('req-details').innerHTML, /Debug checks: passed/);
  elements.get('time-range').value = 0;
  vm.runInContext('draw_map()', context);
  assert.equal(vm.runInContext('visible_debug.length', context), 31);
  elements.get('debug-reason').value = 'pickup_after_latest_feasible_time';
  elements.get('debug-reason').listeners.change();
  assert.equal(vm.runInContext('visible_debug.length', context), debug.rejected_candidates.filter((cand) => cand.rejection_reasons.includes('pickup_after_latest_feasible_time')).length);
  elements.get('debug-reason').value = 'all';
  elements.get('debug-outside-check').checked = true;
  elements.get('debug-outside-check').listeners.change();
  assert.equal(vm.runInContext('visible_debug.length', context), debug.rejected_candidates.length);
  const pool = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'candidate_pool_550.json'), 'utf8'));
  const src = pool.candidate_pool[0].candidates[0];
  const start = context.data.network.patterns[0].service_period.start_minute;
  context.alloc = { ...src, scenario: 'base', booking_type: 'dynamic', request_time: start - 1,
    service_start_minute: start, rejection_reasons: ['booking_before_service_start'] };
  elements.get('debug-outside-check').checked = false;
  vm.runInContext('debug_data.rejected_allocations.push(alloc); debug_data.rejected_allocation_count++; audit_debug(); draw_map()', context);
  assert.equal(vm.runInContext('visible_debug.length', context), 32);
  assert.equal(vm.runInContext('debug_findings.get(alloc).length', context), 0);
  vm.runInContext('show_debug(alloc)', context);
  assert.match(elements.get('req-details').innerHTML, /Service starts/);
  elements.get('debug-reason').value = 'booking_before_service_start';
  elements.get('debug-reason').listeners.change();
  assert.equal(vm.runInContext('visible_debug.length', context), 1);
  elements.get('debug-reason').value = 'all';
  vm.runInContext('debug_data.rejected_candidates[0].rejection_reasons = []; audit_debug()', context);
  assert.match(elements.get('debug-warnings').textContent, /1 rejected candidate/);
  elements.get('debug-mode-check').checked = false;
  elements.get('debug-mode-check').listeners.change();
  assert.equal(vm.runInContext('debug_layer.layers.length', context), 0);
  console.log('Viewer checks passed for filters, generator audits, distance overlay, and rejected-candidate debug mode.');
}
check_distances().catch((error) => { console.error(error); process.exitCode = 1; });
