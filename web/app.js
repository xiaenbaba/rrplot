import { rotate, endpoint, route, along, nearestSegment, splitRoute, translateDocument, layoutPage, editableSegments, moveSegment, transformedBox, selectInBox, projectOnRoute } from './geometry.js';
import { copySelection, captureSelection, pasteFragment, deleteSelection, translateSelection, editSelectedEdges, splitEdgeLabels, reconnectEdge, nudgeSelection } from './document.js';
import { inspectDiagram } from './checks.js';
import { objectIndex, filterObjects } from './objects.js';
import { styleTargets, applyStyles } from './styles.js';

const $ = id => document.getElementById(id);
const svg = $('diagram');
const NS = 'http://www.w3.org/2000/svg';
const clone = value => structuredClone(value);
const uid = prefix => prefix + '-' + crypto.randomUUID().slice(0, 8);
const DRAFT = 'rrplot-web-v1-draft';
let doc = null, catalog = [], geometries = new Map(), fontFamily = 'Times New Roman, SimSun, serif';
let selection = null, multiSelection = [], mode = 'select', placement = null, ports = [], pendingPort = null;
let previewTarget = null;
let reconnect = null;
let edgeLabelsSupported = false;
let undo = [], redo = [], drag = null, dirty = false, spaceDown = false;
let nudge = null;
let editorClipboard = null, clipboardPastes = 0;
let pageMargin = 40, pageLayoutBusy = false;
let styleSession = null;
let saving = false, pendingDownload = null;
let revision = 0, request = 0, previewUrl = null, messageTimer = null;
let view = { x: -40, y: -30, w: 840, h: 640 };

function html(tag, text, className) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
}

function shape(tag, attrs = {}, parent = svg) {
  const e = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([k, v]) => { if (v !== undefined) e.setAttribute(k, v); });
  parent.append(e);
  return e;
}

function status(text) { $('status').textContent = text; }
function message(text) {
  clearTimeout(messageTimer);
  $('message').textContent = text;
  $('message').hidden = !text;
  if (text) messageTimer = setTimeout(() => { $('message').hidden = true; }, 7000);
}

async function api(path, body) {
  if (body?.document?.labels?.some(label => label.edgeId) && !edgeLabelsSupported)
    throw new Error('管路状态点需要新版服务，请保存当前图纸后重启 start-web.cmd，再刷新页面。');
  const response = await fetch('/api/' + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `请求失败 (${response.status})`);
  }
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : response.blob();
}

function currentNodes() {
  return doc.nodes.map(n => ({ ...n, geometry: geometries.get(n.id) })).filter(n => n.geometry);
}
function findSelected() {
  if (!selection) return null;
  return doc[{ node: 'nodes', edge: 'edges', label: 'labels', junction: 'junctions' }[selection.kind]]
    ?.find(item => item.id === selection.id);
}
function selected(kind, id) {
  return multiSelection.some(item => item.kind === kind && item.id === id);
}
function setSelection(kind, id, additive = false) {
  const key = item => item.kind + ':' + item.id;
  const item = { kind, id };
  if (additive && ['node', 'label', 'junction', 'edge'].includes(kind)) {
    const index = multiSelection.findIndex(existing => key(existing) === key(item));
    if (index >= 0) multiSelection.splice(index, 1);
    else multiSelection.push(item);
    selection = multiSelection.at(-1) || null;
  } else {
    multiSelection = [item];
    selection = item;
  }
}
function clearSelection() { selection = null; multiSelection = []; }
function refName(ref) {
  if (ref.junctionId) return '三通 · ' + ref.junctionId.slice(-5);
  const n = doc.nodes.find(n => n.id === ref.nodeId);
  return (n?.title || ref.nodeId) + ' · ' + ref.portId;
}
function eqRef(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
function snapped(v) { return +($('snap').checked ? Math.round(v / 10) * 10 : v).toFixed(2); }
function world(event) {
  const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
  const p = point.matrixTransform(svg.getScreenCTM().inverse());
  return [p.x, p.y];
}
function labelPosition(label) {
  if (label.edgeId) {
    const edge = doc.edges.find(e => e.id === label.edgeId);
    return along(edgePoints(edge), label.at).point.map((v, i) => v + [label.x, label.y][i]);
  }
  if (!label.nodeId) return [label.x, label.y];
  const n = doc.nodes.find(n => n.id === label.nodeId);
  const p = rotate([label.x, label.y], n.rotation);
  return [n.x + p[0], n.y + p[1]];
}
function attachLabelToEdge(label, edgeId) {
  const p = labelPosition(label);
  delete label.edgeId; delete label.at;
  if (edgeId) {
    const projected = projectOnRoute(edgePoints(doc.edges.find(e => e.id === edgeId)), p);
    label.edgeId = edgeId; label.at = projected.at;
    [label.x, label.y] = p.map((v, i) => v - projected.point[i]);
  } else [label.x, label.y] = p;
}
function addStateLabel(edge) {
  if (!edgeLabelsSupported) return message('管路状态点需要新版服务，请保存图纸后重启 start-web.cmd，再刷新页面。');
  if (doc.labels.length >= 2000) return message('标签数量已达上限，请先删除部分标签。');
  const used = new Set(doc.labels.map(l => l.text));
  let number = 1; while (used.has(String(number))) number++;
  edit(() => {
    const id = uid('label');
    doc.labels.push({ id, edgeId: edge.id, at: .5, x: 0, y: -16, text: String(number),
      size: 12, ha: 'center', boxed: true, color: '#111111' });
    setSelection('label', id);
  });
}
function selectionCandidates() {
  const candidates = currentNodes().map(n => ({ kind: 'node', id: n.id,
    box: transformedBox(n.geometry.box, [n.x, n.y], n.rotation) }));
  for (const edge of doc.edges) {
    try {
      const points = edgePoints(edge), xs = points.map(p => p[0]), ys = points.map(p => p[1]);
      candidates.push({ kind: 'edge', id: edge.id, box: [Math.min(...xs), Math.min(...ys),
        Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)] });
    } catch { /* Geometry for a newly placed endpoint may still be loading. */ }
  }
  for (const j of doc.junctions) candidates.push({ kind: 'junction', id: j.id, box: [j.x - 4, j.y - 4, 8, 8] });
  for (const element of svg.querySelectorAll('.diagram-label')) {
    const b = element.querySelector('text').getBBox();
    candidates.push({ kind: 'label', id: element.dataset.id, box: [b.x, b.y, b.width, b.height] });
  }
  return candidates;
}
function edgePoints(edge) {
  const nodes = currentNodes();
  return route(endpoint(edge.source, nodes, doc.junctions), endpoint(edge.target, nodes, doc.junctions), edge.vertices);
}

function connectionTarget(event, point) {
  const hit = event.target.closest('[data-kind="port"], [data-kind="junction"]');
  if (hit?.dataset.kind === 'port') return endpoint(JSON.parse(hit.dataset.ref), currentNodes(), doc.junctions);
  if (hit?.dataset.kind === 'junction') return endpoint({ junctionId: hit.dataset.id }, currentNodes(), doc.junctions);
  return { point, direction: [0, 0] };
}

function saveDraft() {
  try { localStorage.setItem(DRAFT, JSON.stringify({ time: Date.now(), document: doc })); }
  catch { message('浏览器草稿空间不可用，请使用“保存 JSON”保存图纸。'); }
}

async function refresh() {
  const token = ++request, version = revision;
  status('正在更新图纸…');
  try {
    const result = await api('resolve', { document: doc });
    if (token !== request || version !== revision) return;
    geometries = new Map(result.nodes.map(n => [n.id, n.geometry]));
    fontFamily = result.fontFamily;
    if (dirty) saveDraft();
    // Keep input focus and the editor-owned objects while geometry arrives.
    // Replacing inspector fields here can discard a value being typed.
    renderCanvas();
    status('已更新 · 本机草稿自动保存');
  } catch (error) {
    if (token === request) { message(error.message); status('图纸需要调整，或本机服务未连接'); }
  }
}

function finishEdit(before, { merge = false, deferRefresh = false } = {}) {
  if (JSON.stringify(before) === JSON.stringify(doc)) return render();
  if (!merge || !undo.length) { undo.push(before); if (undo.length > 80) undo.shift(); }
  redo = [];
  dirty = true; revision++; saveDraft(); render();
  if (!deferRefresh) void refresh();
}
function edit(fn) {
  if (!doc) return;
  const before = clone(doc); fn(); finishEdit(before);
}

function clearDraft() {
  try { localStorage.removeItem(DRAFT); } catch { /* Storage may be unavailable. */ }
  $('draft-banner').hidden = true;
}

async function replaceDocument(next, preserveDraft = false) {
  const token = ++request, version = revision;
  const result = await api('resolve', { document: next });
  edgeLabelsSupported = result.features?.includes('edgeLabels') || false;
  if (token !== request || version !== revision) return;
  ++revision;
  doc = result.document; geometries = new Map(result.nodes.map(n => [n.id, n.geometry]));
  fontFamily = result.fontFamily; undo = []; redo = []; clearSelection(); ports = [];
  pendingPort = null; previewTarget = null; reconnect = null; mode = 'select'; placement = null; dirty = false;
  clipboardPastes = 0;
  $('object-search').value = ''; $('object-kind').value = '';
  if (!preserveDraft) clearDraft();
  render(); fit(); status('图纸已打开 · 点击对象编辑'); message('');
}

async function confirmReplace() {
  if (!dirty) return true;
  const dialog = $('replace-dialog');
  dialog.returnValue = 'cancel';
  const answer = new Promise(resolve => dialog.addEventListener('close',
    () => resolve(dialog.returnValue === 'replace'), { once: true }));
  dialog.showModal();
  return answer;
}

function updateView() {
  svg.setAttribute('viewBox', `${view.x} ${view.y} ${view.w} ${view.h}`);
  $('zoom').textContent = Math.round((svg.clientWidth / view.w) * 100) + '%';
}
function fit() {
  if (!doc) return;
  const ratio = svg.clientWidth / svg.clientHeight;
  const width = doc.page.width + 80, height = doc.page.height + 80;
  view.w = Math.max(width, height * ratio); view.h = view.w / ratio;
  view.x = (doc.page.width - view.w) / 2; view.y = (doc.page.height - view.h) / 2;
  updateView();
}
function zoom(factor, at) {
  const center = at || [view.x + view.w / 2, view.y + view.h / 2];
  const w = Math.max(100, Math.min(10000, view.w * factor)), k = w / view.w;
  view = { x: center[0] + (view.x - center[0]) * k, y: center[1] + (view.y - center[1]) * k, w, h: view.h * k };
  updateView();
}

