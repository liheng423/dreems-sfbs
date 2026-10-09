/* The viewer reads a generator instance through the file picker so file:// works. */
const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView([49.611, 6.131], 10);
L.control.zoom({ position: 'topright' }).addTo(map);
L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
}).addTo(map);

const route_layer = L.layerGroup().addTo(map);
const stop_layer = L.layerGroup().addTo(map);
const flow_layer = L.layerGroup().addTo(map);
const dist_layer = L.layerGroup().addTo(map);
const debug_layer = L.layerGroup().addTo(map);
const sel_layer = L.layerGroup().addTo(map);
const pattern_colors = ['#246b59', '#3c7d9f', '#9b6845', '#875b8e', '#a45d64'];
const book_colors = { prebooked: '#496cb1', dynamic: '#e69247' };
const $ = (id) => document.getElementById(id);

let inst = null;
let reqs = [];
let visible_reqs = [];
let selected_req = null;
let route_bounds = null;
let cand_pool = null;
let timetable = null;
let dist_mat = null;
let dist_idx = new Map();
let debug_data = null;
let visible_debug = [];
let selected_debug = null;
let debug_findings = new Map();
let issues = [];
let req_cands = new Map();

/** Format generator minutes, including services after midnight. */
function minute_label(min) {
  const day = Math.floor(min / 1440);
  const hour = Math.floor((min - day * 1440) / 60);
  const minute = min - day * 1440 - hour * 60;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}${day ? ` ${day > 0 ? '+' : ''}${day}d` : ''}`;
}

function escape_html(val) {
  return String(val).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function stop_xy(net, stop_id) {
  const [longitude, latitude] = net.coordinates[String(stop_id)];
  return [latitude, longitude];
}

function pattern_key(pattern) {
  return `${pattern.route_id}|${pattern.pattern_id}`;
}

function cand_key(cand) {
  return `${pattern_key(cand)}|${cand.origin}|${cand.destination}|${cand.desired_time}`;
}

function compare_text(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function stop_name(net, stop_id) {
  return net.stop_names[String(stop_id)];
}

/** Look up a directed road distance using the instance's physical stop IDs. */
function dist_m(org, dst) {
  const ids = inst.network.source_stop_ids;
  return dist_mat.distances_m[dist_idx.get(ids[String(org)])][dist_idx.get(ids[String(dst)])];
}

function dist_label(metres) {
  return metres === null ? 'unavailable' : metres >= 1000 ? `${(metres / 1000).toFixed(1)} km` : `${Math.round(metres)} m`;
}

function debug_deviation(cand) {
  if (!cand.feasible_pickup_bounds) return 0;
  const [earliest, latest] = cand.feasible_pickup_bounds;
  return cand.desired_time < earliest ? cand.desired_time - earliest : Math.max(0, cand.desired_time - latest);
}

function debug_color(cand) {
  const deviation = debug_deviation(cand);
  return deviation < 0 ? '#496cb1' : deviation > 0 ? '#b65143' : '#875b8e';
}

function debug_reason(reason) {
  return reason.replaceAll('_', ' ');
}

/** Check rejection provenance and whether each stated reason follows from its recorded bounds. */
function audit_debug() {
  const net = inst.network;
  const patterns = new Map(net.patterns.map((pattern) => [pattern_key(pattern), pattern]));
  const warnings = [];
  debug_findings = new Map();
  if (debug_data.rejected_count !== debug_data.rejected_candidates.length) warnings.push('Rejected preference count differs from the file contents.');
  if (debug_data.rejected_allocation_count !== (debug_data.rejected_allocations?.length || 0)) warnings.push('Rejected allocation count differs from the file contents.');
  if (debug_data.seed !== inst.generation.seed) warnings.push('Debug seed differs from the instance seed.');
  if (debug_data.service_date !== inst.config.service_date) warnings.push('Debug service date differs from the instance.');
  const cand_ids = new Set();
  for (const cand of [...debug_data.rejected_candidates, ...(debug_data.rejected_allocations || [])]) {
    const findings = [];
    const pattern = patterns.get(pattern_key(cand));
    const cand_id = `${cand.scenario || 'raw'}|${cand.candidate_id}`;
    if (cand_ids.has(cand_id)) findings.push('Duplicate candidate ID in this stage and scenario.');
    cand_ids.add(cand_id);
    if (!pattern || pattern.stops.indexOf(cand.origin) < 0 || pattern.stops.indexOf(cand.destination) <= pattern.stops.indexOf(cand.origin)) {
      findings.push('Stops are not in forward pattern order.');
    }
    if (cand.source_origin_stop_id !== net.source_stop_ids[String(cand.origin)] ||
        cand.source_destination_stop_id !== net.source_stop_ids[String(cand.destination)]) findings.push('Source stop mapping differs from the instance.');
    const width = inst.config.pickup_window_half_width_minutes;
    if (cand.time_window[0] !== cand.desired_time - width || cand.time_window[1] !== cand.desired_time + width) {
      findings.push('Pickup window differs from the configured width.');
    }
    const expected = [];
    if (cand.feasible_pickup_bounds) {
      const [earliest, latest] = cand.feasible_pickup_bounds;
      const [start, end] = cand.operating_hours;
      if (pattern && (start !== pattern.service_period.start_minute || end !== pattern.service_period.end_minute)) {
        findings.push('Operating hours differ from the pattern service period.');
      }
      if (earliest < start || latest > end || earliest > latest) findings.push('Feasible pickup bounds fall outside operating hours.');
      if (cand.desired_time < earliest) expected.push('pickup_before_earliest_feasible_time');
      if (cand.desired_time > latest) expected.push('pickup_after_latest_feasible_time');
    } else {
      if (pattern && cand.service_start_minute !== pattern.service_period.start_minute) findings.push('Service start differs from the pattern.');
      if (cand.booking_type !== 'dynamic') findings.push('Rejected allocation is not dynamic.');
      if (cand.request_time < cand.service_start_minute) expected.push('booking_before_service_start');
    }
    if (expected.length !== cand.rejection_reasons.length || expected.some((reason) => !cand.rejection_reasons.includes(reason))) {
      findings.push('Rejection reasons disagree with recorded times and bounds.');
    }
    debug_findings.set(cand, findings);
  }
  const flagged = [...debug_findings.values()].filter((findings) => findings.length).length;
  $('debug-warnings').textContent = [...warnings, ...(flagged ? [`${flagged} rejected candidate${flagged === 1 ? '' : 's'} fail the debug checks; select them for details.`] : [])].join(' ');
}

function selected_patterns() {
  const key = $('pattern-select').value;
  return inst.network.patterns.filter((pattern) => key === 'all' || pattern_key(pattern) === key);
}

function filtered_reqs(patterns) {
  const keys = new Set(patterns.map(pattern_key));
  const until_min = Number($('time-range').value);
  return reqs.filter((req) => keys.has(pattern_key(req)) &&
    $(req.type === 'prebooked' ? 'prebooked-check' : 'dynamic-check').checked &&
    (!$('issues-check').checked || issues.some((issue) => issue.req_id === req.id)) &&
    req.desired_time <= until_min);
}

/** Recheck the generator's output rules; the optional pool also checks sampled provenance. */
function audit_inst() {
  const net = inst.network;
  const patterns = new Map(net.patterns.map((pattern) => [pattern_key(pattern), pattern]));
  const width = inst.config.pickup_window_half_width_minutes;
  const prebook_lead = cand_pool?.lead_time_rules.prebooked_minutes || [1440, 4320];
  const dyn_lead = cand_pool?.lead_time_rules.dynamic_minutes || [5, 30];
  const report = [];
  const add = (message, req_id = null, cand = null) => report.push({ message, req_id, cand });
  const allocations = inst.config.route_pattern_booking_allocations;
  const alloc_keys = new Set(allocations.map((alloc) => `${pattern_key(alloc)}|${alloc.booking_type}`));
  const req_by_id = new Map(reqs.map((req) => [req.id, req]));

  if (reqs.length !== inst.config.request_count) add(`Request count: file says ${inst.config.request_count}, found ${reqs.length}.`);
  for (const book_type of ['prebooked', 'dynamic']) {
    const count = reqs.filter((req) => req.type === book_type).length;
    if (count !== inst.config[book_type === 'prebooked' ? 'prebooked_count' : 'dynamic_count']) {
      add(`${book_type} count differs from config: found ${count}.`);
    }
    for (const [key, req] of Object.entries(inst.requests[book_type])) {
      if (String(req.id) !== key || req.type !== book_type) add(`Request key/type mismatch in ${book_type}[${key}].`, req.id);
    }
  }
  if (req_by_id.size !== reqs.length || reqs.some((req) => !Number.isInteger(req.id) || req.id < 0 || req.id >= reqs.length)) {
    add('Request IDs must be unique and contiguous from 0.');
  }

  for (const req of reqs) {
    if (!alloc_keys.has(`${pattern_key(req)}|${req.type}`)) {
      add(`Request #${req.id}: booking/pattern cell has no allocation.`, req.id);
    }
    const pattern = patterns.get(pattern_key(req));
    if (!pattern) {
      add(`Request #${req.id}: route/pattern is absent from network.`, req.id);
      continue;
    }
    const org_idx = pattern.stops.indexOf(req.origin);
    const dst_idx = pattern.stops.indexOf(req.destination);
    if (org_idx < 0 || dst_idx <= org_idx) add(`Request #${req.id}: origin and destination are not in forward pattern order.`, req.id);
    if (req.time_window[0] !== req.desired_time - width || req.time_window[1] !== req.desired_time + width) {
      add(`Request #${req.id}: pickup window differs from desired ±${width} min.`, req.id);
    }
    const svc = pattern.service_period;
    if (req.time_window[0] < svc.start_minute || req.time_window[1] > svc.end_minute) {
      add(`Request #${req.id}: pickup window exceeds service period ${minute_label(svc.start_minute)}–${minute_label(svc.end_minute)}.`, req.id);
    }
    const lead_min = req.desired_time - req.request_time;
    if (req.type === 'prebooked' && (lead_min < prebook_lead[0] || lead_min > prebook_lead[1] || lead_min % 1440 !== 0)) {
      add(`Request #${req.id}: pre-booking lead is ${lead_min} min; expected whole days in ${prebook_lead.join('–')}.`, req.id);
    }
    if (req.type === 'dynamic' && (lead_min < dyn_lead[0] || lead_min > dyn_lead[1] || req.request_time < svc.start_minute)) {
      add(`Request #${req.id}: dynamic lead is ${lead_min} min or booking precedes service start.`, req.id);
    }
  }

  for (const alloc of allocations) {
    const count = reqs.filter((req) => req.type === alloc.booking_type && pattern_key(req) === pattern_key(alloc)).length;
    if (count !== alloc.count) add(`${alloc.booking_type} ${alloc.route_id}/${alloc.pattern_id}: allocation says ${alloc.count}, found ${count}.`);
  }
  if (inst.config.request_count % 2 !== 0) add('Scenario request count must be even for the generator allocation rule.');
  if (inst.config.request_count % 2 === 0) {
    const base = Math.floor(inst.config.request_count / 2 / net.patterns.length);
    const remainder = inst.config.request_count / 2 % net.patterns.length;
    for (const [book_type, offset] of [['prebooked', 0], ['dynamic', Math.floor(net.patterns.length / 2)]]) {
      net.patterns.forEach((pattern, idx) => {
        const expected = base + ((idx - offset + net.patterns.length) % net.patterns.length < remainder ? 1 : 0);
        const alloc = allocations.find((item) => item.booking_type === book_type && pattern_key(item) === pattern_key(pattern));
        if (!alloc || alloc.count !== expected) {
          add(`${book_type} ${pattern.route_id}/${pattern.pattern_id}: expected ${expected} by cyclic allocation rule, found ${alloc?.count ?? 'none'}.`);
        }
      });
    }
  }
  if (allocations.reduce((sum, alloc) => sum + alloc.count, 0) !== inst.config.request_count) {
    add('Allocation counts do not sum to the configured request count.');
  }

  req_cands = new Map();
  if (timetable && timetable.service_date !== inst.config.service_date) {
    add(`Timetable service date ${timetable.service_date} differs from instance ${inst.config.service_date}.`);
  }
  if (cand_pool?.candidate_attempts_per_pattern) {
    if (cand_pool.seed !== inst.generation.seed) add('Candidate pool and instance use different random seeds.');
    if (cand_pool.pickup_window_half_width_minutes !== width) add('Candidate pool and instance use different pickup widths.');
    const cand_ids = new Set();
    const matches = new Map();
    for (const cell of cand_pool.candidate_pool) {
      const pattern = patterns.get(pattern_key(cell));
      if (cell.candidates.length > cand_pool.candidate_attempts_per_pattern) {
        add(`${cell.route_id}/${cell.pattern_id}: candidate count exceeds the raw draw count.`);
      }
      for (const cand of cell.candidates) {
        const add_cand = (message) => add(`Candidate ${cand.candidate_id}: ${message}`, null, cand);
        if (cand_ids.has(cand.candidate_id)) add_cand('candidate ID is duplicated.');
        cand_ids.add(cand.candidate_id);
        if (pattern_key(cand) !== pattern_key(cell) || !pattern ||
            pattern.stops.indexOf(cand.origin) < 0 || pattern.stops.indexOf(cand.destination) <= pattern.stops.indexOf(cand.origin)) {
          add_cand('stops or cell identity are not in forward pattern order.');
          continue;
        }
        if (cand.source_origin_stop_id !== net.source_stop_ids[String(cand.origin)] ||
            cand.source_destination_stop_id !== net.source_stop_ids[String(cand.destination)]) add_cand('source stop ID differs from network mapping.');
        if (cand.time_window[0] !== cand.desired_time - width || cand.time_window[1] !== cand.desired_time + width) {
          add_cand(`pickup window differs from desired ±${width} min.`);
        }
        if (cand.time_window[0] < pattern.service_period.start_minute || cand.time_window[1] > pattern.service_period.end_minute) {
          add_cand('pickup window exceeds the pattern service period.');
        }
        const key = cand_key(cand);
        if (!matches.has(key)) matches.set(key, []);
        matches.get(key).push(cand);
      }
    }
    for (const req of reqs) {
      const candidates = matches.get(cand_key(req)) || [];
      if (!candidates.length) add(`Request #${req.id}: no matching raw pool candidate.`, req.id);
      if (candidates.length === 1) req_cands.set(req.id, candidates[0]);
    }
  } else if (cand_pool) {
    if (cand_pool.seed !== inst.generation.seed) add('Candidate pool and instance use different random seeds.');
    if (cand_pool.pickup_window_half_width_minutes !== width) add('Candidate pool and instance use different pickup widths.');
    const cells = new Map(cand_pool.candidate_pool.map((cell) => [pattern_key(cell).concat('|', cell.booking_type), cell]));
    const trips = timetable ? new Map(timetable.patterns.flatMap((pattern) =>
      pattern.trips.map((trip) => [`${pattern_key(pattern)}|${trip.trip_id}`, trip]))) : null;
    const cand_ids = new Set();
    for (const cell of cand_pool.candidate_pool) {
      const pattern = patterns.get(pattern_key(cell));
      if (cell.candidates.length !== cand_pool.candidate_count_per_booking_route_pattern_cell) {
        add(`${cell.booking_type} ${cell.route_id}/${cell.pattern_id}: candidate count differs from pool metadata.`);
      }
      for (const cand of cell.candidates) {
        const prefix = `Candidate ${cand.candidate_id}`;
        const add_cand = (message) => add(`${prefix}: ${message}`, null, cand);
        if (cand_ids.has(cand.candidate_id)) add_cand('candidate ID is duplicated.');
        cand_ids.add(cand.candidate_id);
        if (cand.booking_type !== cell.booking_type || pattern_key(cand) !== pattern_key(cell)) add_cand('cell identity differs from candidate fields.');
        if (!pattern || pattern.stops.indexOf(cand.origin) < 0 || pattern.stops.indexOf(cand.destination) <= pattern.stops.indexOf(cand.origin)) {
          add_cand('stops are not in forward pattern order.');
          continue;
        }
        const svc = pattern.service_period;
        if (cand.time_window[0] < svc.start_minute || cand.time_window[1] > svc.end_minute) {
          add_cand('pickup window exceeds the pattern service period.');
        }
        const lead_min = cand.desired_time - cand.request_time;
        if (cand.booking_type === 'prebooked' && (lead_min < prebook_lead[0] || lead_min > prebook_lead[1] || lead_min % 1440 !== 0)) {
          add_cand(`pre-booking lead is ${lead_min} min.`);
        }
        if (cand.booking_type === 'dynamic' && (lead_min < dyn_lead[0] || lead_min > dyn_lead[1] || cand.request_time < svc.start_minute)) {
          add_cand(`dynamic lead is ${lead_min} min or booking precedes service start.`);
        }
        const trav_min = net.travel_times[`${cand.origin},${cand.destination}`];
        if (trav_min === undefined || cand.desired_time + trav_min > cand.scheduled_arrival_minute) {
          add_cand('scheduled destination time leaves less than matrix travel time.');
        }
        if (cand.source_origin_stop_id !== net.source_stop_ids[String(cand.origin)] ||
            cand.source_destination_stop_id !== net.source_stop_ids[String(cand.destination)]) {
          add_cand('source stop ID differs from network mapping.');
        }
        if (cand.time_window[0] !== cand.desired_time - width || cand.time_window[1] !== cand.desired_time + width) {
          add_cand(`pickup window differs from desired ±${width} min.`);
        }
        if (trips) {
          const trip = trips.get(`${pattern_key(cand)}|${cand.source_trip_id}`);
          if (!trip) {
            add_cand(`source trip ${cand.source_trip_id} is absent from timetable.`);
          } else {
            const org_evt = trip.stop_times[pattern.stops.indexOf(cand.origin)];
            const dst_evt = trip.stop_times[pattern.stops.indexOf(cand.destination)];
            if (!org_evt || !dst_evt || Math.floor(org_evt.departure_seconds / 60) !== cand.desired_time ||
                Math.floor(dst_evt.departure_seconds / 60) !== cand.scheduled_arrival_minute ||
                org_evt.stop_id !== cand.source_origin_stop_id || dst_evt.stop_id !== cand.source_destination_stop_id) {
              add_cand('source trip stop IDs or departure minutes differ from timetable.');
            }
          }
        }
      }
    }

    // The instance contains no candidate IDs. Rebuild the selected prefixes and ID order.
    const selected = [];
    for (const alloc of allocations) {
      const cell = cells.get(`${pattern_key(alloc)}|${alloc.booking_type}`);
      if (!cell || cell.candidates.length < alloc.count) {
        add(`${alloc.booking_type} ${alloc.route_id}/${alloc.pattern_id}: candidate pool has fewer than ${alloc.count} entries.`);
      } else {
        selected.push(...cell.candidates.slice(0, alloc.count));
      }
    }
    selected.sort((left, right) => left.request_time - right.request_time ||
      left.desired_time - right.desired_time || compare_text(left.route_id, right.route_id) ||
      compare_text(left.booking_type, right.booking_type) || left.origin - right.origin ||
      left.destination - right.destination || compare_text(left.candidate_id, right.candidate_id));
    for (const [req_id, cand] of selected.entries()) {
      req_cands.set(req_id, cand);
      const req = req_by_id.get(req_id);
      if (!req || req.type !== cand.booking_type || req.route_id !== cand.route_id || req.pattern_id !== cand.pattern_id ||
          req.origin !== cand.origin || req.destination !== cand.destination ||
          req.desired_time !== cand.desired_time || req.request_time !== cand.request_time) {
        add(`Request #${req_id}: does not match selected pool candidate ${cand.candidate_id}.`, req_id);
      }
    }
  }
  issues = report;
  draw_issues();
}

