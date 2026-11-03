/* Read-only checks. Unused ports are valid: many glyphs offer alternate ports. */
export function inspectDiagram(document, { nodes = [], routes = new Map(), bounds = [] } = {}) {
  const issues = [], geometry = new Map(nodes.map(n => [n.id, n.geometry]));
  const degrees = new Map(), owners = new Map();
  const owner = ref => JSON.stringify(ref.nodeId !== undefined ? ['node', ref.nodeId] : ['junction', ref.junctionId]);
  const port = ref => ref.nodeId !== undefined
    ? JSON.stringify(['node', ref.nodeId, geometry.get(ref.nodeId)?.ports[ref.portId]?.point || ref.portId])
    : JSON.stringify(['junction', ref.junctionId]);
  const add = (code, ref, title, detail) => issues.push({ code, ref, title, detail });
  for (const [kind, items] of [['node', document.nodes], ['junction', document.junctions]]) {
    for (const item of items) {
      const id = JSON.stringify([kind, item.id]);
      degrees.set(id, new Set()); owners.set(id, { kind, id: item.id });
    }
  }
  // Remove redundant straight-through vertices, but retain a path that doubles back.
  const simplify = points => {
    const result = [];
    for (const point of points) {
      const p = point.map(v => +v.toFixed(6));
      if (result.length && p.every((v, i) => v === result.at(-1)[i])) continue;
      while (result.length >= 2) {
        const a = result.at(-2), b = result.at(-1);
        const ab = b.map((v, i) => v - a[i]), bc = p.map((v, i) => v - b[i]);
        if (Math.abs(ab[0] * bc[1] - ab[1] * bc[0]) > 1e-8 || ab[0] * bc[0] + ab[1] * bc[1] < 0) break;
        result.pop();
      }
      result.push(p);
    }
    return result;
  };
  const seen = new Map();
  for (const edge of document.edges) {
    for (const ref of [edge.source, edge.target]) degrees.get(owner(ref))?.add(edge.id);
    const source = port(edge.source), target = port(edge.target), ref = { kind: 'edge', id: edge.id };
    const points = routes.get(edge.id);
    if (source === target) add('same-endpoint', ref, '管路两端连接到同一端口或三通', '请选择管路属性中的“重接起点”或“重接终点”，核对连接。');
    else if (points?.length && points.every(p => p.every((v, i) => Math.abs(v - points[0][i]) < 1e-6)))
      add('zero-length', ref, '管路长度为零', '两端位于同一位置，请检查设备位置或端点连接。');
    if (points?.length) {
      const path = simplify(points), forward = JSON.stringify([source, target, path]);
      const backward = JSON.stringify([target, source, [...path].reverse()]);
      const key = forward < backward ? forward : backward;
      if (seen.has(key)) add('duplicate-edge', ref, '管路与另一条管路完全重合', '端点和走线相同（忽略流向与样式），请确认是否重复绘制。');
      else seen.set(key, edge.id);
    }
  }
  for (const [id, connected] of degrees) {
    const ref = owners.get(id);
    if (ref.kind === 'node' && !connected.size)
      add('isolated-node', ref, '设备未连接管路', '该设备没有接管，请连接端口或确认是否需要保留。');
    if (ref.kind === 'junction' && connected.size < 2)
      add('open-junction', ref, connected.size ? '三通仅连接一条管路' : '三通未连接管路', '请补充连接，或确认是否需要保留该三通。');
  }
  const boxes = [...bounds];
  for (const edge of document.edges) {
    const points = routes.get(edge.id);
    if (!points?.length) continue;
    const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
    const x = Math.min(...xs), y = Math.min(...ys);
    boxes.push({ kind: 'edge', id: edge.id, box: [x, y, Math.max(...xs) - x, Math.max(...ys) - y] });
  }
  const outside = new Set();
  for (const { kind, id, box: [x, y, w, h] } of boxes) {
    const key = JSON.stringify([kind, id]);
    if (!outside.has(key) && (x < -1e-6 || y < -1e-6 || x + w > document.page.width + 1e-6 || y + h > document.page.height + 1e-6)) {
      outside.add(key);
      add('outside-page', { kind, id }, '对象超出页面边界', '导出时可能显示不完整，请调整位置、走线或页面尺寸。');
    }
  }
  return issues;
}