function renderCanvas() {
  if (!doc) return;
  svg.replaceChildren();
  svg.classList.toggle('connecting', mode === 'connect' || mode === 'reconnect');
  svg.classList.toggle('moving-all', mode === 'move-all');
  svg.classList.toggle('box-selecting', mode === 'box-select' || drag?.kind === 'box');
  svg.classList.toggle('placing', !!placement || ['junction', 'text'].includes(mode));
  const defs = shape('defs');
  const pattern = shape('pattern', { id: 'grid-pattern', width: 10, height: 10, patternUnits: 'userSpaceOnUse' }, defs);
  shape('path', { d: 'M 10 0 L 0 0 0 10', fill: 'none', stroke: '#c6d6d1', 'stroke-width': .65 }, pattern);
  shape('rect', { x: 0, y: 0, width: doc.page.width, height: doc.page.height, fill: '#fff', class: 'page' });
  if ($('grid').checked) shape('rect', { width: doc.page.width, height: doc.page.height, fill: 'url(#grid-pattern)', opacity: .65, 'pointer-events': 'none' });
  const nodes = currentNodes();
  for (const edge of doc.edges) {
    let points;
    try { points = edgePoints(edge); } catch { continue; }
    const g = shape('g', { class: 'edge' + (selected('edge', edge.id) ? ' selected' : '')
      + (reconnect?.edgeId === edge.id ? ' reconnecting-edge' : ''), 'data-kind': 'edge', 'data-id': edge.id });
    const p = points.map(p => p.join(',')).join(' ');
    shape('polyline', { points: p, class: 'edge-hit' }, g);
    shape('polyline', { points: p, class: 'edge-visible', fill: 'none', stroke: edge.color,
      'stroke-width': edge.width * 100 / 72, 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      'stroke-dasharray': edge.linestyle === 'dashed' ? '7 5' : undefined }, g);
    if (edge.head) for (const at of edge.headAt || [.55]) {
      const info = along(points, at); if (info.length < 1) continue;
      const half = Math.min(20, info.length / 2), direction = info.direction;
      const center = info.point.map((v, i) => Math.max(Math.min(info.start[i], info.end[i]) + (direction[i] ? half : 0), Math.min(Math.max(info.start[i], info.end[i]) - (direction[i] ? half : 0), v)));
      const tip = center.map((v, i) => v + direction[i] * (half - 2));
      const base = tip.map((v, i) => v - direction[i] * 7);
      shape('polygon', { points: [tip, [base[0] - direction[1] * 2.7, base[1] + direction[0] * 2.7],
        [base[0] + direction[1] * 2.7, base[1] - direction[0] * 2.7]].map(p => p.join(',')).join(' '), fill: edge.color, 'pointer-events': 'none' }, g);
    }
  }
  if (mode === 'connect' && pendingPort && previewTarget) {
    try {
      const start = endpoint(pendingPort, nodes, doc.junctions);
      const points = route(start, previewTarget, []);
      shape('polyline', { points: points.map(p => p.join(',')).join(' '), class: 'connection-preview' });
    } catch { /* The source may have been removed while connecting. */ }
  }
  if (mode === 'reconnect' && reconnect && previewTarget) {
    try {
      const edge = doc.edges.find(e => e.id === reconnect.edgeId);
      const source = reconnect.side === 'source' ? previewTarget : endpoint(edge.source, nodes, doc.junctions);
      const target = reconnect.side === 'target' ? previewTarget : endpoint(edge.target, nodes, doc.junctions);
      const points = route(source, target, edge.vertices);
      shape('polyline', { points: points.map(p => p.join(',')).join(' '), class: 'connection-preview' });
    } catch { /* Geometry may still be loading. */ }
  }
  for (const n of nodes) {
    const g = shape('g', { class: 'node' + (selected('node', n.id) ? ' selected' : ''),
      'data-kind': 'node', 'data-id': n.id, transform: `translate(${n.x} ${n.y}) rotate(${n.rotation})` });
    const [x, y, w, h] = n.geometry.box;
    shape('title', {}, g).textContent = n.title;
    shape('image', { x, y, width: w, height: h, href: n.geometry.image, class: 'node-image' }, g);
    shape('rect', { x: x - 3, y: y - 3, width: w + 6, height: h + 6, rx: 2, class: 'node-hit' }, g);
    const seen = new Set();
    for (const [id, p] of Object.entries(n.geometry.ports)) {
      const key = p.point.join(','); if (seen.has(key)) continue; seen.add(key);
      const ref = { nodeId: n.id, portId: id };
      const chosen = ports.some(p => eqRef(p, ref)) || eqRef(pendingPort, ref);
      shape('circle', { cx: p.point[0], cy: p.point[1], r: 10,
        class: 'port-hit', 'data-kind': 'port', 'data-ref': JSON.stringify(ref) }, g);
      const circle = shape('circle', { cx: p.point[0], cy: p.point[1], r: 4.5,
        class: 'port' + (chosen ? ' chosen' : ''), 'data-kind': 'port', 'data-ref': JSON.stringify(ref) }, g);
      shape('title', {}, circle).textContent = id;
    }
  }
  for (const j of doc.junctions) {
    const g = shape('g', { class: 'junction' + (selected('junction', j.id) ? ' selected' : ''),
      'data-kind': 'junction', 'data-id': j.id });
    shape('circle', { cx: j.x, cy: j.y, r: 10, class: 'junction-hit' }, g);
    const c = shape('circle', { cx: j.x, cy: j.y, r: 4, class: 'junction-dot', 'pointer-events': 'none' }, g);
    shape('title', {}, c).textContent = '三通';
  }
  for (const label of doc.labels) {
    const [x, y] = labelPosition(label);
    const g = shape('g', { class: 'diagram-label' + (selected('label', label.id) ? ' selected' : ''),
      'data-kind': 'label', 'data-id': label.id });
    const text = shape('text', { x, y, fill: label.color, 'font-family': fontFamily,
      'font-size': label.size * 100 / 72, 'text-anchor': { left: 'start', center: 'middle', right: 'end' }[label.ha],
      'dominant-baseline': 'central' }, g);
    const lines = label.text.split('\n');
    lines.forEach((line, i) => shape('tspan', { x, dy: i ? '1.2em' : `${-(lines.length - 1) * .6}em` }, text).textContent = line);
    if (label.boxed || selected('label', label.id)) {
      const b = text.getBBox();
      const bg = shape('rect', { x: b.x - 2, y: b.y - 2, width: b.width + 4, height: b.height + 4,
        fill: label.boxed ? '#fff' : '#d6eee4', opacity: label.boxed ? 1 : .55 }, g);
      g.insertBefore(bg, text);
    }
  }
  renderVertices();
  if (drag?.kind === 'box' && drag.moved) {
    const [x, y] = drag.start, [ex, ey] = drag.point;
    shape('rect', { x: Math.min(x, ex), y: Math.min(y, ey), width: Math.abs(ex - x),
      height: Math.abs(ey - y), class: 'selection-marquee' });
  }
  updateView();
}

function renderVertices() {
  svg.querySelectorAll('[data-kind="vertex"], [data-kind="segment"]').forEach(element => element.remove());
  if (mode === 'reconnect' || multiSelection.length > 1) return;
  const e = selection?.kind === 'edge' && findSelected();
  if (e && mode === 'select') {
    const nodes = currentNodes();
    const source = endpoint(e.source, nodes, doc.junctions), target = endpoint(e.target, nodes, doc.junctions);
    for (const { index, axis, point: [x, y] } of editableSegments(source, target, e.vertices)) {
      const handle = shape('rect', { x: x - (axis ? 9 : 4), y: y - (axis ? 4 : 9),
        width: axis ? 18 : 8, height: axis ? 8 : 18, rx: 3,
        class: 'segment-handle ' + (axis ? 'horizontal' : 'vertical'),
        'data-kind': 'segment', 'data-id': e.id, 'data-index': index });
      shape('title', {}, handle).textContent = axis ? '上下拖动水平线段' : '左右拖动垂直线段';
    }
  }
  if (e) e.vertices.forEach((v, i) => {
    const c = shape('rect', { x: v[0] - 4, y: v[1] - 4, width: 8, height: 8,
      class: 'vertex', 'data-kind': 'vertex', 'data-id': e.id, 'data-index': i });
    shape('title', {}, c).textContent = '拖动折点；Alt+点击删除';
  });
}