function draw_issues() {
  const list = $('issue-list');
  list.replaceChildren();
  $('issue-count').textContent = `${issues.length} issues`;
  $('debug-summary').textContent = issues.length
    ? `${issues.length} generator check issue${issues.length === 1 ? '' : 's'} found${cand_pool ? ' with candidate pool' : ''}${cand_pool && timetable ? ' and timetable' : ''}.`
    : `No issues found in ${reqs.length} requests${cand_pool ? ' and the candidate pool' : ''}${cand_pool && timetable ? ' and timetable' : ''}.`;
  $('issues-check').disabled = false;
  for (const issue of issues.slice(0, 200)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'issue-item';
    button.textContent = issue.message;
    button.disabled = !issue.cand && (issue.req_id === null || !reqs.some((req) => req.id === issue.req_id));
    if (issue.cand) button.addEventListener('click', () => show_cand(issue.cand));
    else if (!button.disabled) button.addEventListener('click', () => show_req(reqs.find((req) => req.id === issue.req_id)));
    list.append(button);
  }
  if (issues.length > 200) {
    const note = document.createElement('p');
    note.className = 'hint';
    note.textContent = `Showing the first 200 of ${issues.length} issues.`;
    list.append(note);
  }
}

function show_req(req) {
  selected_req = req;
  selected_debug = null;
  sel_layer.clearLayers();
  const net = inst.network;
  const org_xy = stop_xy(net, req.origin);
  const dst_xy = stop_xy(net, req.destination);
  const cand = req_cands.get(req.id);
  const trav_min = net.travel_times[`${req.origin},${req.destination}`];
  const cand_trav_min = cand && net.travel_times[`${cand.origin},${cand.destination}`];
  const req_issues = issues.filter((issue) => issue.req_id === req.id);
  const details_panel = $('req-details');
  details_panel.hidden = false;
  details_panel.innerHTML = `<strong>Request #${escape_html(req.id)} · ${escape_html(req.type)}</strong><br>` +
    `${escape_html(stop_name(net, req.origin))} → ${escape_html(stop_name(net, req.destination))}<br>` +
    `Desired ${minute_label(req.desired_time)} · Booked ${minute_label(req.request_time)} · Lead ${req.desired_time - req.request_time} min<br>` +
    `Pickup ${req.time_window.map(minute_label).join('–')} · Matrix travel ${trav_min ?? 'missing'} min` +
    (dist_mat && $('dist-button').getAttribute('aria-pressed') === 'true' ? `<br>Road distance ${dist_label(dist_m(req.origin, req.destination))}` : '') +
    (cand && cand.booking_type === undefined ? `<br>Matching raw pool draw: ${escape_html(cand.candidate_id)}` +
      `<br>Source stops: ${escape_html(cand.source_origin_stop_id)} → ${escape_html(cand.source_destination_stop_id)}` : '') +
    (cand && cand.booking_type !== undefined ? `<br>Selected pool slot: ${escape_html(cand.candidate_id)} · Trip ${escape_html(cand.source_trip_id)}` +
      `<br>Source stops: ${escape_html(cand.source_origin_stop_id)} → ${escape_html(cand.source_destination_stop_id)}` +
      `<br>Destination departure ${minute_label(cand.scheduled_arrival_minute)} · Candidate travel slack ${cand_trav_min === undefined ? 'unavailable' : `${cand.scheduled_arrival_minute - cand.desired_time - cand_trav_min} min`}` : '') +
    (req_issues.length ? `<br><span class="bad">${req_issues.map((issue) => escape_html(issue.message)).join('<br>')}</span>` : '');
  const details = `<strong>Request #${escape_html(req.id)}</strong><br>` +
    `${escape_html(stop_name(net, req.origin))} → ${escape_html(stop_name(net, req.destination))}<br>` +
    `${escape_html(req.type)} · Route ${escape_html(req.route_id)} · Pattern ${escape_html(req.pattern_id)}<br>` +
    `Desired pickup ${minute_label(req.desired_time)}<br>` +
    `Pickup window ${req.time_window.map(minute_label).join(' – ')}<br>` +
    `Booked ${minute_label(req.request_time)} <span class="popup-muted">(relative to service day)</span>`;
  L.polyline([org_xy, dst_xy], { color: '#17342f', weight: 4, opacity: .9, dashArray: '7 6' }).addTo(sel_layer);
  L.circleMarker(org_xy, { radius: 8, color: '#fff', weight: 2, fillColor: book_colors[req.type], fillOpacity: 1 })
    .bindPopup(details)
    .addTo(sel_layer).openPopup();
  L.circleMarker(dst_xy, { radius: 8, color: '#fff', weight: 2, fillColor: '#17342f', fillOpacity: 1 })
    .bindPopup(`<strong>Alight · ${escape_html(stop_name(net, req.destination))}</strong><br>Request #${escape_html(req.id)}`)
    .addTo(sel_layer);
  map.fitBounds(L.latLngBounds([org_xy, dst_xy]).pad(.35), { maxZoom: 14 });
  document.querySelectorAll('.debug-item').forEach((button) => button.classList.toggle('active', false));
  document.querySelectorAll('.req-item').forEach((button) => button.classList.toggle('active', Number(button.dataset.reqId) === req.id));
}

