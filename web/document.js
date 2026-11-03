/* Pure document edits: each result can be committed as one undo step. */
const collections = { node: 'nodes', junction: 'junctions', label: 'labels', edge: 'edges' };
const key = ref => JSON.stringify([ref.kind, ref.id]);
function localOffset([x, y], rotation) {
  const angle = -rotation * Math.PI / 180, c = Math.round(Math.cos(angle)), s = Math.round(Math.sin(angle));
  return [c * x - s * y, s * x + c * y];
}

function selectedRefs(document, selection) {
  const refs = new Map();
  for (const ref of selection) {
    if (document[collections[ref.kind]]?.some(item => item.id === ref.id))
      refs.set(key(ref), { kind: ref.kind, id: ref.id });
  }
  return [...refs.values()];
}

export function copySelection(document, selection, newId, offset = [20, 20]) {
  const refs = selectedRefs(document, selection).filter(ref => ref.kind !== 'edge');
  const selected = new Set(refs.map(key)), ids = new Map();
  const used = new Set(Object.values(collections).flatMap(name => document[name].map(item => item.id)));
  const result = structuredClone(document);
  const allocate = (kind, original) => {
    const id = newId(kind);
    if (typeof id !== 'string' || !id || used.has(id)) throw new Error('无法生成唯一对象 ID，请重试复制。');
    used.add(id); ids.set(key({ kind, id: original }), id); return id;
  };
  const shift = item => { item.x += offset[0]; item.y += offset[1]; };
  for (const kind of ['node', 'junction']) {
    for (const item of document[collections[kind]]) {
      if (!selected.has(key({ kind, id: item.id }))) continue;
      const copy = structuredClone(item); copy.id = allocate(kind, item.id); shift(copy);
      result[collections[kind]].push(copy);
    }
  }
  const remap = ref => ref.nodeId
    ? ids.has(key({ kind: 'node', id: ref.nodeId })) && { ...ref, nodeId: ids.get(key({ kind: 'node', id: ref.nodeId })) }
    : ids.has(key({ kind: 'junction', id: ref.junctionId })) && { junctionId: ids.get(key({ kind: 'junction', id: ref.junctionId })) };
  for (const edge of document.edges) {
    const source = remap(edge.source), target = remap(edge.target);
    if (!source || !target) continue;
    result.edges.push({ ...structuredClone(edge), id: allocate('edge', edge.id), source, target,
      vertices: edge.vertices.map(p => p.map((v, i) => v + offset[i])) });
  }
  for (const label of document.labels) {
    const parent = ids.get(key({ kind: 'node', id: label.nodeId }));
    const pipe = ids.get(key({ kind: 'edge', id: label.edgeId }));
    if (!parent && !pipe && !selected.has(key({ kind: 'label', id: label.id }))) continue;
    const copy = structuredClone(label); copy.id = allocate('label', label.id);
    if (parent) copy.nodeId = parent;
    else if (pipe) copy.edgeId = pipe;
    else if (label.nodeId) {
      const delta = localOffset(offset, document.nodes.find(n => n.id === label.nodeId).rotation);
      copy.x += delta[0]; copy.y += delta[1];
    } else shift(copy);
    result.labels.push(copy);
  }
  for (const name of Object.values(collections)) {
    if (result[name].length > 2000) throw new Error('复制后对象数量超过上限（每类最多 2000 项）。');
    for (const item of result[name].slice(document[name].length)) {
      const values = name === 'edges' ? item.vertices.flat() : [item.x, item.y];
      if (values.some(v => !Number.isFinite(v) || Math.abs(v) > 100000)) throw new Error('复制后坐标超出允许范围。');
    }
  }
  return { document: result, selection: refs.map(ref => ({ ...ref, id: ids.get(key(ref)) })) };
}

