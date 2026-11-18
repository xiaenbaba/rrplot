/* Searchable object descriptions; browsing never mutates the drawing. */
const groups = { node: ['nodes', '设备'], edge: ['edges', '管路'], junction: ['junctions', '三通'], label: ['labels', '文字'] };
const normalized = value => String(value ?? '').normalize('NFKC').toLowerCase();

export function objectIndex(document, catalog = []) {
  const nodes = new Map(document.nodes.map(item => [item.id, item]));
  const edges = new Map(document.edges.map(item => [item.id, item]));
  const names = new Map(catalog.map(entry => [entry.type, entry.label]));
  const endpointName = ref => ref.nodeId
    ? `${nodes.get(ref.nodeId)?.title || ref.nodeId} · ${ref.portId}` : `三通 · ${ref.junctionId}`;
  const edgeName = edge => `${endpointName(edge.source)} → ${endpointName(edge.target)}`;
  const edgeSearch = edge => [edgeName(edge), edge.source.nodeId, edge.source.junctionId,
    edge.target.nodeId, edge.target.junctionId].filter(Boolean).join(' ');
  const result = [];
  for (const [kind, [collection, type]] of Object.entries(groups)) {
    for (const item of document[collection]) {
      const title = kind === 'node' ? item.title || item.id : kind === 'edge' ? edgeName(item)
        : kind === 'label' ? item.text || '空文字' : item.id;
      const parent = kind === 'label' ? nodes.get(item.nodeId) : null;
      const pipe = kind === 'label' ? edges.get(item.edgeId) : null;
      const detail = kind === 'node' ? `${names.get(item.type) || item.type} · ${item.type}${item.mount ? ' · 挂接管路：' + item.mount.edgeId : ''}` : parent ? `附着设备：${parent.title || parent.id}`
        : pipe ? `附着管路：${pipe.id}` : kind === 'label' ? '独立文字' : type;
      result.push({ kind, id: item.id, type, title, detail,
        search: normalized([type, title, item.id, detail, parent?.id,
          kind === 'edge' ? edgeSearch(item) : '', pipe ? edgeSearch(pipe) : ''].filter(Boolean).join(' ')) });
    }
  }
  return result;
}

export function filterObjects(entries, query = '', kind = '') {
  const words = normalized(query).trim().split(/\s+/).filter(Boolean);
  return entries.filter(entry => (!kind || entry.kind === kind) && words.every(word => entry.search.includes(word)));
}