function show_cand(cand) {
  selected_req = null;
  selected_debug = null;
  sel_layer.clearLayers();
  const net = inst.network;
  const trav_min = net.travel_times[`${cand.origin},${cand.destination}`];
  const details_panel = $('req-details');
  details_panel.hidden = false;
  details_panel.innerHTML = `<strong>Candidate ${escape_html(cand.candidate_id)}${cand.booking_type ? ` · ${escape_html(cand.booking_type)}` : ' · raw pool draw'}</strong><br>` +
    `${escape_html(stop_name(net, cand.origin))} → ${escape_html(stop_name(net, cand.destination))}<br>` +
    `Desired ${minute_label(cand.desired_time)}` +
    (cand.request_time === undefined ? '<br>' : ` · Booked ${minute_label(cand.request_time)} · Lead ${cand.desired_time - cand.request_time} min<br>`) +
    `Pickup ${cand.time_window.map(minute_label).join('–')} · Matrix travel ${trav_min ?? 'missing'} min<br>` +
    (dist_mat && $('dist-button').getAttribute('aria-pressed') === 'true' ? `Road distance ${dist_label(dist_m(cand.origin, cand.destination))}<br>` : '') +
    (cand.source_trip_id ? `Trip ${escape_html(cand.source_trip_id)} · ` : '') +
    `Source stops ${escape_html(cand.source_origin_stop_id)} → ${escape_html(cand.source_destination_stop_id)}` +
    (cand.scheduled_arrival_minute === undefined ? '' : `<br>Destination departure ${minute_label(cand.scheduled_arrival_minute)} · Travel slack ${trav_min === undefined ? 'unavailable' : `${cand.scheduled_arrival_minute - cand.desired_time - trav_min} min`}`);
  if (net.coordinates[String(cand.origin)] && net.coordinates[String(cand.destination)]) {
    const org_xy = stop_xy(net, cand.origin);
    const dst_xy = stop_xy(net, cand.destination);
    L.polyline([org_xy, dst_xy], { color: '#b65143', weight: 4, dashArray: '7 6' }).addTo(sel_layer);
    L.circleMarker(org_xy, { radius: 8, color: '#fff', weight: 2, fillColor: '#b65143', fillOpacity: 1 })
      .bindPopup(`<strong>Candidate ${escape_html(cand.candidate_id)}</strong>${cand.source_trip_id ? `<br>Trip ${escape_html(cand.source_trip_id)}` : ''}`)
      .addTo(sel_layer).openPopup();
    L.circleMarker(dst_xy, { radius: 8, color: '#fff', weight: 2, fillColor: '#17342f', fillOpacity: 1 }).addTo(sel_layer);
    map.fitBounds(L.latLngBounds([org_xy, dst_xy]).pad(.35), { maxZoom: 14 });
  }
  document.querySelectorAll('.debug-item').forEach((button) => button.classList.toggle('active', false));
  document.querySelectorAll('.req-item').forEach((button) => button.classList.toggle('active', false));
}

