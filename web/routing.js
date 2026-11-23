import { endpoint, route, transformedBox, mountedNodes } from './geometry.js';

// Explicit routing stores ordinary vertices: canvas, JSON and Python exports
// continue to use the same port lead-ins and orthogonal route contract.
const EPS = 1e-7;
const equal = (a, b) => Math.abs(a[0] - b[0]) < EPS && Math.abs(a[1] - b[1]) < EPS;
const inside = (p, b) => p[0] > b[0] + EPS && p[0] < b[2] - EPS
  && p[1] > b[1] + EPS && p[1] < b[3] - EPS;

export function crossesBox(a, b, box) {
  if (Math.abs(a[1] - b[1]) < EPS) return a[1] > box[1] + EPS && a[1] < box[3] - EPS
    && Math.max(a[0], b[0]) > box[0] + EPS && Math.min(a[0], b[0]) < box[2] - EPS;
  if (Math.abs(a[0] - b[0]) < EPS) return a[0] > box[0] + EPS && a[0] < box[2] - EPS
    && Math.max(a[1], b[1]) > box[1] + EPS && Math.min(a[1], b[1]) < box[3] - EPS;
  return true;
}

function compact(points) {
  const out = [];
  for (const point of points) {
    if (out.length && equal(out.at(-1), point)) continue;
    while (out.length > 1) {
      const a = out.at(-2), b = out.at(-1);
      if (!((a[0] === b[0] && b[0] === point[0] && (b[1] - a[1]) * (point[1] - b[1]) >= 0)
        || (a[1] === b[1] && b[1] === point[1] && (b[0] - a[0]) * (point[0] - b[0]) >= 0))) break;
      out.pop();
    }
    out.push(point);
  }
  return out;
}

class Heap {
  items = [];
  push(value) {
    const items = this.items; let i = items.length; items.push(value);
    while (i) { const p = (i - 1) >> 1; if (items[p].score <= value.score) break; items[i] = items[p]; i = p; }
    items[i] = value;
  }
  pop() {
    const items = this.items, first = items[0], last = items.pop();
    if (items.length) {
      let i = 0;
      while (i * 2 + 1 < items.length) {
        let c = i * 2 + 1;
        if (c + 1 < items.length && items[c + 1].score < items[c].score) c++;
        if (items[c].score >= last.score) break;
        items[i] = items[c]; i = c;
      }
      items[i] = last;
    }
    return first;
  }
}