function field(parent, caption, value, setter, options = {}) {
  const wrap = html('label', undefined, 'field'); wrap.append(html('span', caption));
  const input = html(options.multiline ? 'textarea' : options.options ? 'select' : 'input');
  input.setAttribute('aria-label', caption);
  if (options.options) options.options.forEach(v => {
    const o = html('option', typeof v === 'object' ? v.label : String(v)); o.value = typeof v === 'object' ? v.value : v; input.append(o);
  });
  else if (!options.multiline) input.type = options.type || (typeof value === 'number' ? 'number' : 'text');
  if (options.min !== undefined) input.min = options.min;
  if (options.max !== undefined) input.max = options.max;
  if (options.required) input.required = true;
  input.disabled = !!options.disabled;
  if (input.type === 'number') input.step = options.step || 'any';
  if (input.type === 'checkbox') input.checked = value; else input.value = value;
  let committed = value;
  function commit() {
    if (!input.checkValidity()) { input.reportValidity(); return; }
    const next = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
    if (next === committed) return;
    committed = next;
    if (options.transient) setter(next); else edit(() => setter(next));
  }
  input.addEventListener('change', commit);
  input.addEventListener('blur', commit);
  wrap.append(input); parent.append(wrap); return input;
}
function inspectorButton(parent, caption, action) {
  const b = html('button', caption); b.addEventListener('click', action); parent.append(b); return b;
}
function renderInspector() {
  renderHint();
  renderObjectList();
  const root = $('inspector'); root.replaceChildren();
  if (mode === 'reconnect' && reconnect) {
    $('selection-kind').textContent = 'RECONNECT';
    root.append(html('h2', reconnect.side === 'source' ? '重新连接起点' : '重新连接终点', 'object-heading'));
    const edge = doc.edges.find(e => e.id === reconnect.edgeId);
    root.append(html('p', '当前端点：' + refName(edge[reconnect.side]), 'muted'));
    root.append(html('p', '点击新的设备端口或三通。靠近时吸附并预览走线，折点、样式和状态点保留。', 'muted'));
    inspectorButton(root, '取消重接（Esc）', cancelReconnect);
    return;
  }
  if (mode === 'move-all') {
    $('selection-kind').textContent = 'ALL';
    root.append(html('h2', '整体移动', 'object-heading'));
    root.append(html('p', '在画布中按住左键拖动，整体移动全部设备、三通、管路折点和文字。页面位置保持不变，附着标签随设备移动。', 'muted'));
    root.append(html('p', '每次拖动可用 Ctrl+Z 撤销；拖动中按 Esc 取消本次移动，松开后按 Esc 退出。', 'muted'));
    return;
  }
  if (multiSelection.length > 1) {
    $('selection-kind').textContent = 'MULTI';
    root.append(html('h2', `已选择 ${multiSelection.length} 项`, 'object-heading'));
    const movable = layoutRefs().length, pipes = multiSelection.filter(ref => ref.kind === 'edge').length;
    root.append(html('p', `设备、三通和文字 ${movable} 项 · 管路 ${pipes} 条。按住 Shift 点击可添加或取消选择，Shift+拖动空白可追加框选。`, 'muted'));
    root.append(html('p', '可批量修改样式或删除。拖动已选设备、三通或文字可一起移动；管路随端点移动，单选管路后可编辑走线。', 'muted'));
    root.append(html('p', movable ? 'Ctrl+C 复制设备、三通和文字，Ctrl+D 生成副本，均包含设备标签和组内管路。单独选中的管路不复制，请同时选择其两端设备或三通。'
      : '复制管路时，请同时选择两端设备或三通，再使用 Ctrl+C 或 Ctrl+D。', 'muted'));
    const layout = html('div', undefined, 'layout-grid');
    for (const [action, caption] of [
      ['align-left', '左对齐'], ['align-center-x', '水平居中'], ['align-right', '右对齐'],
      ['align-top', '上对齐'], ['align-center-y', '垂直居中'], ['align-bottom', '下对齐'],
      ['distribute-x', '水平等距'], ['distribute-y', '垂直等距'],
    ]) {
      const button = inspectorButton(layout, caption, () => batchLayout(action));
      button.disabled = movable < (action.startsWith('distribute') ? 3 : 2);
    }
    if (movable) root.append(html('div', '批量布局（设备、三通和文字）', 'section-label'), layout);
    if (pipes) renderPipeActions(root, pipes);
    inspectorButton(root, '批量样式', showBatchStyles);
    inspectorButton(root, '清除多选', () => { clearSelection(); render(); });
    return;
  }
  const item = findSelected();
  $('selection-kind').textContent = selection?.kind?.toUpperCase() || 'PAGE';
  if (!item) {
    root.append(html('h2', '页面设置', 'object-heading'));
    field(root, '图纸名称', doc.title, v => { doc.title = v; });
    const pair = html('div', undefined, 'field-pair'); root.append(pair);
    field(pair, '页面宽度', doc.page.width, v => { doc.page.width = v; }, { min: 100, max: 4000 });
    field(pair, '页面高度', doc.page.height, v => { doc.page.height = v; }, { min: 100, max: 4000 });
    root.append(html('div', '页面排版', 'section-label'));
    const margin = field(root, '适配留白（单位）', pageMargin, v => { pageMargin = v; },
      { min: 10, max: 500, required: true, transient: true, disabled: pageLayoutBusy });
    margin.id = 'page-margin';
    const layout = html('div', undefined, 'button-row'); root.append(layout);
    const empty = !['nodes', 'edges', 'junctions', 'labels'].some(name => doc[name].length);
    for (const [action, title] of [['center', '内容居中'], ['fit', '页面适配内容']]) {
      const button = inspectorButton(layout, title, () => applyPageLayout(action));
      button.dataset.pageLayout = action; button.disabled = empty || pageLayoutBusy;
    }
    root.append(html('p', '作用于整张图纸，包含文字和管路。保持图元大小与连接；适配会调整纸张尺寸，每次排版可一次撤销。“适应页面”只调整视图。', 'muted'));
    root.append(html('p', mode === 'box-select' ? '拖出矩形，完整框住设备、管路、三通或文字。松开后可批量修改样式或删除，拖动设备、三通和文字可移动；按住 Shift 可追加选择。'
      : '选择设备、标签或管路查看属性；使用“框选”或 Shift+拖动空白可多选。坐标单位与 rrplot 画布一致。', 'muted')); return;
  }
  const kind = selection.kind;
  root.append(html('h2', kind === 'node' ? item.title : { edge: '管路', label: '文字标签', junction: '分流三通' }[kind], 'object-heading'));
  if (kind === 'node') {
    field(root, '设备名称', item.title, v => {
      const l = doc.labels.find(l => l.nodeId === item.id && l.text === item.title);
      if (l) l.text = v; item.title = v;
    });
    coordinateFields(root, item);
    field(root, '旋转角度', item.rotation, v => { item.rotation = Number(v); }, { options: [0, 90, 180, 270] });
    root.append(html('div', '图元参数', 'section-label'));
    const entry = catalog.find(c => c.type === item.type);
    for (const [key, f] of Object.entries(entry.fields)) field(root, f.label, item.params[key], v => { item.params[key] = v; }, f);
    if (item.type === 'four_way_valve') root.append(html('p', 'D / exhaust：排气；S / suction：回气；C / condenser、E / evaporator：两侧换热器。端口随旋转移动，图元只表示接管关系。', 'muted'));
    if (item.type === 'check_valve') root.append(html('p', '三角尖端指向 out；改变流通方向会交换 in/out 的位置，已有管路继续按端口 ID 跟随。', 'muted'));
    inspectorButton(root, '添加设备标签', () => edit(() => {
      const id = uid('label'); doc.labels.push({ id, nodeId: item.id, x: 0, y: 70, text: item.title, size: 15, ha: 'center', boxed: true, color: '#111111' }); setSelection('label', id);
    }));
  } else if (kind === 'label') {
    field(root, '标签内容', item.text, v => { item.text = v; }, { multiline: true });
    if (!item.nodeId) {
      field(root, '附着管路', item.edgeId || '', v => attachLabelToEdge(item, v), {
        options: [{ value: '', label: '独立文字' }, ...doc.edges.map(e => ({ value: e.id,
          label: refName(e.source) + ' → ' + refName(e.target) }))], disabled: !edgeLabelsSupported });
      if (!edgeLabelsSupported) root.append(html('p', '使用管路状态点前，请重启 start-web.cmd 并刷新页面。', 'muted'));
    }
    if (item.edgeId) field(root, '沿管路位置（%）', item.at * 100, v => { item.at = v / 100; }, { min: 0, max: 100 });
    coordinateFields(root, item, item.nodeId || item.edgeId ? '相对偏移' : '');
    field(root, '字号（pt）', item.size, v => { item.size = v; }, { min: 6, max: 72 });
    field(root, '文字对齐', item.ha, v => { item.ha = v; }, { options: ['left', 'center', 'right'] });
    field(root, '文字颜色', item.color, v => { item.color = v; }, { type: 'color' });
    field(root, '白色背景', item.boxed, v => { item.boxed = v; }, { type: 'checkbox' });
    if (item.nodeId) inspectorButton(root, '解除设备附着', () => edit(() => {
      const p = labelPosition(item); delete item.nodeId; [item.x, item.y] = p;
    }));
  } else if (kind === 'junction') {
    coordinateFields(root, item);
    inspectorButton(root, '删除三通并恢复管路', () => removeSelected());
  }
  else if (kind === 'edge') {
    root.append(html('p', refName(item.source) + ' → ' + refName(item.target), 'muted'));
    field(root, '线宽（pt）', item.width, v => { item.width = v; }, { min: .2, max: 8 });
    field(root, '管路颜色', item.color, v => { item.color = v; }, { type: 'color' });
    field(root, '线型', item.linestyle, v => { item.linestyle = v; }, { options: ['solid', 'dashed'] });
    field(root, '显示流向箭头', item.head, v => { item.head = v; }, { type: 'checkbox' });
    root.append(html('p', `${item.vertices.length} 个手动顶点。拖动线段中间的长条手柄调整走线；双击管线添加折点，Alt+点击方形折点删除。`, 'muted'));
    renderPipeActions(root, 1);
    inspectorButton(root, '在管路中间插入三通', () => splitEdge(item));
    inspectorButton(root, '添加状态点', () => addStateLabel(item));
    const endpoints = html('div', undefined, 'button-row reconnect-buttons'); root.append(endpoints);
    inspectorButton(endpoints, '重接起点', () => beginReconnect(item, 'source'));
    inspectorButton(endpoints, '重接终点', () => beginReconnect(item, 'target'));
  }
}
function pipeActionsBusy() {
  return mode !== 'select' || placement || pendingPort || reconnect || drag || spaceDown || pageLayoutBusy;
}
function renderPipeActions(root, count) {
  root.append(html('div', `管路操作（已选 ${count} 条）`, 'section-label'));
  const buttons = html('div', undefined, 'button-row'); root.append(buttons);
  for (const [action, caption] of [['reverse', '反转流向'], ['clear-vertices', '清除折点']]) {
    const button = inspectorButton(buttons, caption, () => operateSelectedPipes(action));
    button.dataset.pipeAction = action;
    button.disabled = !!pipeActionsBusy() || (action === 'clear-vertices'
      && !doc.edges.some(edge => selected('edge', edge.id) && edge.vertices.length));
  }
  root.append(html('p', '仅处理直接选中的管路。反转保留走线及状态点位置；清除折点恢复自动走线，状态点沿新路径跟随。每次操作可一次撤销。', 'muted'));
}
function operateSelectedPipes(action) {
  if (!doc || pipeActionsBusy() || document.querySelector('dialog[open]')) return;
  const edges = doc.edges.filter(edge => selected('edge', edge.id));
  if (!edges.length) return;
  try {
    const routes = new Map(action === 'reverse' ? edges.map(edge => [edge.id, edgePoints(edge)]) : []);
    const next = editSelectedEdges(doc, multiSelection, action, routes);
    const changed = edges.filter(edge => JSON.stringify(edge) !== JSON.stringify(next.edges.find(e => e.id === edge.id))).length;
    if (!changed) return status('所选管路无需修改');
    edit(() => { doc = next; });
    status(`${action === 'reverse' ? '已反转流向' : '已清除折点'} · ${changed} 条管路 · Ctrl+Z 撤销`);
  } catch (error) { message(error.message); }
}
function coordinateFields(parent, item, prefix = '') {
  const pair = html('div', undefined, 'field-pair'); parent.append(pair);
  for (const axis of ['x', 'y']) field(pair, `${prefix}${axis.toUpperCase()}`, item[axis], v => { item[axis] = v; }, { min: -100000, max: 100000 });
}

