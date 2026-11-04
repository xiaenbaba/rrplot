/* Resolve the same group boundaries as copy/paste; never change graph or layout. */
export function styleTargets(document, selection, scope = 'selection') {
  if (!['selection', 'all'].includes(scope)) throw new Error('请选择当前选择或整张图纸。');
  if (scope === 'all') return {
    edges: document.edges.map(e => e.id), labels: document.labels.map(l => l.id)
  };
  const ids = kind => new Set(selection.filter(ref => ref.kind === kind).map(ref => ref.id));
  const nodes = ids('node'), junctions = ids('junction'), edges = ids('edge'), labels = ids('label');
  const inside = ref => ref.nodeId ? nodes.has(ref.nodeId) : junctions.has(ref.junctionId);
  const pipes = document.edges.filter(e => edges.has(e.id) || (inside(e.source) && inside(e.target)));
  const pipeIds = new Set(pipes.map(e => e.id));
  return { edges: pipes.map(e => e.id), labels: document.labels.filter(l => labels.has(l.id)
    || nodes.has(l.nodeId) || pipeIds.has(l.edgeId)).map(l => l.id) };
}

export function applyStyles(document, selection, scope, patch) {
  const number = (v, low, high) => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
  const color = v => typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v);
  const rules = {
    edges: { color, width: v => number(v, .2, 8), linestyle: v => ['solid', 'dashed'].includes(v),
      head: v => typeof v === 'boolean' },
    labels: { color, size: v => number(v, 6, 72), ha: v => ['left', 'center', 'right'].includes(v),
      boxed: v => typeof v === 'boolean' }
  };
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('批量样式设置无效。');
  for (const [group, values] of Object.entries(patch)) {
    if (!Object.hasOwn(rules, group) || !values || typeof values !== 'object' || Array.isArray(values))
      throw new Error('批量样式设置无效。');
    for (const [key, value] of Object.entries(values)) {
      if (!Object.hasOwn(rules[group], key) || !rules[group][key](value))
        throw new Error('样式值无效：线宽为 0.2～8，字号为 6～72，颜色使用六位十六进制。');
    }
  }
  const targets = styleTargets(document, selection, scope), result = structuredClone(document);
  for (const group of ['edges', 'labels']) {
    const ids = new Set(targets[group]);
    for (const item of result[group]) if (ids.has(item.id)) Object.assign(item, patch[group]);
  }
  return result;
}
