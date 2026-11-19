/* Read-only checks. Unused ports are valid: many glyphs offer alternate ports. */
export function inspectDiagram(document, { nodes = [], routes = new Map(), bounds = [], visual = false } = {}) {
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
  for (const node of document.nodes) if (node.mount) {
    const edge = document.edges.find(e => e.id === node.mount.edgeId);
    if (edge) degrees.get(JSON.stringify(['node', node.id]))?.add(edge.id);
    else add('invalid-mount', { kind: 'node', id: node.id }, '挂接管路不存在', '请重新选择挂接管路或解除挂接。');
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
  if (visual) issues.push(...inspectVisualQuality(document, { nodes, routes, bounds }));
  return issues;
}

/* Conservative geometry hints, only on demand. Never move or rewrite objects. */
export function inspectVisualQuality(document, { nodes = [], routes = new Map(), bounds = [] } = {}) {
  const issues = [], byId = new Map(nodes.map(n => [n.id, n]));
  const devices = bounds.filter(b => b.kind === 'node' && byId.has(b.id));
  const labels = bounds.filter(b => b.kind === 'label');
  const overlap = (a, b, inset = 2) => Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]) > inset
    && Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]) > inset;
  const crosses = (points, box, inset) => {
    const [x, y, w, h] = box, left = x + inset, right = x + w - inset, top = y + inset, bottom = y + h - inset;
    if (left >= right || top >= bottom) return false;
    for (let i = 1; i < (points?.length || 0); i++) {
      const a = points[i - 1], b = points[i];
      let low = 0, high = 1, hit = true;
      for (let axis = 0; axis < 2; axis++) {
        const min = axis ? top : left, max = axis ? bottom : right, d = b[axis] - a[axis];
        if (Math.abs(d) < 1e-8) { if (a[axis] <= min || a[axis] >= max) { hit = false; break; } }
        else { const t1 = (min - a[axis]) / d, t2 = (max - a[axis]) / d;
          low = Math.max(low, Math.min(t1, t2)); high = Math.min(high, Math.max(t1, t2)); }
      }
      if (hit && high - low > 1e-6) return true;
    }
    return false;
  };
  const add = (code, ref, title, detail) => {
    if (issues.length < 200) issues.push({ code, ref, title, detail, severity: 'hint' });
  };
  for (let i = 0; i < devices.length; i++) for (let j = i + 1; j < devices.length; j++) {
    const a = devices[i], b = devices[j];
    if (overlap(a.box, b.box, 6)) add('device-overlap', { kind: 'node', id: b.id }, '设备外形可能重叠',
      `与设备 ${byId.get(a.id).title || a.id} 的包围框相交，请核对间距；旋转图元按包围框估算。`);
  }
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    if (overlap(labels[i].box, labels[j].box)) add('label-overlap', { kind: 'label', id: labels[j].id },
      '文字可能相互重叠', '文字边界相交，请核对标签位置；仅作排版提示。');
  }
  for (const edge of document.edges) {
    const points = routes.get(edge.id);
    if (!points?.length) continue;
    for (const device of devices) {
      if ([edge.source, edge.target].some(ref => ref.nodeId === device.id) || byId.get(device.id).mount?.edgeId === edge.id) continue;
      if (crosses(points, device.box, 6)) add('pipe-through-device', { kind: 'edge', id: edge.id },
        '管路可能穿过其他设备', `走线经过设备 ${byId.get(device.id).title || device.id} 的包围框内部，请核对走线或设备位置。`);
    }
    for (const label of labels) if (crosses(points, label.box, 1)) add('label-on-pipe', { kind: 'label', id: label.id },
      '文字可能压住管路', `文字边界与管路 ${edge.id} 相交，请核对文字偏移；白底状态点也会提示。`);
  }
  return issues;
}