function layoutRefs() {
  return multiSelection.filter(ref => ['node', 'junction', 'label'].includes(ref.kind))
    .map(ref => ({ ref, item: doc[{ node: 'nodes', junction: 'junctions', label: 'labels' }[ref.kind]]
      .find(item => item.id === ref.id) })).filter(entry => entry.item);
}
function layoutBox(entry) {
  const { ref, item } = entry;
  if (ref.kind === 'node') {
    const geometry = geometries.get(item.id), rotated = item.rotation % 180 !== 0;
    const width = rotated ? geometry.height : geometry.width, height = rotated ? geometry.width : geometry.height;
    return { x: item.x, y: item.y, left: item.x - width / 2, right: item.x + width / 2,
      top: item.y - height / 2, bottom: item.y + height / 2, width, height };
  }
  const [x, y] = ref.kind === 'label' ? labelPosition(item) : [item.x, item.y];
  return { x, y, left: x, right: x, top: y, bottom: y, width: 0, height: 0 };
}
function moveLayoutRef(entry, x, y) {
  const { ref, item } = entry;
  if (ref.kind === 'node' || ref.kind === 'junction') { item.x = +x.toFixed(4); item.y = +y.toFixed(4); return; }
  if (item.nodeId) {
    const node = doc.nodes.find(candidate => candidate.id === item.nodeId);
    const local = rotate([x - node.x, y - node.y], -node.rotation);
    item.x = +local[0].toFixed(4); item.y = +local[1].toFixed(4);
  } else if (item.edgeId) {
    const anchor = along(edgePoints(doc.edges.find(e => e.id === item.edgeId)), item.at).point;
    item.x = +(x - anchor[0]).toFixed(4); item.y = +(y - anchor[1]).toFixed(4);
  } else { item.x = +x.toFixed(4); item.y = +y.toFixed(4); }
}
function batchLayout(action) {
  const entries = layoutRefs();
  if (entries.length < 2) return message('请至少多选两个设备、三通或文字。');
  const boxes = entries.map(layoutBox), before = clone(doc);
  const minLeft = Math.min(...boxes.map(box => box.left)), maxRight = Math.max(...boxes.map(box => box.right));
  const minTop = Math.min(...boxes.map(box => box.top)), maxBottom = Math.max(...boxes.map(box => box.bottom));
  if (action === 'distribute-x' || action === 'distribute-y') {
    if (entries.length < 3) return message('均匀分布至少需要三个对象。');
    const axis = action === 'distribute-x' ? 'x' : 'y';
    const order = entries.map((entry, index) => ({ entry, box: boxes[index] })).sort((a, b) => a.box[axis] - b.box[axis]);
    const first = order[0].box[axis], step = (order.at(-1).box[axis] - first) / (order.length - 1);
    order.forEach(({ entry, box }, index) => moveLayoutRef(entry, axis === 'x' ? first + step * index : box.x,
      axis === 'y' ? first + step * index : box.y));
  } else {
    const target = { 'align-left': minLeft, 'align-center-x': (minLeft + maxRight) / 2, 'align-right': maxRight,
      'align-top': minTop, 'align-center-y': (minTop + maxBottom) / 2, 'align-bottom': maxBottom }[action];
    entries.forEach((entry, index) => {
      const box = boxes[index];
      const x = action === 'align-left' ? target + box.width / 2 : action === 'align-right' ? target - box.width / 2
        : action === 'align-center-x' ? target : box.x;
      const y = action === 'align-top' ? target + box.height / 2 : action === 'align-bottom' ? target - box.height / 2
        : action === 'align-center-y' ? target : box.y;
      moveLayoutRef(entry, x, y);
    });
  }
  finishEdit(before);
}

function renderHint() {
  document.querySelector('.canvas-hint').textContent = mode === 'move-all'
    ? '拖动任意位置整体移动全部内容 · Ctrl+Z 撤销 · Esc 退出'
    : mode === 'box-select' ? '拖出矩形完整框住对象 · Shift 追加选择 · Esc 取消'
    : mode === 'reconnect' ? '点击设备端口或三通完成重接 · 空格拖动平移 · Esc 取消'
    : mode === 'select' && !placement && multiSelection.some(ref => ['node', 'junction', 'label'].includes(ref.kind)) ? '方向键微调 1 单位 · Shift+方向键 10 单位 · Ctrl+Z 撤销'
    : mode === 'select' && multiSelection.some(ref => ref.kind === 'edge') ? 'Shift+点击追加管路 · 批量样式统一外观 · 单选管路调整走线'
    : '滚轮缩放 · 空白拖动平移 · Shift+空白拖动框选 · 双击管线加折点';
}
function render() {
  if (!doc) return;
  $('title').value = doc.title;
  renderSaveState();
  $('undo').disabled = !undo.length; $('redo').disabled = !redo.length;
  const clipboardBusy = mode !== 'select' || placement || pendingPort || reconnect || drag;
  $('clipboard-copy').disabled = !!clipboardBusy || !multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind));
  document.querySelector('[data-action="copy"]').disabled = !!clipboardBusy
    || !multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind));
  $('clipboard-paste').disabled = !!clipboardBusy || !editorClipboard;
  updateStyleButton();
  $('counts').textContent = `${doc.nodes.length} 个设备 · ${doc.edges.length} 条管路`;
  document.querySelectorAll('[data-tool]').forEach(b => {
    const active = b.dataset.tool === mode && !placement;
    b.classList.toggle('active', active); b.setAttribute('aria-pressed', active);
  });
  document.querySelectorAll('[data-part]').forEach(b => b.classList.toggle('active', b.dataset.part === placement));
  $('align-description').textContent = ports.length ? ports.map(refName).join(' → ') : '选择模式下依次点击两个端口，移动第二个对象。';
  for (const action of ['align-x', 'align-y']) document.querySelector(`[data-action="${action}"]`).disabled = ports.length !== 2;
  renderCanvas(); renderInspector();
}

function addNode(type, position) {
  const entry = catalog.find(c => c.type === type), id = uid('node');
  edit(() => {
    const params = Object.fromEntries(Object.entries(entry.fields).map(([k, v]) => [k, v.default]));
    doc.nodes.push({ id, type, title: entry.label, x: snapped(position[0]), y: snapped(position[1]), params, rotation: 0 });
    doc.labels.push({ id: uid('label'), nodeId: id, x: 0, y: (params.h || 2 * params.r) / 2 + 24 + (type === 'four_way_valve' && params.mark ? 30 : 0),
      text: entry.label, size: 15, ha: 'center', color: '#111111', boxed: false });
    setSelection('node', id); placement = null; mode = 'select';
  });
}

function beginReconnect(edge, side) {
  message('');
  reconnect = { edgeId: edge.id, side }; mode = 'reconnect'; placement = null; pendingPort = null; ports = [];
  previewTarget = endpoint(edge[side], currentNodes(), doc.junctions);
  render(); status('请选择新的' + (side === 'source' ? '起点' : '终点') + '端口或三通 · Esc 取消');
}
function cancelReconnect() {
  message('');
  reconnect = null; previewTarget = null; mode = 'select'; render(); status('已取消重接，管路保持原连接');
}
function onPort(ref) {
  if (mode === 'reconnect' && reconnect) {
    try {
      const edge = doc.edges.find(e => e.id === reconnect.edgeId);
      const other = edge[reconnect.side === 'source' ? 'target' : 'source'];
      const a = endpoint(ref, currentNodes(), doc.junctions), b = endpoint(other, currentNodes(), doc.junctions);
      if (a.point.every((v, i) => v === b.point[i])) throw new Error('管路两端不能连接到同一位置，请选择其他端口或三通。');
      const next = reconnectEdge(doc, edge.id, reconnect.side, ref);
      message('');
      reconnect = null; previewTarget = null; mode = 'select';
      edit(() => { doc = next; });
    } catch (error) { message(error.message); }
    return;
  }
  if (mode === 'connect') {
    if (!pendingPort) {
      pendingPort = ref;
      previewTarget = endpoint(ref, currentNodes(), doc.junctions);
      status('已选择起点，请点击终点端口或三通');
    }
    else if (!eqRef(pendingPort, ref)) edit(() => {
      const id = uid('edge'); doc.edges.push({ id, source: pendingPort, target: ref, vertices: [], head: true, headAt: [.55], color: '#111111', width: 1.8, linestyle: 'solid' });
      setSelection('edge', id); pendingPort = null; previewTarget = null;
    });
    render(); return;
  }
  ports = ports.filter(p => !eqRef(p, ref));
  ports.push(ref); if (ports.length > 2) ports.shift(); render();
}

function alignPorts(axis) {
  if (ports.length !== 2) return;
  const [a, b] = ports.map(p => endpoint(p, currentNodes(), doc.junctions));
  const first = ports[0].nodeId || ports[0].junctionId;
  const second = ports[1].nodeId || ports[1].junctionId;
  if (first === second) return message('请选择两个不同设备或三通上的端口。');
  edit(() => {
    const ref = ports[1], n = ref.nodeId ? doc.nodes.find(n => n.id === ref.nodeId) : doc.junctions.find(j => j.id === ref.junctionId);
    n[axis] = +(n[axis] + a.point[axis === 'x' ? 0 : 1] - b.point[axis === 'x' ? 0 : 1]).toFixed(4);
  });
}