export function avoidObstacles(a, b, obstacles, { page, clearance = 12, maxStates = 60000 } = {}) {
  const fail = message => { throw new Error(message); };
  if (!Number.isFinite(clearance) || clearance < 0) fail('避障间距无效。');
  const boxes = obstacles.map(({ id, box }) => ({ id, box: [box[0] - clearance, box[1] - clearance,
    box[0] + box[2] + clearance, box[1] + box[3] + clearance] }));
  for (const end of [a, b]) {
    if (!end.point?.every(Number.isFinite) || !end.direction?.every(Number.isFinite)
      || end.point.length !== 2 || end.direction.length !== 2
      || ![[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]].some(d => equal(d, end.direction)))
      fail('端口方向不支持正交布线，请使用水平或竖直端口。');
  }
  const outward = (p, q, end) => end.nodeId && end.direction.some(Boolean) && [p, q].every(v => {
    const dx = v[0] - end.point[0], dy = v[1] - end.point[1];
    return Math.abs(dx * end.direction[1] - dy * end.direction[0]) < EPS
      && dx * end.direction[0] + dy * end.direction[1] >= -EPS;
  });
  const blocked = (p, q, obstacle) => crossesBox(p, q, obstacle.box)
    && !(obstacle.id === a.nodeId && outward(p, q, a))
    && !(obstacle.id === b.nodeId && outward(p, q, b));
  // Facing ports closer than two lead-ins need no detour. Also preserve the
  // established simple route whenever it already clears all equipment.
  const simple = route(a, b);
  if (simple.every(p => !page || (p[0] >= 0 && p[1] >= 0 && p[0] <= page.width && p[1] <= page.height))
    && simple.every((p, i) => !i || !boxes.some(o => blocked(simple[i - 1], p, o))))
    return { vertices: [], points: simple };
  const escape = end => {
    let length = end.direction.some(Boolean) ? 20 : 0;
    const own = boxes.find(o => o.id === end.nodeId)?.box;
    const [dx, dy] = end.direction, [x, y] = end.point;
    if (own) {
      if (dx > 0) length = Math.max(length, own[2] - x);
      if (dx < 0) length = Math.max(length, x - own[0]);
      if (dy > 0) length = Math.max(length, own[3] - y);
      if (dy < 0) length = Math.max(length, y - own[1]);
    }
    const point = [x + dx * length, y + dy * length];
    if (boxes.some(o => o.id !== end.nodeId && (inside(end.point, o.box)
      || crossesBox(end.point, point, o.box)))) fail('端口引出段被其他设备遮挡，请先移动设备或三通。');
    return point;
  };
  const start = escape(a), target = escape(b);
  const limits = page ? [0, 0, page.width, page.height] : [
    Math.min(start[0], target[0], ...boxes.map(o => o.box[0])) - 20,
    Math.min(start[1], target[1], ...boxes.map(o => o.box[1])) - 20,
    Math.max(start[0], target[0], ...boxes.map(o => o.box[2])) + 20,
    Math.max(start[1], target[1], ...boxes.map(o => o.box[3])) + 20];
  const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
  const inPage = p => p[0] >= limits[0] - EPS && p[1] >= limits[1] - EPS
    && p[0] <= limits[2] + EPS && p[1] <= limits[3] + EPS;
  if (![a.point, start, target, b.point].every(inPage)) fail('端口或引出段超出纸张，请先调整设备或扩大页面。');
  const startGrid = [clamp(start[0], limits[0], limits[2]), clamp(start[1], limits[1], limits[3])];
  const targetGrid = [clamp(target[0], limits[0], limits[2]), clamp(target[1], limits[1], limits[3])];
  const xs = [...new Set([startGrid[0], targetGrid[0], limits[0], limits[2], ...boxes.flatMap(o => [o.box[0], o.box[2]])])]
    .filter(x => x >= limits[0] && x <= limits[2]).sort((x, y) => x - y);
  const ys = [...new Set([startGrid[1], targetGrid[1], limits[1], limits[3], ...boxes.flatMap(o => [o.box[1], o.box[3]])])]
    .filter(y => y >= limits[1] && y <= limits[3]).sort((x, y) => x - y);
  if (xs.length * ys.length > 120000) fail('障碍数量过多，请减少设备数量后重试。');
  const rows = new Map(), cols = new Map();
  const clear = (p, q, axis) => {
    const cache = axis === 0 ? rows : cols, key = p[1 - axis];
    if (!cache.has(key)) cache.set(key, boxes.filter(o => key > o.box[1 - axis] + EPS && key < o.box[3 - axis] - EPS));
    return !cache.get(key).some(o => crossesBox(p, q, o.box));
  };
  const width = xs.length, startId = ys.indexOf(startGrid[1]) * width + xs.indexOf(startGrid[0]);
  const targetId = ys.indexOf(targetGrid[1]) * width + xs.indexOf(targetGrid[0]);
  const point = id => [xs[id % width], ys[Math.floor(id / width)]];
  const distance = p => Math.abs(p[0] - targetGrid[0]) + Math.abs(p[1] - targetGrid[1]);
  const axisOf = end => end.direction[0] ? 0 : end.direction[1] ? 1 : 2;
  const initial = startId * 3 + axisOf(a), best = new Map([[initial, 0]]), previous = new Map();
  const heap = new Heap(); heap.push({ key: initial, cost: 0, score: distance(startGrid) });
  let found = null, visited = 0;
  while (heap.items.length) {
    const current = heap.pop();
    if (current.cost !== best.get(current.key)) continue;
    if (++visited > maxStates) fail('布线搜索达到上限，请减少障碍或手动调整走线。');
    const id = Math.floor(current.key / 3), axis = current.key % 3, p = point(id);
    if (id === targetId) { found = current.key; break; }
    const x = id % width, y = Math.floor(id / width);
    for (const [nx, ny, nextAxis] of [[x + 1, y, 0], [x - 1, y, 0], [x, y + 1, 1], [x, y - 1, 1]]) {
      if (nx < 0 || nx >= width || ny < 0 || ny >= ys.length) continue;
      const nextId = ny * width + nx, q = point(nextId);
      if (!clear(p, q, nextAxis)) continue;
      // Do not double back into a device along either port lead-in.
      if (id === startId && (q[0] - p[0]) * a.direction[0] + (q[1] - p[1]) * a.direction[1] < -EPS) continue;
      if (nextId === targetId && (p[0] - q[0]) * b.direction[0] + (p[1] - q[1]) * b.direction[1] < -EPS) continue;
      const cost = current.cost + Math.abs(q[0] - p[0]) + Math.abs(q[1] - p[1])
        + (axis !== 2 && axis !== nextAxis ? 16 : 0) + (nextId === targetId && axisOf(b) !== 2 && axisOf(b) !== nextAxis ? 16 : 0);
      const key = nextId * 3 + nextAxis;
      if (cost >= (best.get(key) ?? Infinity)) continue;
      best.set(key, cost); previous.set(key, current.key);
      heap.push({ key, cost, score: cost + distance(q) });
    }
  }
  if (found === null) fail('页面内没有可用通道，请移动设备或扩大页面。');
  const middle = [];
  for (let key = found; key !== undefined; key = previous.get(key)) middle.push(point(Math.floor(key / 3)));
  const vertices = compact(middle.reverse());
  if (vertices.length > 100) fail('避障折点超过 100 个，请简化设备布局。');
  const points = route(a, b, vertices);
  // Check the exact legacy/export route, including fixed 20-unit lead-ins.
  for (let i = 1; i < points.length; i++) {
    for (const obstacle of boxes) {
      if (blocked(points[i - 1], points[i], obstacle)) fail('端口引出空间不足，请移动设备后重试。');
    }
  }
  return { vertices, points };
}

