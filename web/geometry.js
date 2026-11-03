/* Diagram units: x right, y down. Keep route() in sync with rrplot.scene. */
export function translateDocument(document, dx, dy) {
  const moved = structuredClone(document);
  const shift = item => { item.x += dx; item.y += dy; };
  moved.nodes.forEach(shift);
  moved.junctions.forEach(shift);
  // Attached labels already follow their nodes; their coordinates are local offsets.
  moved.labels.filter(label => !label.nodeId).forEach(shift);
  moved.edges.forEach(edge => {
    edge.vertices = edge.vertices.map(([x, y]) => [x + dx, y + dy]);
  });
  return moved;
}

export function rotate([x, y], angle) {
  const c = Math.round(Math.cos(angle * Math.PI / 180) * 1e12) / 1e12;
  const s = Math.round(Math.sin(angle * Math.PI / 180) * 1e12) / 1e12;
  return [+(c * x - s * y).toFixed(8), +(s * x + c * y).toFixed(8)];
}

export function endpoint(ref, nodes, junctions) {
  if (ref.junctionId) {
    const j = junctions.find(j => j.id === ref.junctionId);
    return { point: [j.x, j.y], direction: [0, 0] };
  }
  const n = nodes.find(n => n.id === ref.nodeId);
  const p = n.geometry.ports[ref.portId];
  const [x, y] = rotate(p.point, n.rotation);
  return { point: [n.x + x, n.y + y], direction: rotate(p.direction, n.rotation) };
}

export function route(a, b, vertices = []) {
  const same = (p, q) => p[0] === q[0] && p[1] === q[1];
  const delta = b.point.map((v, i) => v - a.point[i]);
  const dot = (p, q) => p.reduce((sum, v, i) => sum + v * q[i], 0);
  if (!vertices.length && (a.point[0] === b.point[0] || a.point[1] === b.point[1])
      && dot(a.direction, delta) >= 0 && dot(b.direction, delta) <= 0) {
    return [a.point, b.point];
  }
  const pts = [a.point];
  if (a.direction.some(Boolean)) pts.push(a.point.map((v, i) => v + a.direction[i] * 20));
  pts.push(...vertices);
  if (b.direction.some(Boolean)) pts.push(b.point.map((v, i) => v + b.direction[i] * 20));
  pts.push(b.point);
  const out = [pts[0]];
  for (const cur of pts.slice(1)) {
    const prev = out.at(-1);
    if (prev[0] !== cur[0] && prev[1] !== cur[1]) {
      let corner;
      if (out.length >= 2 && out.at(-2)[1] === prev[1]) corner = [cur[0], prev[1]];
      else corner = [prev[0], cur[1]];
      out.push(corner);
    }
    out.push(cur);
  }
  const result = out.filter((p, i) => !i || !same(p, out[i - 1]));
  return result.length > 1 ? result : [a.point, b.point];
}

export function along(points, fraction) {
  const lengths = points.slice(1).map((p, i) => Math.hypot(p[0] - points[i][0], p[1] - points[i][1]));
  const total = lengths.reduce((a, b) => a + b, 0);
  let distance = total * fraction;
  for (let i = 0; i < lengths.length; i++) {
    if (distance <= lengths[i] || i === lengths.length - 1) {
      const t = lengths[i] ? distance / lengths[i] : 0;
      const a = points[i], b = points[i + 1];
      return { point: a.map((v, j) => v + (b[j] - v) * t),
        direction: lengths[i] ? a.map((v, j) => (b[j] - v) / lengths[i]) : [1, 0],
        start: a, end: b, length: lengths[i] };
    }
    distance -= lengths[i];
  }
  return { point: points[0], direction: [1, 0], length: 0, start: points[0], end: points[0] };
}

export function nearestSegment(points, point) {
  let best = { index: 0, distance: Infinity };
  points.slice(1).forEach((b, i) => {
    const a = points[i];
    const v = b.map((x, j) => x - a[j]);
    const len = v[0] ** 2 + v[1] ** 2;
    const t = len ? Math.max(0, Math.min(1, ((point[0] - a[0]) * v[0] + (point[1] - a[1]) * v[1]) / len)) : 0;
    const distance = Math.hypot(...point.map((x, j) => x - a[j] - t * v[j]));
    if (distance < best.distance) best = { index: i, distance };
  });
  return best.index;
}

// Port lead-ins stay fixed; only offer handles where a usable span remains.
export function editableSegments(source, target, vertices = []) {
  const points = route(source, target, vertices), segments = [];
  for (let index = 0; index < points.length - 1; index++) {
    const a = points[index], b = points[index + 1];
    const axis = a[1] === b[1] ? 1 : 0, alongAxis = 1 - axis;
    const start = index === 0 ? source.point.map((v, i) => v + source.direction[i] * 20) : a;
    const end = index === points.length - 2 ? target.point.map((v, i) => v + target.direction[i] * 20) : b;
    if ((end[alongAxis] - start[alongAxis]) * Math.sign(b[alongAxis] - a[alongAxis]) < 24) continue;
    segments.push({ index, axis, start, end, point: start.map((v, i) => (v + end[i]) / 2) });
  }
  return segments;
}

export function moveSegment(source, target, vertices, index, offset) {
  const segment = editableSegments(source, target, vertices).find(s => s.index === index);
  if (!segment || !offset) return vertices.map(p => [...p]);
  const points = route(source, target, vertices), { axis, start, end } = segment;
  const shift = p => p.map((v, i) => i === axis ? v + offset : v);
  const prefix = index === 0 ? [source.point, start] : points.slice(0, index);
  const suffix = index === points.length - 2 ? [end, target.point] : points.slice(index + 2);
  return [...prefix, shift(start), shift(end), ...suffix].slice(1, -1);
}

// Split a routed polyline while retaining the exact split point in both
// halves.  This is used when inserting a junction into an existing edge;
// explicit endpoints keep the two rendered edges anchored to the junction
// even when the original route contains corners or port lead-ins.
export function splitRoute(points, fraction = .5) {
  const { point } = along(points, fraction);
  const index = nearestSegment(points, point);
  return {
    point,
    index,
    prefix: [...points.slice(1, index + 1), point],
    suffix: [point, ...points.slice(index + 1, -1)],
  };
}