function splitEdge(edge) {
  const points = edgePoints(edge), split = splitRoute(points), { point: p, prefix, suffix } = split;
  const id = uid('junction');
  edit(() => {
    doc.junctions.push({ id, x: p[0], y: p[1] });
    // Keep the split point in both routes explicitly.  The junction endpoint
    // has no direction, so relying on route() to reconstruct the last/first
    // segment can otherwise leave a visible gap or make the branch start away
    // from the junction when the original edge contains corners.
    const other = { ...clone(edge), id: uid('edge'), source: { junctionId: id }, vertices: suffix };
    edge.target = { junctionId: id }; edge.vertices = prefix;
    doc.edges.push(other); setSelection('junction', id);
    doc.labels = splitEdgeLabels(doc.labels, edge.id, other.id);
  });
}

function removeSelected() {
  if (reconnect) return message('请先完成重接，或按 Esc 取消。');
  if (!multiSelection.length) return;
  try {
    const routes = new Map();
    for (const edge of doc.edges) {
      try { routes.set(edge.id, edgePoints(edge)); } catch { /* Newly placed geometry may still be loading. */ }
    }
    const next = deleteSelection(doc, multiSelection, routes);
    edit(() => {
      doc = next;
      ports = ports.filter(ref => ref.nodeId ? doc.nodes.some(n => n.id === ref.nodeId)
        : doc.junctions.some(j => j.id === ref.junctionId));
      pendingPort = null; previewTarget = null; clearSelection();
    });
  } catch (error) { message(error.message); }
}
function copySelected() {
  if (reconnect) return message('请先完成重接，或按 Esc 取消。');
  if (!multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind))) return;
  try {
    const result = copySelection(doc, multiSelection, uid);
    const originalNodes = multiSelection.filter(ref => ref.kind === 'node');
    result.selection.filter(ref => ref.kind === 'node').forEach((ref, index) => {
      const geometry = geometries.get(originalNodes[index].id);
      if (geometry) geometries.set(ref.id, geometry);
    });
    edit(() => {
      doc = result.document; multiSelection = result.selection; selection = multiSelection.at(-1) || null;
      pendingPort = null; previewTarget = null; mode = 'select'; placement = null;
    });
  } catch (error) { message(error.message); }
}
function clipboardReady() {
  if (!doc) return false;
  if (drag || reconnect || pendingPort || placement || mode !== 'select') {
    message('请先完成当前操作或切回选择模式，再复制粘贴。'); return false;
  }
  return true;
}
function showPageLayout() {
  if (drag || reconnect || pendingPort) return message('请先完成当前连接或拖动，或按 Esc 取消，再进行页面排版。');
  mode = 'select'; placement = null; ports = []; previewTarget = null; clearSelection(); render();
  document.body.classList.remove('library-open'); document.body.classList.add('properties-open');
  document.querySelector('.properties').scrollTop = 0;
  status('页面排版 · 内容居中或按内容调整页面尺寸');
}
function pageContentBoxes(resolved) {
  const boxes = resolved.nodes.map(n => transformedBox(n.geometry.box, [n.x, n.y], n.rotation));
  for (const j of doc.junctions) boxes.push([j.x - 4, j.y - 4, 8, 8]);
  // Measure at the origin and a fixed scale: SVG font hinting can otherwise
  // change text bounds as fitting changes the canvas zoom or label position.
  const measurement = shape('svg', { width: 100, height: 100, viewBox: '0 0 100 100',
    style: 'position:fixed;left:-10000px;top:-10000px;visibility:hidden;pointer-events:none',
    'aria-hidden': 'true' }, document.body);
  try {
    const labels = new Map(resolved.labels.map(label => [label.id, label]));
    for (const element of svg.querySelectorAll('.diagram-label')) {
      const label = labels.get(element.dataset.id), [x, y] = label.position;
      const text = element.querySelector('text').cloneNode(true);
      text.setAttribute('x', 0); text.setAttribute('y', 0);
      text.querySelectorAll('tspan').forEach(span => span.setAttribute('x', 0));
      measurement.append(text);
      const b = text.getBBox(), pad = label.boxed ? 2 : 0;
      boxes.push([x + b.x - pad, y + b.y - pad, b.width + pad * 2, b.height + pad * 2]);
    }
  } finally { measurement.remove(); }
  for (const edge of resolved.edges) {
    const xs = edge.points.map(p => p[0]), ys = edge.points.map(p => p[1]);
    const x = Math.min(...xs), y = Math.min(...ys), pad = Math.max(edge.width * 100 / 144, edge.head ? 4 : 0);
    boxes.push([x - pad, y - pad, Math.max(...xs) - x + pad * 2, Math.max(...ys) - y + pad * 2]);
  }
  return boxes;
}
async function applyPageLayout(action) {
  if (pageLayoutBusy) return;
  if (drag || reconnect || pendingPort || placement || mode !== 'select')
    return message('请先完成当前编辑操作，再进行页面排版。');
  const input = $('page-margin');
  if (action === 'fit' && input && !input.checkValidity()) { input.reportValidity(); return; }
  const version = revision, before = clone(doc), margin = pageMargin;
  pageLayoutBusy = true; message(''); renderInspector(); status('正在计算整张图纸的内容范围…');
  try {
    const resolved = await api('resolve', { document: before });
    if (version !== revision || drag || reconnect || pendingPort || placement || mode !== 'select') {
      status('图纸或操作已变化，请重新进行页面排版'); return;
    }
    geometries = new Map(resolved.nodes.map(n => [n.id, n.geometry])); fontFamily = resolved.fontFamily; renderCanvas();
    const boxes = pageContentBoxes(resolved);
    const next = layoutPage(doc, boxes, action, margin);
    const changed = JSON.stringify(next) !== JSON.stringify(doc);
    edit(() => { doc = next; }); fit();
    status(changed ? (action === 'fit' ? '页面已适配内容' : '内容已在页面中居中') + ' · Ctrl+Z 撤销' : '内容已符合当前排版设置');
  } catch (error) { message(error.message); status('未应用页面排版'); }
  finally {
    pageLayoutBusy = false;
    updateStyleButton();
    const empty = !['nodes', 'edges', 'junctions', 'labels'].some(name => doc[name].length);
    document.querySelectorAll('[data-page-layout]').forEach(button => { button.disabled = empty; });
    if ($('page-margin')) $('page-margin').disabled = false;
  }
}
function copyToClipboard() {
  if (!clipboardReady()) return;
  if (!multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind)))
    return message('请先选择设备、三通或文字；组内管路会随设备一起复制。');
  try {
    const positions = new Map(multiSelection.filter(ref => ref.kind === 'label')
      .map(ref => { const label = doc.labels.find(l => l.id === ref.id); return [ref.id, labelPosition(label)]; }));
    const fragment = captureSelection(doc, multiSelection, positions);
    const geometry = new Map(fragment.nodes.map(node => {
      const value = geometries.get(node.id);
      if (!value) throw new Error('图元正在更新，请稍后再复制。');
      return [node.id, clone(value)];
    }));
    editorClipboard = { fragment, geometry }; clipboardPastes = 0;
    render(); status(`已复制 ${fragment.nodes.length} 台设备、${fragment.junctions.length} 个三通、${fragment.edges.length} 条管路、${fragment.labels.length} 个标签 · 可切换图纸后 Ctrl+V 粘贴`);
  } catch (error) { message(error.message); }
}
function pasteClipboard() {
  if (!clipboardReady()) return;
  if (!editorClipboard) return message('编辑器剪贴板为空，请先选择对象并按 Ctrl+C。');
  try {
    const offset = 20 * (clipboardPastes + 1);
    const result = pasteFragment(doc, editorClipboard.fragment, uid, [offset, offset]);
    const originals = editorClipboard.fragment.selection.filter(ref => ref.kind === 'node');
    result.selection.filter(ref => ref.kind === 'node').forEach((ref, index) => {
      geometries.set(ref.id, editorClipboard.geometry.get(originals[index].id));
    });
    edit(() => {
      doc = result.document; multiSelection = result.selection; selection = multiSelection.at(-1) || null;
      ports = []; pendingPort = null; previewTarget = null;
    });
    clipboardPastes++;
    document.body.classList.remove('library-open');
    svg.focus({ preventScroll: true });
    status('已粘贴 · 可拖动整组调整位置 · Ctrl+Z 撤销');
  } catch (error) { message(error.message); }
}
function history(direction) {
  if (reconnect) cancelReconnect();
  const from = direction === 'undo' ? undo : redo, to = direction === 'undo' ? redo : undo;
  if (!from.length) return;
  to.push(clone(doc)); doc = from.pop(); clearSelection(); ports = []; pendingPort = null; previewTarget = null;
  revision++; dirty = true; saveDraft(); render(); void refresh();
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob), a = html('a'); a.href = url; a.download = filename;
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
}
function filename(extension) { return (doc.title || 'rrplot').replace(/[\\/:*?"<>|]/g, '_') + '.' + extension; }

function renderSaveState() {
  $('save-state').textContent = dirty ? '已修改 · 本机草稿' : 'JSON 图纸 · 本机编辑';
  $('save-json').disabled = saving || !doc || !!drag || pageLayoutBusy;
  $('save-json').textContent = saving ? '保存中…' : '保存 JSON';
  if (pendingDownload?.version !== revision) pendingDownload = null;
  $('download-banner').hidden = !pendingDownload;
}
function markJSONSaved(version) {
  if (version !== revision || drag) return false;
  // A clean template can coexist with an older recoverable draft at startup.
  if (dirty) clearDraft();
  dirty = false; pendingDownload = null;
  return true;
}
async function saveJSON() {
  if (!doc || saving || document.querySelector('dialog[open]')) return;
  if (drag || pageLayoutBusy) return message('请先完成拖动或页面排版，再保存图纸。');
  const snapshot = clone(doc), version = revision, name = filename('json');
  saving = true; renderSaveState();
  let writable = null;
  try {
    let handle = null;
    if (typeof window.showSaveFilePicker === 'function') {
      try {
        // Open before awaiting the server, while the click/shortcut is still active.
        handle = await window.showSaveFilePicker({ suggestedName: name, excludeAcceptAllOption: true,
          types: [{ description: 'rrplot JSON 图纸', accept: { 'application/json': ['.json'] } }] });
      } catch (error) {
        if (error.name === 'AbortError') { status('已取消保存 · 图纸与本机草稿保留'); return; }
        if (!['SecurityError', 'NotSupportedError'].includes(error.name)) throw error;
      }
    }
    const result = await api('resolve', { document: snapshot });
    const contents = JSON.stringify(result.document, null, 2);
    if (handle) {
      writable = await handle.createWritable();
      await writable.write(contents);
      await writable.close(); writable = null;
      const current = markJSONSaved(version);
      status(current ? '图纸 JSON 已保存：' + handle.name
        : '已保存操作开始时的图纸 · 当前图纸状态保留，请保存后续修改');
    } else {
      download(new Blob([contents], { type: 'application/json' }), name);
      if (version === revision && !drag) {
        if (dirty) pendingDownload = { version };
        status('JSON 下载已发起 · 请确认文件已保存');
      } else status('已发起操作开始时图纸的 JSON 下载 · 当前图纸状态保留');
    }
  } catch (error) {
    if (writable) try { await writable.abort(); } catch { /* Preserve the original write error. */ }
    message('保存 JSON 失败：' + error.message);
    status('JSON 未保存完成 · 图纸与本机草稿保留');
  } finally { saving = false; renderSaveState(); }
}
function confirmJSONDownload() {
  if (!pendingDownload || saving || document.querySelector('dialog[open]')) return;
  if (markJSONSaved(pendingDownload.version)) status('已确认 JSON 文件保存 · 后续修改将继续记录草稿');
  renderSaveState();
}

function objectName(ref) {
  const item = doc[{ node: 'nodes', edge: 'edges', junction: 'junctions', label: 'labels' }[ref.kind]].find(i => i.id === ref.id);
  if (ref.kind === 'edge') return '管路：' + refName(item.source) + ' → ' + refName(item.target);
  return ref.kind === 'node' ? '设备：' + item.title : ref.kind === 'label' ? '文字：' + item.text : '三通 · ' + item.id.slice(-5);
}
function locateObject(ref, additive = false) {
  if (drag || reconnect || pendingPort) return message('请先完成当前连接或拖动，或按 Esc 取消，再定位对象。');
  mode = 'select'; placement = null; reconnect = null; pendingPort = null; previewTarget = null; ports = [];
  setSelection(ref.kind, ref.id, additive); render();
  let box = selectionCandidates().find(item => item.kind === ref.kind && item.id === ref.id)?.box;
  if (ref.kind === 'edge') {
    const points = edgePoints(doc.edges.find(item => item.id === ref.id)), xs = points.map(p => p[0]), ys = points.map(p => p[1]);
    box = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
  }
  if (box) {
    const [x, y, w, h] = box, ratio = svg.clientWidth / svg.clientHeight;
    view.w = Math.max(view.w, w + 80, (h + 80) * ratio); view.h = view.w / ratio;
    view.x = x + w / 2 - view.w / 2; view.y = y + h / 2 - view.h / 2; updateView();
  }
  document.body.classList.remove('library-open'); document.body.classList.add('properties-open');
  document.querySelector('.properties').scrollTop = 0;
  svg.focus({ preventScroll: true }); status('已定位：' + objectName(ref));
}
function locateIssue(ref) {
  $('checks-dialog').close(); locateObject(ref);
}
function renderObjectList() {
  if (!doc || $('objects-panel').hidden) return;
  const entries = objectIndex(doc, catalog), found = filterObjects(entries, $('object-search').value, $('object-kind').value);
  $('object-count').textContent = `显示 ${Math.min(found.length, 200)} / 匹配 ${found.length} / 共 ${entries.length} 项`;
  const root = $('object-list'); root.replaceChildren();
  for (const entry of found.slice(0, 200)) {
    const active = selected(entry.kind, entry.id);
    const button = html('button', undefined, 'object-entry' + (active ? ' active' : ''));
    button.dataset.kind = entry.kind; button.dataset.id = entry.id;
    button.setAttribute('aria-pressed', active);
    button.title = `${entry.type}：${entry.title}\nID：${entry.id}\n${entry.detail}`;
    button.append(html('strong', `${entry.type} · ${entry.title}`), html('small', entry.id));
    button.addEventListener('click', event => locateObject(entry, event.shiftKey)); root.append(button);
  }
  if (!found.length) root.append(html('p', entries.length ? '没有匹配的对象，请调整搜索或类型。' : '图纸为空，请从图元库添加设备。', 'muted'));
  if (found.length > 200) root.append(html('p', '仅显示前 200 项，请搜索名称或 ID 缩小范围。', 'muted'));
}
const libraryPanes = [['show-parts', 'library-parts'], ['show-templates', 'templates-panel'], ['show-objects', 'objects-panel']];
for (const [id] of libraryPanes) {
  $(id).addEventListener('click', () => {
    for (const [buttonId, paneId] of libraryPanes) {
      const active = buttonId === id;
      $(paneId).hidden = !active;
      $(buttonId).classList.toggle('active', active); $(buttonId).setAttribute('aria-pressed', active);
    }
    renderObjectList();
  });
}
$('object-search').addEventListener('input', renderObjectList);
$('object-kind').addEventListener('change', renderObjectList);
function filterPalette() {
  const words = $('part-search').value.normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean);
  let count = 0;
  document.querySelectorAll('[data-part]').forEach(button => {
    button.hidden = !words.every(word => button.textContent.normalize('NFKC').toLowerCase().includes(word));
    if (!button.hidden) count++;
  });
  $('part-count').textContent = `显示 ${count} / 共 ${catalog.length} 种图元`;
  $('part-empty').hidden = count > 0;
}
$('part-search').addEventListener('input', filterPalette);
function filterTemplates() {
  const words = $('template-search').value.normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean);
  const buttons = [...document.querySelectorAll('[data-template]')];
  let count = 0;
  for (const button of buttons) {
    const text = `${button.textContent} ${button.dataset.template}`.normalize('NFKC').toLowerCase();
    button.hidden = !words.every(word => text.includes(word));
    if (!button.hidden) count++;
  }
  $('template-count').textContent = `显示 ${count} / 共 ${buttons.length} 个模板`;
  $('template-empty').hidden = count > 0;
}
$('template-search').addEventListener('input', filterTemplates);
async function runChecks() {
  if (reconnect || drag || pendingPort) return message('请先完成当前连接或拖动，或按 Esc 取消，再检查图纸。');
  const version = revision;
  status('正在检查图纸…');
  let result;
  try { result = await api('resolve', { document: clone(doc) }); }
  catch (error) { status('检查未完成，请查看提示'); throw error; }
  if (version !== revision || drag || reconnect || pendingPort) {
    status('图纸已变化，请重新检查');
    return message('图纸或当前操作已变化，请完成后重新点击“检查”。');
  }
  geometries = new Map(result.nodes.map(n => [n.id, n.geometry])); fontFamily = result.fontFamily; renderCanvas();
  const routes = new Map(doc.edges.map(edge => [edge.id, edgePoints(edge)]));
  const issues = inspectDiagram(doc, { nodes: currentNodes(), routes, bounds: selectionCandidates() });
  const root = $('checks-results'); root.replaceChildren();
  $('checks-summary').textContent = issues.length ? `发现 ${issues.length} 项待核对，点击结果定位并查看属性。` : '未发现连接或页面越界问题。';
  for (const issue of issues.slice(0, 100)) {
    const button = html('button', undefined, 'check-result');
    button.append(html('strong', issue.title), html('span', objectName(issue.ref), 'check-object'), html('span', issue.detail, 'check-detail'), html('span', '定位 →', 'check-locate'));
    button.addEventListener('click', () => locateIssue(issue.ref)); root.append(button);
  }
  if (issues.length > 100) root.append(html('p', '仅显示前 100 项；修改后再次检查可查看剩余结果。', 'muted'));
  if (!$('checks-dialog').open) $('checks-dialog').showModal();
  status(issues.length ? `检查完成 · ${issues.length} 项待核对` : '检查完成 · 未发现问题');
}

const actions = {
  new: async () => { if (await confirmReplace()) await replaceDocument({ schemaVersion: 1, title: '未命名图纸', page: { width: 1000, height: 700 }, nodes: [], edges: [], junctions: [], labels: [] }); },
  open: () => $('file-input').click(),
  save: saveJSON,
  'confirm-download': confirmJSONDownload,
  'dismiss-download': () => { pendingDownload = null; renderSaveState(); },
  export: async () => {
    status('正在生成导出文件…');
    const format = $('export-format').value;
    const blob = await api('export/' + format, { document: doc, dpi: 140 });
    download(blob, filename(format)); status(format.toUpperCase() + ' 已导出');
  },
  preview: async () => {
    status('正在生成正式预览…');
    const blob = await api('preview', { document: doc });
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(blob); $('preview-image').src = previewUrl;
    $('preview-dialog').showModal(); status('正式出图预览已生成');
  },
  'close-preview': () => $('preview-dialog').close(),
  check: runChecks, 'close-checks': () => $('checks-dialog').close(),
  'toggle-library': () => { document.body.classList.toggle('library-open'); document.body.classList.remove('properties-open'); },
  'toggle-properties': () => { document.body.classList.toggle('properties-open'); document.body.classList.remove('library-open'); },
  undo: () => history('undo'), redo: () => history('redo'), copy: copySelected, delete: removeSelected,
  'clipboard-copy': copyToClipboard, 'clipboard-paste': pasteClipboard,
  'page-layout': showPageLayout, 'batch-styles': showBatchStyles,
  'close-styles': () => $('styles-dialog').close(),
  fit, 'zoom-in': () => zoom(.85), 'zoom-out': () => zoom(1 / .85),
  'align-x': () => alignPorts('x'), 'align-y': () => alignPorts('y'),
  'clear-ports': () => { ports = []; pendingPort = null; previewTarget = null; render(); },
  restore: async () => {
    const saved = JSON.parse(localStorage.getItem(DRAFT));
    if (saved?.document && await confirmReplace()) { await replaceDocument(saved.document); dirty = true; saveDraft(); render(); }
    $('draft-banner').hidden = true;
  },
  'dismiss-draft': () => { $('draft-banner').hidden = true; }
};

document.addEventListener('click', async event => {
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (action && doc) try { await actions[action]?.(); } catch (error) { message(error.message); }
  const tool = event.target.closest('[data-tool]')?.dataset.tool;
  if (tool) setTool(tool);
});

function setTool(tool) {
  mode = tool; placement = null; pendingPort = null; previewTarget = null; reconnect = null;
  if (tool === 'move-all') { clearSelection(); ports = []; }
  render();
  status('工具：' + { select: '选择', 'box-select': '框选：拖出矩形完整框住对象，Shift 可追加', 'move-all': '整体移动：按住左键拖动全部内容', connect: '连线：点击起点和终点端口，鼠标靠近时自动吸附', junction: '在空白处放三通，或选中管路后在属性中插入', text: '在画布点击放置文字' }[tool]);
}

svg.addEventListener('pointerdown', event => {
  if (!doc || event.button > 1) return;
  svg.focus({ preventScroll: true });
  const p = world(event), hit = event.target.closest('[data-kind]');
  if (event.button === 1 || spaceDown) return startPan(event);
  if (mode === 'reconnect') {
    event.preventDefault();
    if (hit?.dataset.kind === 'port') onPort(JSON.parse(hit.dataset.ref));
    else if (hit?.dataset.kind === 'junction') onPort({ junctionId: hit.dataset.id });
    else status('请点击设备端口或三通 · 空格拖动平移 · Esc 取消');
    return;
  }
  if (mode === 'box-select' || (mode === 'select' && !placement && event.shiftKey && !hit)) {
    drag = { kind: 'box', start: p, point: p, candidates: selectionCandidates(),
      beforeSelection: clone(multiSelection), additive: event.shiftKey, moved: false, pointerId: event.pointerId };
    svg.setPointerCapture(event.pointerId); event.preventDefault(); return;
  }
  if (mode === 'move-all') {
    ++request;
    drag = { kind: 'all', start: p, before: clone(doc), pointerId: event.pointerId, moved: false };
    svg.setPointerCapture(event.pointerId); event.preventDefault(); return;
  }
  if (hit?.dataset.kind === 'port') { event.preventDefault(); onPort(JSON.parse(hit.dataset.ref)); return; }
  if (hit?.dataset.kind === 'junction' && mode === 'connect') { onPort({ junctionId: hit.dataset.id }); return; }
  if (placement) { addNode(placement, p); return; }
  if (mode === 'junction' && !hit) {
    edit(() => { const id = uid('junction'); doc.junctions.push({ id, x: snapped(p[0]), y: snapped(p[1]) }); setSelection('junction', id); mode = 'select'; }); return;
  }
  if (mode === 'text' && !hit) {
    edit(() => { const id = uid('label'); doc.labels.push({ id, text: '文字', x: snapped(p[0]), y: snapped(p[1]), size: 15, ha: 'center', color: '#111111', boxed: false }); setSelection('label', id); mode = 'select'; }); return;
  }
  if (!hit) { clearSelection(); render(); return startPan(event); }
  const kind = hit.dataset.kind, id = hit.dataset.id;
  if (kind === 'vertex' && event.altKey) {
    edit(() => doc.edges.find(e => e.id === id).vertices.splice(Number(hit.dataset.index), 1)); return;
  }
  const selectedKind = ['vertex', 'segment'].includes(kind) ? 'edge' : kind;
  const additive = event.shiftKey && ['node', 'label', 'junction', 'edge'].includes(selectedKind);
  const keepMulti = !additive && multiSelection.length > 1
    && multiSelection.some(ref => ref.kind === selectedKind && ref.id === id);
  if (!keepMulti) setSelection(selectedKind, id, additive);
  if (additive) { render(); return; }
  const item = findSelected();
  if (kind === 'segment') {
    ++request;
    const nodes = currentNodes(), index = Number(hit.dataset.index);
    const source = endpoint(item.source, nodes, doc.junctions), target = endpoint(item.target, nodes, doc.junctions);
    const segment = editableSegments(source, target, item.vertices).find(s => s.index === index);
    if (!segment) return;
    drag = { kind, id, index, source, target, axis: segment.axis, coordinate: segment.point[segment.axis],
      vertices: clone(item.vertices), start: p, before: clone(doc), pointerId: event.pointerId, moved: false };
    svg.setPointerCapture(event.pointerId); event.preventDefault(); return;
  }
  if (kind === 'edge') {
    // Keep the clicked path alive so the browser can deliver a double click.
    svg.querySelectorAll('[data-kind="node"], [data-kind="edge"], [data-kind="label"], [data-kind="junction"]')
      .forEach(element => element.classList.toggle('selected', selected(element.dataset.kind, element.dataset.id)));
    renderInspector(); renderVertices(); return;
  }
  if (['node', 'label', 'junction', 'vertex'].includes(kind)) {
    ++request;
    if (multiSelection.length > 1 && multiSelection.some(ref => ref.kind === selectedKind && ref.id === id)) {
      drag = { kind: 'multi', start: p, before: clone(doc), pointerId: event.pointerId, moved: false };
    } else {
      drag = { kind, id, start: p, before: clone(doc), origin: kind === 'vertex' ? [...item.vertices[Number(hit.dataset.index)]] : [item.x, item.y],
        index: Number(hit.dataset.index), pointerId: event.pointerId, moved: false };
    }
    svg.setPointerCapture(event.pointerId); event.preventDefault();
  }
  render();
});
function startPan(event) {
  drag = { kind: 'pan', client: [event.clientX, event.clientY], origin: { ...view }, pointerId: event.pointerId };
  svg.setPointerCapture(event.pointerId); svg.classList.add('panning'); event.preventDefault();
}
svg.addEventListener('pointermove', event => {
  if (!drag) {
    if ((mode === 'connect' && pendingPort) || reconnect) {
      const next = connectionTarget(event, world(event));
      const changed = !previewTarget || next.point.some((value, index) => value !== previewTarget.point[index])
        || next.direction.some((value, index) => value !== previewTarget.direction[index]);
      if (changed) { previewTarget = next; renderCanvas(); }
    }
    return;
  }
  if (drag.kind === 'pan') {
    view.x = drag.origin.x - (event.clientX - drag.client[0]) * view.w / svg.clientWidth;
    view.y = drag.origin.y - (event.clientY - drag.client[1]) * view.h / svg.clientHeight;
    updateView(); return;
  }
  const p = world(event), delta = p.map((v, i) => v - drag.start[i]);
  if (drag.kind === 'box') {
    if (!drag.moved && Math.hypot(...delta) < 2) return;
    drag.moved = true; drag.point = p;
    multiSelection = selectInBox(drag.candidates, drag.start, p, drag.additive ? drag.beforeSelection : []);
    selection = multiSelection.at(-1) || null;
    renderCanvas(); renderInspector(); return;
  }
  if (drag.kind === 'segment') {
    if (!drag.moved && Math.abs(delta[drag.axis]) < 1) return;
    const offset = snapped(drag.coordinate + delta[drag.axis]) - drag.coordinate;
    const vertices = moveSegment(drag.source, drag.target, drag.vertices, drag.index, offset);
    if (vertices.length > 100) return message('管路折点已达上限，请先清除部分折点。');
    drag.moved = true;
    doc.edges.find(e => e.id === drag.id).vertices = vertices;
    renderCanvas(); return;
  }
  if (!drag.moved && Math.hypot(...delta) < 1) return;
  drag.moved = true;
  if (drag.kind === 'all') {
    doc = translateDocument(drag.before, ...delta.map(snapped));
    renderCanvas(); return;
  }
  if (drag.kind === 'multi') {
    doc = translateSelection(drag.before, multiSelection, delta.map(snapped));
    renderCanvas(); return;
  }
  const item = findSelected();
  if (drag.kind === 'label' && item.nodeId) {
    const n = doc.nodes.find(n => n.id === item.nodeId), local = rotate(delta, -n.rotation);
    [item.x, item.y] = drag.origin.map((v, i) => snapped(v + local[i]));
  } else if (drag.kind === 'vertex') item.vertices[drag.index] = drag.origin.map((v, i) => snapped(v + delta[i]));
  else [item.x, item.y] = drag.origin.map((v, i) => snapped(v + delta[i]));
  renderCanvas();
});
svg.addEventListener('pointerleave', () => {
  if (!drag && ((mode === 'connect' && pendingPort) || reconnect) && previewTarget) { previewTarget = null; renderCanvas(); }
});
function endDrag(event) {
  if (!drag) return;
  const current = drag; drag = null; svg.classList.remove('panning');
  if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  if (current.kind === 'box') {
    if (!current.moved && !current.additive) clearSelection();
    mode = 'select'; render();
    status(multiSelection.length ? `已选择 ${multiSelection.length} 项 · 可批量设置样式或删除，拖动设备、三通和文字可移动`
      : '未框选对象，请完整框住设备、管路、三通或文字');
    return;
  }
  if (current.kind !== 'pan') finishEdit(current.before);
}
svg.addEventListener('pointerup', endDrag);
function cancelDrag() {
  const current = drag;
  if (drag?.before) doc = drag.before;
  if (drag?.kind === 'box') {
    multiSelection = drag.beforeSelection;
    selection = multiSelection.at(-1) || null;
  }
  drag = null; svg.classList.remove('panning');
  if (current && svg.hasPointerCapture(current.pointerId)) svg.releasePointerCapture(current.pointerId);
  render();
}
svg.addEventListener('pointercancel', cancelDrag);
svg.addEventListener('dblclick', event => {
  if (event.shiftKey || mode === 'move-all' || mode === 'box-select' || reconnect) return;
  if (event.target.closest('[data-kind="segment"]')) return;
  const hit = event.target.closest('[data-kind="edge"]'); if (!hit) return;
  const edge = doc.edges.find(e => e.id === hit.dataset.id), points = edgePoints(edge), p = world(event);
  const index = nearestSegment(points, p);
  edit(() => { const vertices = points.slice(1, -1); vertices.splice(index, 0, p.map(snapped)); edge.vertices = vertices; setSelection('edge', edge.id); });
});
svg.addEventListener('wheel', event => { event.preventDefault(); if (doc) zoom(event.deltaY > 0 ? 1.1 : 1 / 1.1, world(event)); }, { passive: false });
svg.addEventListener('dragover', event => event.preventDefault());
svg.addEventListener('drop', event => { event.preventDefault(); const type = event.dataTransfer.getData('text/rrplot-part'); if (catalog.some(c => c.type === type)) { reconnect = null; addNode(type, world(event)); } });

$('title').addEventListener('change', event => edit(() => { doc.title = event.target.value; }));
 $('grid').addEventListener('change', () => {
  renderCanvas(); status($('grid').checked ? '网格已显示' : '网格已隐藏');
 });
 $('snap').addEventListener('change', () => {
  status($('snap').checked ? '网格吸附已开启' : '网格吸附已关闭');
 });
$('file-input').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 5000000) throw new Error('图纸文件超过 5 MB');
    const next = JSON.parse(await file.text());
    if (await confirmReplace()) await replaceDocument(next);
  } catch (error) { message('无法打开图纸：' + error.message); }
  event.target.value = '';
});
function updateStyleButton() {
  $('batch-styles').disabled = mode !== 'select' || !!(placement || pendingPort || reconnect || drag || pageLayoutBusy)
    || !(doc.edges.length || doc.labels.length);
}