export function routeDiagramEdges(document, nodes, edgeIds) {
  const byId = new Map(nodes.map(n => [n.id, n]));
  const obstacles = nodes.map(n => ({ id: n.id, mount: n.mount,
    box: transformedBox(n.geometry.box, [n.x, n.y], n.rotation) }));
  const changes = [], failures = [];
  for (const edge of document.edges) {
    if (!edgeIds.has(edge.id)) continue;
    try {
      if (nodes.length !== document.nodes.length) throw new Error('设备几何尚未加载完成，请等待更新后重试。');
      const a = { ...endpoint(edge.source, byId, document.junctions), nodeId: edge.source.nodeId };
      const b = { ...endpoint(edge.target, byId, document.junctions), nodeId: edge.target.nodeId };
      const result = avoidObstacles(a, b, obstacles.filter(o => o.mount?.edgeId !== edge.id), { page: document.page });
      if (JSON.stringify(compact(route(a, b, edge.vertices))) !== JSON.stringify(compact(result.points)))
        changes.push({ id: edge.id, vertices: result.vertices });
    } catch (error) { failures.push({ id: edge.id, message: error.message }); }
  }
  return { changes, failures };
}

export function validateRoutedMounts(document, nodes, changes) {
  if (!nodes.some(n => n.mount) || !changes.length) return;
  const byId = new Map(changes.map(c => [c.id, c.vertices]));
  const candidate = { ...document, edges: document.edges.map(e => byId.has(e.id) ? { ...e, vertices: byId.get(e.id) } : e) };
  const resolved = mountedNodes(candidate, nodes), lookup = new Map(resolved.map(n => [n.id, n]));
  // Valves follow their parent route. Check their final positions against every
  // other pipe, including unselected pipes that were clear before this change.
  const valves = resolved.filter(n => n.mount);
  for (const valve of valves.filter(n => byId.has(n.mount.edgeId))) {
    const [x, y, w, h] = transformedBox(valve.geometry.box, [valve.x, valve.y], valve.rotation);
    if (x < 0 || y < 0 || x + w > document.page.width || y + h > document.page.height)
      throw new Error(`挂接阀件 ${valve.title || valve.id} 改线后超出页面，请调整挂接位置。`);
    for (const other of resolved) {
      if (other.id === valve.id) continue;
      const [ox, oy, ow, oh] = transformedBox(other.geometry.box, [other.x, other.y], other.rotation);
      if (Math.min(x + w, ox + ow) > Math.max(x, ox) + EPS
        && Math.min(y + h, oy + oh) > Math.max(y, oy) + EPS)
        throw new Error(`挂接阀件 ${valve.title || valve.id} 改线后与设备 ${other.title || other.id} 重叠，请调整挂接位置。`);
    }
  }
  for (const edge of candidate.edges) {
    const relevant = byId.has(edge.id)
      ? valves.filter(valve => valve.mount.edgeId !== edge.id)
      : valves.filter(valve => valve.mount.edgeId !== edge.id && byId.has(valve.mount.edgeId));
    if (!relevant.length) continue;
    const points = route(endpoint(edge.source, lookup, candidate.junctions), endpoint(edge.target, lookup, candidate.junctions), edge.vertices);
    for (const valve of relevant) {
      const [x, y, w, h] = transformedBox(valve.geometry.box, [valve.x, valve.y], valve.rotation);
      if (points.some((p, i) => i && crossesBox(points[i - 1], p, [x - 12, y - 12, x + w + 12, y + h + 12])))
        throw new Error(`挂接阀件 ${valve.title || valve.id} 随改线移动后会挡住管路 ${edge.id}，请先调整挂接位置或分批布线。`);
    }
  }
}