function show_debug(cand) {
  selected_req = null;
  selected_debug = cand;
  sel_layer.clearLayers();
  const net = inst.network;
  const deviation = debug_deviation(cand);
  const status = deviation < 0 ? `${-deviation} min early` : deviation > 0 ? `${deviation} min late` : 'inside feasible pickup bounds';
  const findings = debug_findings.get(cand);
  const details_panel = $('req-details');
  details_panel.hidden = false;
  details_panel.innerHTML = `<strong>Rejected draw ${escape_html(cand.candidate_id)}</strong><br>` +
    `${escape_html(stop_name(net, cand.origin))} → ${escape_html(stop_name(net, cand.destination))}<br>` +
    `${cand.scenario ? `${escape_html(cand.scenario)} · ${escape_html(cand.booking_type)} allocation` : 'raw preference'} · ${escape_html(cand.route_id)}/${escape_html(cand.pattern_id)}<br>` +
    `Reasons: ${cand.rejection_reasons.map((reason) => escape_html(debug_reason(reason))).join(', ')}<br>` +
    `Desired ${minute_label(cand.desired_time)}` +
    (cand.feasible_pickup_bounds ? ` · Feasible ${cand.feasible_pickup_bounds.map(minute_label).join('–')} · ${status}<br>` : '<br>') +
    (cand.request_time === undefined ? '' : `Booked ${minute_label(cand.request_time)} · Lead ${cand.desired_time - cand.request_time} min<br>`) +
    (cand.operating_hours ? `Operating ${cand.operating_hours.map(minute_label).join('–')}` : `Service starts ${minute_label(cand.service_start_minute)}`) +
    ` · Pickup window ${cand.time_window.map(minute_label).join('–')}<br>` +
    `Source stops ${escape_html(cand.source_origin_stop_id)} → ${escape_html(cand.source_destination_stop_id)}` +
    (dist_mat && $('dist-button').getAttribute('aria-pressed') === 'true' ? `<br>Road distance ${dist_label(dist_m(cand.origin, cand.destination))}` : '') +
    (findings.length ? `<br><span class="bad">Debug checks: ${findings.map(escape_html).join(' ')}</span>` : '<br>Debug checks: passed');
  if (net.coordinates[String(cand.origin)] && net.coordinates[String(cand.destination)]) {
    const org_xy = stop_xy(net, cand.origin);
    const dst_xy = stop_xy(net, cand.destination);
    const color = debug_color(cand);
    L.polyline([org_xy, dst_xy], { color, weight: 5, dashArray: '8 6' }).addTo(sel_layer);
    L.circleMarker(org_xy, { radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1 }).addTo(sel_layer);
    L.circleMarker(dst_xy, { radius: 8, color: '#fff', weight: 2, fillColor: '#17342f', fillOpacity: 1 }).addTo(sel_layer);
    map.fitBounds(L.latLngBounds([org_xy, dst_xy]).pad(.35), { maxZoom: 14 });
  }
  document.querySelectorAll('.debug-item').forEach((button) => button.classList.toggle('active',
    button.dataset.candId === cand.candidate_id && button.dataset.scenario === (cand.scenario || '')));
  document.querySelectorAll('.req-item').forEach((button) => button.classList.toggle('active', false));
}