function showBatchStyles() {
  if (!doc || mode !== 'select' || placement || pendingPort || reconnect || drag || pageLayoutBusy)
    return message('请先完成当前操作或按 Esc，再设置批量样式。');
  styleSession = { revision, selection: clone(multiSelection), controls: [] };
  $('style-scope').value = multiSelection.length ? 'selection' : 'all';
  renderStyleFields();
  $('styles-dialog').showModal();
}

function renderStyleFields() {
  const scope = $('style-scope').value;
  const targets = styleTargets(doc, styleSession.selection, scope);
  $('style-summary').textContent = `将处理 ${targets.edges.length} 条管路、${targets.labels.length} 个标签。`
    + (scope === 'selection' ? ' 包含所选设备的标签、两端均在组内的管路及其状态点。' : ' 包含独立文字、设备标签和管路状态点。');
  $('style-error').textContent = '';
  const root = $('style-fields'); root.replaceChildren(); styleSession.controls = [];
  for (const [group, title, specs] of [
    ['edges', '管路', [
      ['color', '管路颜色', '#111111', { type: 'color' }],
      ['width', '线宽（pt）', 1.8, { min: .2, max: 8, required: true }],
      ['linestyle', '线型', 'solid', { options: [{ value: 'solid', label: '实线' }, { value: 'dashed', label: '虚线' }] }],
      ['head', '流向箭头', true, { options: [{ value: 'true', label: '显示' }, { value: 'false', label: '隐藏' }] }]
    ]],
    ['labels', '标签', [
      ['color', '文字颜色', '#111111', { type: 'color' }],
      ['size', '字号（pt）', 15, { min: 6, max: 72, required: true }],
      ['ha', '文字对齐', 'center', { options: [{ value: 'left', label: '左对齐' }, { value: 'center', label: '居中' }, { value: 'right', label: '右对齐' }] }],
      ['boxed', '白色背景', false, { options: [{ value: 'true', label: '显示' }, { value: 'false', label: '隐藏' }] }]
    ]]
  ]) {
    const section = html('section', undefined, 'style-section');
    section.append(html('h3', `${title} · ${targets[group].length} 项`)); root.append(section);
    const ids = new Set(targets[group]), items = doc[group].filter(item => ids.has(item.id));
    for (const [key, caption, fallback, options] of specs) {
      const row = html('div', undefined, 'style-row'); section.append(row);
      const label = html('label', undefined, 'style-enable'), enable = html('input');
      enable.type = 'checkbox'; enable.disabled = !items.length;
      enable.setAttribute('aria-label', '修改' + caption); label.append(enable, html('span', caption)); row.append(label);
      const common = items.length && items.every(item => item[key] === items[0][key]);
      const initial = common ? items[0][key] : fallback;
      const namedColor = options.type === 'color' && !/^#[0-9a-f]{6}$/i.test(initial);
      const input = field(row, '批量' + caption, namedColor ? fallback : initial, () => {}, { ...options, disabled: true, transient: true });
      if (!common && items.length) row.append(html('small', '当前值不一致', 'muted'));
      else if (namedColor) row.append(html('small', '请重新选择颜色', 'muted'));
      enable.addEventListener('change', () => { input.disabled = !enable.checked; updateStyleApply(); });
      styleSession.controls.push({ group, key, enable, input });
    }
  }
  updateStyleApply();
}

