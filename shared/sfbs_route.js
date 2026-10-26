/* Shared SFBS route order, line style, and stop labels for both maps. */
function sfbsRoute(stopIds, stops) {
  const points = stopIds.map((id, index) => {
    const stop = stops.get(`Stop_${id}`);
    if (!stop) throw new Error(`Missing route stop Stop_${id}.`);
    return {stop, number: index + 1, coordinates: [stop.lat, stop.lon]};
  });
  const segments = points.slice(1).map((to, index) => {
    const from = points[index];
    return {from: from.stop.name, to: to.stop.name,
      coordinates: [from.coordinates, to.coordinates],
      dashArray: from.stop.class === 'optional' || to.stop.class === 'optional' ? '7 6' : undefined};
  });
  return {points, segments};
}

function sfbsStopStyle(stopClass) {
  return stopClass === 'mandatory'
    ? {radius: 7, color: '#fff', weight: 2, fillColor: '#174b9b', fillOpacity: 1}
    : {radius: 7, color: '#174b9b', weight: 2, dashArray: '3 2',
      fillColor: '#6baddb', fillOpacity: 1};
}

function sfbsNumberStops(markers, routes) {
  const numbers = new Map();
  for (const route of routes) {
    for (const point of route.points) {
      const name = point.stop.name;
      if (!numbers.has(name)) numbers.set(name, {order: [], stopClass: point.stop.class});
      numbers.get(name).order.push(point.number);
    }
  }
  for (const [name, marker] of markers) {
    const entry = numbers.get(name);
    const className = entry && `sfbs-sequence sfbs-${entry.stopClass}`;
    if (!entry || marker.getTooltip()?.options.className !== className) {
      marker.closeTooltip();
      marker.unbindTooltip();
    }
    if (!entry) continue;
    const label = entry.order.join(' / ');
    if (marker.getTooltip()) marker.setTooltipContent(label);
    else marker.bindTooltip(label, {permanent: true, direction: 'top', className});
  }
}
