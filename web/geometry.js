/* Diagram units: x right, y down. Keep route() in sync with rrplot.scene. */
export function fitViewport(boxes, width, height, padding = 32) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= padding * 2
    || height <= padding * 2 || !Number.isFinite(padding) || padding < 0)
    throw new Error('画布空间不足，请展开绘图区域后重试。');
  if (!boxes.length || boxes.some(box => !Array.isArray(box) || box.length !== 4
    || box.some(v => !Number.isFinite(v)) || box[2] < 0 || box[3] < 0))
    throw new Error('无法确定内容边界，请等待图纸更新后重试。');
  const left = Math.min(...boxes.map(b => b[0])), top = Math.min(...boxes.map(b => b[1]));
  const right = Math.max(...boxes.map(b => b[0] + b[2])), bottom = Math.max(...boxes.map(b => b[1] + b[3]));
  const scale = Math.max((right - left) / (width - padding * 2),
    (bottom - top) / (height - padding * 2), 100 / width);
  const w = width * scale, h = height * scale;
  return { x: (left + right - w) / 2, y: (top + bottom - h) / 2, w, h };
}

export function translateDocument(document, dx, dy) {
  const moved = structuredClone(document);
  const shift = item => { item.x += dx; item.y += dy; };
  moved.nodes.forEach(shift);
  moved.junctions.forEach(shift);
  // Attached labels already follow their nodes; their coordinates are local offsets.
  moved.labels.filter(label => !label.nodeId && !label.edgeId).forEach(shift);
  moved.edges.forEach(edge => {
    edge.vertices = edge.vertices.map(([x, y]) => [x + dx, y + dy]);
  });
  return moved;
}

export function layoutPage(document, boxes, action, margin = 40) {
  if (!['center', 'fit'].includes(action)) throw new Error('请选择内容居中或页面适配内容。');
  if (action === 'fit' && (!Number.isFinite(margin) || margin < 10 || margin > 500))
    throw new Error('页面留白必须为 10～500 的数字。');
  if (!boxes.length) {
    if (['nodes', 'edges', 'junctions', 'labels'].some(name => document[name].length))
      throw new Error('无法确定图纸内容边界，请等待图纸更新后重试。');
    return structuredClone(document);
  }
  if (boxes.some(box => !Array.isArray(box) || box.length !== 4
    || box.some(v => !Number.isFinite(v)) || box[2] < 0 || box[3] < 0))
    throw new Error('图纸内容边界无效，请等待图纸更新后重试。');
  const x = Math.min(...boxes.map(b => b[0])), y = Math.min(...boxes.map(b => b[1]));
  const w = Math.max(...boxes.map(b => b[0] + b[2])) - x;
  const h = Math.max(...boxes.map(b => b[1] + b[3])) - y;
  let width = document.page.width, height = document.page.height, dx, dy;
  if (action === 'fit') {
    width = Math.max(100, Math.ceil(w + margin * 2 - 1e-4));
    height = Math.max(100, Math.ceil(h + margin * 2 - 1e-4));
    if (width > 4000 || height > 4000) throw new Error('适配后页面超过 4000 单位，请先缩小内容范围或减少留白。');
  } else if (w > width + 1e-4 || h > height + 1e-4) {
    throw new Error('内容大于当前页面，请先使用“页面适配内容”。');
  }
  dx = (width - w) / 2 - x; dy = (height - h) / 2 - y;
  const result = translateDocument(document, Math.abs(dx) < 1e-4 ? 0 : dx, Math.abs(dy) < 1e-4 ? 0 : dy);
  Object.assign(result.page, { width, height });
  for (const name of ['nodes', 'junctions', 'labels', 'edges']) {
    for (const item of result[name]) {
      const values = name === 'edges' ? item.vertices.flat() : [item.x, item.y];
      if (values.some(v => !Number.isFinite(v) || Math.abs(v) > 100000))
        throw new Error('排版后坐标超出允许范围，请先调整内容位置。');
    }
  }
  return result;
}

export function rotate([x, y], angle) {
  const c = Math.round(Math.cos(angle * Math.PI / 180) * 1e12) / 1e12;
  const s = Math.round(Math.sin(angle * Math.PI / 180) * 1e12) / 1e12;
  return [+(c * x - s * y).toFixed(8), +(s * x + c * y).toFixed(8)];
}

export function transformedBox([x, y, width, height], position, rotation = 0) {
  const corners = [[x, y], [x + width, y], [x, y + height], [x + width, y + height]]
    .map(point => rotate(point, rotation).map((v, i) => v + position[i]));
  const left = Math.min(...corners.map(p => p[0])), top = Math.min(...corners.map(p => p[1]));
  return [left, top, Math.max(...corners.map(p => p[0])) - left, Math.max(...corners.map(p => p[1])) - top];
}

export function selectInBox(candidates, start, end, base = []) {
  const left = Math.min(start[0], end[0]), right = Math.max(start[0], end[0]);
  const top = Math.min(start[1], end[1]), bottom = Math.max(start[1], end[1]);
  const key = ref => ref.kind + ':' + ref.id;
  const available = new Set(candidates.map(key)), result = new Map();
  for (const ref of base) if (available.has(key(ref))) result.set(key(ref), { kind: ref.kind, id: ref.id });
  for (const { kind, id, box: [x, y, width, height] } of candidates) {
    if (x >= left && y >= top && x + width <= right && y + height <= bottom)
      result.set(key({ kind, id }), { kind, id });
  }
  return [...result.values()];
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

export function projectOnRoute(points, point) {
  const lengths = points.slice(1).map((b, i) => Math.hypot(b[0] - points[i][0], b[1] - points[i][1]));
  const total = lengths.reduce((sum, length) => sum + length, 0);
  let travelled = 0, best = { point: points[0], at: 0, distance: Infinity };
  lengths.forEach((length, i) => {
    const a = points[i], delta = points[i + 1].map((v, j) => v - a[j]);
    const t = length ? Math.max(0, Math.min(1, point.reduce((sum, v, j) => sum + (v - a[j]) * delta[j], 0) / length ** 2)) : 0;
    const projected = a.map((v, j) => v + delta[j] * t), distance = Math.hypot(...point.map((v, j) => v - projected[j]));
    if (distance < best.distance) best = { point: projected, at: total ? (travelled + t * length) / total : 0, distance };
    travelled += length;
  });
  return best;
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
  const { point, start } = along(points, fraction);
  // Use the travelled segment, including when the route crosses itself.
  const index = points.indexOf(start);
  return {
    point,
    index,
    prefix: [...points.slice(1, index + 1), point],
    suffix: [point, ...points.slice(index + 1, -1)],
  };
}