export function translateSelection(document, selection, offset) {
  const selected = new Set(selectedRefs(document, selection).map(key));
  const moving = (kind, id) => selected.has(key({ kind, id }));
  const result = structuredClone(document);
  const movedEndpoint = ref => ref.nodeId ? moving('node', ref.nodeId) : moving('junction', ref.junctionId);
  const movedEdges = new Set(document.edges.filter(e => [e.source, e.target].every(movedEndpoint)).map(e => e.id));
  for (const kind of ['node', 'junction']) {
    for (const item of result[collections[kind]]) if (moving(kind, item.id)) {
      item.x += offset[0]; item.y += offset[1];
    }
  }
  for (const label of result.labels) {
    if (!moving('label', label.id) || moving('node', label.nodeId) || movedEdges.has(label.edgeId)) continue;
    const delta = label.nodeId ? localOffset(offset, document.nodes.find(n => n.id === label.nodeId).rotation) : offset;
    label.x += delta[0]; label.y += delta[1];
  }
  for (const edge of result.edges) if ([edge.source, edge.target].every(movedEndpoint))
    edge.vertices = edge.vertices.map(p => p.map((v, i) => v + offset[i]));
  return result;
}

export function deleteSelection(document, selection, routes = new Map()) {
  const selected = new Set(selectedRefs(document, selection).map(key));
  const result = structuredClone(document);
  routes = new Map(routes);
  const removing = (kind, id) => selected.has(key({ kind, id }));
  result.nodes = result.nodes.filter(n => !removing('node', n.id));
  result.labels = result.labels.filter(l => !removing('label', l.id) && !removing('node', l.nodeId));
  result.edges = result.edges.filter(e => !removing('edge', e.id)
    && ![e.source, e.target].some(ref => removing('node', ref.nodeId)));
  for (const junction of document.junctions.filter(j => removing('junction', j.id))) {
    const incident = result.edges.filter(e => [e.source, e.target].some(ref => ref.junctionId === junction.id));
    const incoming = incident.find(e => e.target.junctionId === junction.id);
    const outgoing = incident.find(e => e.source.junctionId === junction.id);
    result.edges = result.edges.filter(e => !incident.includes(e));
    if (incident.length === 2 && incoming && outgoing && incoming !== outgoing) {
      const a = routes.get(incoming.id), b = routes.get(outgoing.id);
      const points = a && b ? [...a, ...b.slice(1)] : null;
      const vertices = points ? points.slice(1, -1) : [...incoming.vertices, ...outgoing.vertices];
      if (vertices.length > 100) throw new Error('合并后的管路折点超过 100 个，请先清除部分折点再删除三通。');
      result.edges.push({ ...incoming, target: outgoing.target, vertices });
      const attached = result.labels.filter(l => [incoming.id, outgoing.id].includes(l.edgeId));
      if (attached.length) {
        if (!points) throw new Error('无法计算管路状态点位置，请等待图纸更新后重试。');
        const length = path => path.slice(1).reduce((sum, p, i) => sum + Math.hypot(p[0] - path[i][0], p[1] - path[i][1]), 0);
        const first = length(a), total = first + length(b);
        for (const label of attached) {
          label.at = total ? (label.edgeId === incoming.id ? label.at * first : first + label.at * (total - first)) / total : 0;
          label.edgeId = incoming.id;
        }
      }
      if (points) routes.set(incoming.id, points);
    }
  }
  result.junctions = result.junctions.filter(j => !removing('junction', j.id));
  const remaining = new Set(result.edges.map(e => e.id));
  result.labels = result.labels.filter(l => !l.edgeId || remaining.has(l.edgeId));
  return result;
}

export function reverseEdge(document, edgeId, points = null) {
  const result = structuredClone(document), edge = result.edges.find(e => e.id === edgeId);
  const vertices = points ? points.slice(1, -1).reverse() : [...edge.vertices].reverse();
  if (vertices.length > 100) throw new Error('反向后的管路折点超过 100 个，请先清除部分折点。');
  [edge.source, edge.target] = [edge.target, edge.source]; edge.vertices = vertices;
  for (const label of result.labels) if (label.edgeId === edgeId) label.at = 1 - label.at;
  return result;
}

export function splitEdgeLabels(labels, edgeId, nextId, fraction = .5) {
  return labels.map(label => {
    if (label.edgeId !== edgeId) return { ...label };
    return label.at <= fraction ? { ...label, at: label.at / fraction }
      : { ...label, edgeId: nextId, at: (label.at - fraction) / (1 - fraction) };
  });
}