function draw_req_list() {
  const list = $('req-list');
  list.replaceChildren();
  $('list-count').textContent = String(visible_reqs.length).padStart(2, '0');
  if (!visible_reqs.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-list';
    empty.textContent = 'No requests match these filters.';
    list.append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const req of [...visible_reqs].sort((left, right) => left.desired_time - right.desired_time)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `req-item${selected_req?.id === req.id ? ' active' : ''}${issues.some((issue) => issue.req_id === req.id) ? ' flagged' : ''}`;
    button.dataset.reqId = req.id;
    const type = document.createElement('span');
    type.className = `req-type ${req.type}`;
    const main = document.createElement('span');
    main.className = 'req-main';
    const id = document.createElement('span');
    id.className = 'req-id';
    id.textContent = `#${req.id}`;
    const places = document.createElement('span');
    places.className = 'req-places';
    places.textContent = `${stop_name(inst.network, req.origin)} → ${stop_name(inst.network, req.destination)}`;
    const time = document.createElement('span');
    time.className = 'req-time';
    time.textContent = minute_label(req.desired_time);
    main.append(id, places);
    button.append(type, main, time);
    button.addEventListener('click', () => show_req(req));
    fragment.append(button);
  }
  list.append(fragment);
}

/** Aggregate logical stop occurrences that share one physical position. */
function stop_demand(patterns, filtered) {
  const net = inst.network;
  const stops = new Map();
  for (const pattern of patterns) {
    for (const stop_id of pattern.stops) {
      const xy = stop_xy(net, stop_id);
      const key = xy.join(',');
      if (!stops.has(key)) stops.set(key, { xy, names: new Set(), board: 0, alight: 0 });
      stops.get(key).names.add(stop_name(net, stop_id));
    }
  }
  for (const req of filtered) {
    const org_stop = stops.get(stop_xy(net, req.origin).join(','));
    const dst_stop = stops.get(stop_xy(net, req.destination).join(','));
    if (org_stop) org_stop.board++;
    if (dst_stop) dst_stop.alight++;
  }
  return [...stops.values()];
}