function updateStyleApply() {
  $('style-apply').disabled = !styleSession.controls.some(control => control.enable.checked);
}

$('style-scope').addEventListener('change', renderStyleFields);
$('styles-dialog').addEventListener('close', () => { styleSession = null; });
$('style-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!styleSession || revision !== styleSession.revision) {
    $('style-error').textContent = '图纸已变化，请关闭后重新打开批量样式。'; return;
  }
  const patch = {};
  for (const { group, key, enable, input } of styleSession.controls) {
    if (!enable.checked) continue;
    (patch[group] ||= {})[key] = input.type === 'number' ? Number(input.value)
      : ['head', 'boxed'].includes(key) ? input.value === 'true' : input.value;
  }
  if (!Object.keys(patch).length) return;
  try {
    const next = applyStyles(doc, styleSession.selection, $('style-scope').value, patch);
    const changed = JSON.stringify(next) !== JSON.stringify(doc);
    if (changed) edit(() => { doc = next; });
    $('styles-dialog').close();
    status(changed ? '批量样式已应用 · Ctrl+Z 可一次撤销' : '样式已一致，无需修改');
  } catch (error) { $('style-error').textContent = error.message; }
});

function endNudge() {
  if (!nudge) return;
  nudge = null;
  if (doc) void refresh();
}
function nudgeSelected(event) {
  if (!doc || mode !== 'select' || placement || reconnect || pendingPort || drag || spaceDown
    || !multiSelection.some(ref => ['node', 'junction', 'label'].includes(ref.kind))) return;
  const refs = JSON.stringify(multiSelection);
  try {
    const next = nudgeSelection(doc, multiSelection, event.key, event.shiftKey);
    const merge = !!event.repeat && nudge?.key === event.key && nudge.refs === refs && nudge.version === revision;
    const before = doc; doc = next;
    ++request;
    finishEdit(before, { merge, deferRefresh: true });
    nudge = { key: event.key, refs, version: revision };
    status(`已微调 ${event.shiftKey ? 10 : 1} 单位 · 松开方向键结束 · Ctrl+Z 撤销`);
  } catch (error) { endNudge(); message(error.message); }
}
document.addEventListener('pointerdown', endNudge, true);
document.addEventListener('focusin', endNudge);
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('keydown', async event => {
  if (event.target.matches('input,textarea,select') || event.target.isContentEditable || event.isComposing || document.querySelector('dialog[open]')) return;
  if (event.key.startsWith('Arrow') && !event.ctrlKey && !event.metaKey && !event.altKey
    && (event.target === document.body || event.target === svg || svg.contains(event.target))) {
    event.preventDefault(); nudgeSelected(event); return;
  }
  if (!['Shift', 'Alt', 'Control', 'Meta'].includes(event.key)) endNudge();
  if (event.key === 'Escape' && reconnect) { event.preventDefault(); cancelReconnect(); return; }
  const modifier = event.ctrlKey || event.metaKey;
  if (event.code === 'Space') { spaceDown = true; event.preventDefault(); }
  if (event.key === 'Escape') { mode = 'select'; placement = null; pendingPort = null; previewTarget = null; ports = []; cancelDrag(); }
  if (drag) return;
  if (modifier && event.key.toLowerCase() === 'a') { event.preventDefault(); setTool('move-all'); }
  if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); removeSelected(); }
  if (modifier && event.key.toLowerCase() === 'z') { event.preventDefault(); history(event.shiftKey ? 'redo' : 'undo'); }
  if (modifier && event.key.toLowerCase() === 'y') { event.preventDefault(); history('redo'); }
  if (modifier && event.key.toLowerCase() === 'd') { event.preventDefault(); copySelected(); }
  if (modifier && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'c') { event.preventDefault(); copyToClipboard(); }
  if (modifier && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'v') { event.preventDefault(); pasteClipboard(); }
  if (modifier && event.key.toLowerCase() === 's') { event.preventDefault(); try { await actions.save(); } catch (error) { message(error.message); } }
});
window.addEventListener('keyup', event => {
  if (event.key === nudge?.key) endNudge();
  if (event.code === 'Space') spaceDown = false;
});
window.addEventListener('blur', () => { spaceDown = false; endNudge(); });
new ResizeObserver(() => { if (doc) updateView(); }).observe(svg);

async function init() {
  try {
    const data = await Promise.all([api('catalog'), api('templates'), api('templates/evi_ftvi')]);
    [catalog] = data;
    for (const entry of catalog) {
      const b = html('button', undefined, 'part-button'); b.dataset.part = entry.type; b.draggable = true;
      b.append(html('span', entry.label.slice(0, 1), 'part-icon'));
      const name = html('span', entry.label); name.append(html('small', entry.type)); b.append(name);
      b.addEventListener('click', () => { placement = entry.type; mode = 'select'; pendingPort = null; previewTarget = null; reconnect = null; document.body.classList.remove('library-open'); render(); status('在画布点击放置：' + entry.label); });
      b.addEventListener('dragstart', event => event.dataTransfer.setData('text/rrplot-part', entry.type));
      $('palette').append(b);
    }
    for (const template of data[1]) {
      const b = html('button', template.title); b.dataset.template = template.id;
      b.addEventListener('click', async () => { try { if (await confirmReplace()) { await replaceDocument(await api('templates/' + template.id)); document.body.classList.remove('library-open'); } } catch (error) { message(error.message); } });
      $('templates').append(b);
    }
    filterPalette();
    filterTemplates();
    await replaceDocument(data[2], true);
    try { if (JSON.parse(localStorage.getItem(DRAFT))?.document) $('draft-banner').hidden = false; } catch { /* Ignore invalid old drafts. */ }
  } catch (error) { message('无法连接本机服务。请运行 python server/run.py。' + error.message); status('服务未连接'); }
}
void init();