/** Draw rejected raw candidates independently of the demand time slider. */
function draw_debug(patterns) {
  const list = $('debug-list');
  list.replaceChildren();
  visible_debug = [];
  $('debug-legend').hidden = !$('debug-mode-check').checked || !debug_data;
  if (!$('debug-mode-check').checked || !debug_data) return;
  const keys = new Set(patterns.map(pattern_key));
  const reason = $('debug-reason').value;
  visible_debug = [...debug_data.rejected_candidates, ...(debug_data.rejected_allocations || [])].filter((cand) =>
    keys.has(pattern_key(cand)) &&
    (!cand.booking_type || $(cand.booking_type === 'prebooked' ? 'prebooked-check' : 'dynamic-check').checked) &&
    (reason === 'all' || cand.rejection_reasons.includes(reason)) &&
    (!$('debug-outside-check').checked || debug_deviation(cand) !== 0));
  visible_debug.sort((left, right) => Math.abs(debug_deviation(right)) - Math.abs(debug_deviation(left)));
  const early = visible_debug.filter((cand) => debug_deviation(cand) < 0).length;
  const late = visible_debug.filter((cand) => debug_deviation(cand) > 0).length;
  $('debug-counts').textContent = `${visible_debug.length} of ${debug_data.rejected_count + (debug_data.rejected_allocation_count || 0)} rejected draws visible · ${early} early · ${late} late · ${visible_debug.length - early - late} booking allocation. Sorted by pickup deviation.`;
  if (selected_debug && !visible_debug.includes(selected_debug)) {
    selected_debug = null;
    $('req-details').hidden = true;
  }
  for (const cand of visible_debug) {
    const deviation = debug_deviation(cand);
    const color = debug_color(cand);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `debug-item${selected_debug === cand ? ' active' : ''}`;
    button.dataset.candId = cand.candidate_id;
    button.dataset.scenario = cand.scenario || '';
    button.style.borderLeftColor = color;
    button.innerHTML = `<strong>${escape_html(cand.candidate_id)}</strong> · ${deviation < 0 ? `${-deviation} min early` : deviation > 0 ? `${deviation} min late` : 'booking allocation'}${debug_findings.get(cand).length ? ' ⚠' : ''}<small>${escape_html(stop_name(inst.network, cand.origin))} → ${escape_html(stop_name(inst.network, cand.destination))} · ${cand.rejection_reasons.map((item) => escape_html(debug_reason(item))).join(', ')}</small>`;
    button.addEventListener('click', () => show_debug(cand));
    list.append(button);
    if (inst.network.coordinates[String(cand.origin)] && inst.network.coordinates[String(cand.destination)]) {
      const org_xy = stop_xy(inst.network, cand.origin);
      const dst_xy = stop_xy(inst.network, cand.destination);
      L.polyline([org_xy, dst_xy], { color, weight: 2, opacity: .55, dashArray: '5 5' })
        .on('click', () => show_debug(cand)).addTo(debug_layer);
      L.circleMarker(org_xy, { radius: 4, color: '#fff', weight: 1, fillColor: color, fillOpacity: .9 })
        .on('click', () => show_debug(cand)).addTo(debug_layer);
    }
  }
  if (selected_debug) show_debug(selected_debug);
}

function draw_map() {
  route_layer.clearLayers();
  stop_layer.clearLayers();
  flow_layer.clearLayers();
  dist_layer.clearLayers();
  debug_layer.clearLayers();
  sel_layer.clearLayers();
  if (!inst) return;

  const net = inst.network;
  const patterns = selected_patterns();
  visible_reqs = filtered_reqs(patterns);
  if (selected_req && !visible_reqs.includes(selected_req)) {
    selected_req = null;
    $('req-details').hidden = true;
  }
  const all_xy = [];

  for (const pattern of patterns) {
    const xy = pattern.stops.map((stop_id) => stop_xy(net, stop_id));
    all_xy.push(...xy);
    const color = pattern_colors[net.patterns.indexOf(pattern) % pattern_colors.length];
    L.polyline(xy, { color: '#fff', weight: 8, opacity: .9, interactive: false }).addTo(route_layer);
    L.polyline(xy, { color, weight: 4, opacity: .95 })
      .bindPopup(`<strong>${escape_html(pattern.label.replace(' -> ', ' → '))}</strong><br><span class="popup-muted">Route ${escape_html(pattern.route_id)} · Pattern ${escape_html(pattern.pattern_id)}</span>`)
      .addTo(route_layer);
  }
  route_bounds = L.latLngBounds(all_xy);

  if (dist_mat && $('dist-button').getAttribute('aria-pressed') === 'true') {
    const seen = new Set();
    for (const pattern of patterns) {
      for (let idx = 1; idx < pattern.stops.length; idx++) {
        const org = pattern.stops[idx - 1];
        const dst = pattern.stops[idx];
        const pair = [net.source_stop_ids[String(org)], net.source_stop_ids[String(dst)]].sort().join('|');
        // In the all-routes view, label shared segments once; choose a direction for its exact distance.
        if ($('pattern-select').value === 'all' && seen.has(pair)) continue;
        seen.add(pair);
        const metres = dist_m(org, dst);
        if (metres === null) continue;
        L.polyline([stop_xy(net, org), stop_xy(net, dst)], { opacity: 0, interactive: false })
          .bindTooltip(dist_label(metres), { permanent: true, direction: 'center', className: 'dist-label' })
          .addTo(dist_layer);
      }
    }
  }

  if ($('flows-check').checked) {
    for (const req of visible_reqs) {
      L.polyline([stop_xy(net, req.origin), stop_xy(net, req.destination)], {
        color: book_colors[req.type], weight: 2, opacity: .24
      }).bindPopup(`<strong>Request #${escape_html(req.id)}</strong><br>${escape_html(stop_name(net, req.origin))} → ${escape_html(stop_name(net, req.destination))}<br>${escape_html(req.type)} · ${minute_label(req.desired_time)}`)
        .addTo(flow_layer);
    }
  }

  const stops = stop_demand(patterns, visible_reqs);
  for (const stop of stops) {
    const total = stop.board + stop.alight;
    L.circleMarker(stop.xy, {
      radius: total ? 5 + Math.sqrt(total) * 2.7 : 3,
      color: total ? '#fff' : '#527d6b', weight: total ? 2 : 1,
      fillColor: total ? '#e79b50' : '#fff', fillOpacity: total ? .85 : .9
    }).bindPopup(`<strong>${[...stop.names].map(escape_html).join(' / ')}</strong><br>${stop.board} boardings · ${stop.alight} alightings<br><span class="popup-muted">${total} visible request endpoints</span>`)
      .addTo(stop_layer);
  }

  draw_debug(patterns);

  $('req-count').textContent = visible_reqs.length;
  $('stop-count').textContent = stops.filter((stop) => stop.board + stop.alight > 0).length;
  $('pattern-count').textContent = patterns.length;
  $('time-value').textContent = minute_label(Number($('time-range').value));
  $('map-title').textContent = $('pattern-select').value === 'all'
    ? `${inst.config.dataset === 'network' ? 'Network' : `Line ${inst.config.dataset}`} · ${inst.config.scenario} demand`
    : patterns[0].label.replace(' -> ', ' → ');
  $('map-kicker').textContent = `${inst.config.service_date} / ${visible_reqs.length} VISIBLE REQUESTS`;
  draw_req_list();
  if (selected_req) show_req(selected_req);
}

function load_inst(data, file_name) {
  if (data.schema_version !== 2 || !data.config || !data.network?.patterns || !data.network?.coordinates || !data.requests?.prebooked || !data.requests?.dynamic) {
    throw new Error('Choose a schema-version-2 scenario instance JSON from data/instances/.');
  }
  inst = data;
  reqs = [...Object.values(data.requests.prebooked), ...Object.values(data.requests.dynamic)];
  cand_pool = null;
  timetable = null;
  dist_mat = null;
  dist_idx = new Map();
  debug_data = null;
  visible_debug = [];
  selected_debug = null;
  debug_findings = new Map();
  selected_req = null;
  $('req-details').hidden = true;
  $('cand-file').disabled = false;
  $('cand-file').value = '';
  $('cand-name').textContent = 'Optional: data/candidate_pool_*.json';
  $('timetable-file').disabled = false;
  $('timetable-file').value = '';
  $('timetable-name').textContent = 'Optional: data/timetable_*.json, with candidate pool';
  $('dist-file').disabled = false;
  $('dist-file').value = '';
  $('dist-name').textContent = 'Optional: data/distance_matrix_550.json';
  $('dist-error').hidden = true;
  $('dist-button').disabled = true;
  $('dist-button').setAttribute('aria-pressed', 'false');
  $('dist-button').textContent = 'Show road distances';
  $('debug-mode-check').disabled = false;
  $('debug-mode-check').checked = false;
  $('debug-tools').hidden = true;
  $('debug-file').value = '';
  $('debug-name').textContent = 'data/debug/rejected_candidates_550.debug.json';
  $('debug-error').hidden = true;
  $('debug-counts').textContent = 'Choose the matching debug file to see rejected candidates.';
  $('debug-warnings').textContent = '';
  $('debug-list').replaceChildren();
  $('debug-reason').replaceChildren(new Option('All reasons', 'all'));
  $('debug-reason').value = 'all';
  $('debug-reason').disabled = true;
  $('debug-outside-check').checked = false;
  $('debug-outside-check').disabled = true;
  $('prebooked-check').checked = true;
  $('dynamic-check').checked = true;
  $('flows-check').checked = false;
  $('issues-check').checked = false;
  const select = $('pattern-select');
  select.replaceChildren(new Option('All routes and directions', 'all'));
  select.value = 'all';
  for (const pattern of data.network.patterns) {
    select.add(new Option(`${pattern.label.replace(' -> ', ' → ')} (${pattern.route_id})`, pattern_key(pattern)));
  }
  select.disabled = false;
  const max_min = Math.max(1440, ...reqs.map((req) => req.desired_time));
  $('time-range').max = Math.ceil(max_min / 60) * 60;
  $('time-range').value = $('time-range').max;
  $('time-range').disabled = false;
  $('fit-button').disabled = false;
  $('file-name').textContent = file_name;
  $('file-error').hidden = true;
  audit_inst();
  draw_map();
  map.fitBounds(route_bounds.pad(.14));
}

$('inst-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    load_inst(JSON.parse(await file.text()), file.name);
  } catch (error) {
    $('file-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('file-error').hidden = false;
  }
});

$('cand-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.schema_version !== 2 || !Array.isArray(data.candidate_pool) || !data.lead_time_rules) {
      throw new Error('Choose a schema-version-2 candidate_pool JSON.');
    }
    cand_pool = data;
    $('cand-name').textContent = file.name;
    $('cand-error').hidden = true;
    audit_inst();
    draw_map();
  } catch (error) {
    $('cand-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('cand-error').hidden = false;
  }
});

$('timetable-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.schema_version !== 2 || !Array.isArray(data.patterns) || !data.service_date) {
      throw new Error('Choose a schema-version-2 timetable JSON.');
    }
    timetable = data;
    $('timetable-name').textContent = file.name;
    $('timetable-error').hidden = true;
    audit_inst();
    draw_map();
  } catch (error) {
    $('timetable-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('timetable-error').hidden = false;
  }
});

$('dist-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    const ids = new Map(data.stop_ids?.map((id, idx) => [id, idx]));
    const src_ids = Object.values(inst.network.source_stop_ids);
    if (data.schema_version !== 1 || !Array.isArray(data.distances_m) ||
        data.distances_m.length !== ids.size || data.distances_m.some((row) => !Array.isArray(row) || row.length !== ids.size) ||
        src_ids.some((id) => !ids.has(id))) {
      throw new Error('Choose a distance matrix matching the loaded instance stops.');
    }
    dist_mat = data;
    dist_idx = ids;
    $('dist-name').textContent = file.name;
    $('dist-error').hidden = true;
    $('dist-button').disabled = false;
    draw_map();
  } catch (error) {
    $('dist-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('dist-error').hidden = false;
  }
});

$('dist-button').addEventListener('click', () => {
  const active = $('dist-button').getAttribute('aria-pressed') !== 'true';
  $('dist-button').setAttribute('aria-pressed', String(active));
  $('dist-button').textContent = active ? 'Hide road distances' : 'Show road distances';
  draw_map();
});

$('debug-mode-check').addEventListener('change', () => {
  $('debug-tools').hidden = !$('debug-mode-check').checked;
  if (!$('debug-mode-check').checked && selected_debug) {
    selected_debug = null;
    $('req-details').hidden = true;
  }
  draw_map();
});

$('debug-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.debug !== true || !Array.isArray(data.rejected_candidates) || !Number.isInteger(data.rejected_count) ||
        (data.rejected_allocations && !Array.isArray(data.rejected_allocations))) {
      throw new Error('Choose a rejected-candidates debug JSON from data/debug/.');
    }
    debug_data = data;
    selected_debug = null;
    $('req-details').hidden = true;
    $('debug-name').textContent = file.name;
    $('debug-error').hidden = true;
    const reasons = [...new Set([...data.rejected_candidates, ...(data.rejected_allocations || [])]
      .flatMap((cand) => cand.rejection_reasons))].sort();
    $('debug-reason').replaceChildren(new Option('All reasons', 'all'));
    for (const reason of reasons) $('debug-reason').add(new Option(debug_reason(reason), reason));
    $('debug-reason').value = 'all';
    $('debug-reason').disabled = false;
    $('debug-outside-check').checked = false;
    $('debug-outside-check').disabled = false;
    audit_debug();
    draw_map();
  } catch (error) {
    $('debug-error').textContent = error instanceof SyntaxError ? 'This file is not valid JSON.' : error.message;
    $('debug-error').hidden = false;
  }
});

for (const id of ['pattern-select', 'prebooked-check', 'dynamic-check', 'time-range', 'flows-check', 'issues-check', 'debug-reason', 'debug-outside-check']) {
  $(id).addEventListener(id === 'time-range' ? 'input' : 'change', draw_map);
}
$('pattern-select').addEventListener('change', () => map.fitBounds(route_bounds.pad(.14)));
$('fit-button').addEventListener('click', () => map.fitBounds(route_bounds.pad(.14)));
