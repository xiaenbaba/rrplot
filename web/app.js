import { rotate, endpoint, route, along, nearestSegment, splitRoute, translateDocument } from './geometry.js';

const $ = id => document.getElementById(id);
const svg = $('diagram');
const NS = 'http://www.w3.org/2000/svg';
const clone = value => structuredClone(value);
const uid = prefix => prefix + '-' + crypto.randomUUID().slice(0, 8);
const DRAFT = 'rrplot-web-v1-draft';
let doc = null, catalog = [], geometries = new Map(), fontFamily = 'Times New Roman, SimSun, serif';
let selection = null, multiSelection = [], mode = 'select', placement = null, ports = [], pendingPort = null;
let undo = [], redo = [], drag = null, dirty = false, spaceDown = false;
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
  if (additive && ['node', 'label', 'junction'].includes(kind)) {
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
  if (!label.nodeId) return [label.x, label.y];
  const n = doc.nodes.find(n => n.id === label.nodeId);
  const p = rotate([label.x, label.y], n.rotation);
  return [n.x + p[0], n.y + p[1]];
}
function edgePoints(edge) {
  const nodes = currentNodes();
  return route(endpoint(edge.source, nodes, doc.junctions), endpoint(edge.target, nodes, doc.junctions), edge.vertices);
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

function finishEdit(before) {
  if (JSON.stringify(before) === JSON.stringify(doc)) return render();
  undo.push(before); if (undo.length > 80) undo.shift(); redo = [];
  dirty = true; revision++; saveDraft(); render(); void refresh();
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
  if (token !== request || version !== revision) return;
  ++revision;
  doc = result.document; geometries = new Map(result.nodes.map(n => [n.id, n.geometry]));
  fontFamily = result.fontFamily; undo = []; redo = []; clearSelection(); ports = [];
  pendingPort = null; mode = 'select'; placement = null; dirty = false;
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
  svg.classList.toggle('connecting', mode === 'connect');
  svg.classList.toggle('moving-all', mode === 'move-all');
  svg.classList.toggle('placing', !!placement || ['junction', 'text'].includes(mode));
  const defs = shape('defs');
  const pattern = shape('pattern', { id: 'grid-pattern', width: 10, height: 10, patternUnits: 'userSpaceOnUse' }, defs);
  shape('circle', { cx: 0, cy: 0, r: .5, fill: '#b7c5cf' }, pattern);
  shape('rect', { x: 0, y: 0, width: doc.page.width, height: doc.page.height, fill: '#fff', class: 'page' });
  if ($('grid').checked) shape('rect', { width: doc.page.width, height: doc.page.height, fill: 'url(#grid-pattern)', opacity: .65, 'pointer-events': 'none' });
  const nodes = currentNodes();
  for (const edge of doc.edges) {
    let points;
    try { points = edgePoints(edge); } catch { continue; }
    const g = shape('g', { class: 'edge' + (selected('edge', edge.id) ? ' selected' : ''), 'data-kind': 'edge', 'data-id': edge.id });
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
      const circle = shape('circle', { cx: p.point[0], cy: p.point[1], r: 4.5,
        class: 'port' + (chosen ? ' chosen' : ''), 'data-kind': 'port', 'data-ref': JSON.stringify(ref) }, g);
      shape('title', {}, circle).textContent = id;
    }
  }
  for (const j of doc.junctions) {
    const c = shape('circle', { cx: j.x, cy: j.y, r: 4, fill: '#111',
      class: 'junction' + (selected('junction', j.id) ? ' selected' : ''),
      'data-kind': 'junction', 'data-id': j.id });
    shape('title', {}, c).textContent = '三通';
  }
  for (const label of doc.labels) {
    const [x, y] = labelPosition(label);
    const g = shape('g', { class: 'diagram-label', 'data-kind': 'label', 'data-id': label.id });
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
  updateView();
}

function renderVertices() {
  svg.querySelectorAll('[data-kind="vertex"]').forEach(element => element.remove());
  const e = selection?.kind === 'edge' && findSelected();
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
  if (options.options) options.options.forEach(v => { const o = html('option', String(v)); o.value = v; input.append(o); });
  else if (!options.multiline) input.type = options.type || (typeof value === 'number' ? 'number' : 'text');
  if (options.min !== undefined) input.min = options.min;
  if (options.max !== undefined) input.max = options.max;
  if (input.type === 'number') input.step = options.step || 'any';
  if (input.type === 'checkbox') input.checked = value; else input.value = value;
  let committed = value;
  function commit() {
    if (!input.checkValidity()) { input.reportValidity(); return; }
    const next = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
    if (next === committed) return;
    committed = next;
    edit(() => setter(next));
  }
  input.addEventListener('change', commit);
  input.addEventListener('blur', commit);
  wrap.append(input); parent.append(wrap); return input;
}
function inspectorButton(parent, caption, action) {
  const b = html('button', caption); b.addEventListener('click', action); parent.append(b); return b;
}
function renderInspector() {
  const root = $('inspector'); root.replaceChildren();
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
    root.append(html('p', '按住 Shift 点击可继续添加或取消选择。拖动任意已选对象，可一起移动设备、三通和文字。', 'muted'));
    const layout = html('div', undefined, 'layout-grid');
    for (const [action, caption] of [
      ['align-left', '左对齐'], ['align-center-x', '水平居中'], ['align-right', '右对齐'],
      ['align-top', '上对齐'], ['align-center-y', '垂直居中'], ['align-bottom', '下对齐'],
      ['distribute-x', '水平等距'], ['distribute-y', '垂直等距'],
    ]) inspectorButton(layout, caption, () => batchLayout(action));
    root.append(html('div', '批量布局', 'section-label'), layout);
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
    root.append(html('p', '选择设备、标签或管路查看属性。坐标单位与 rrplot 画布一致。', 'muted')); return;
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
    inspectorButton(root, '添加设备标签', () => edit(() => {
      const id = uid('label'); doc.labels.push({ id, nodeId: item.id, x: 0, y: 70, text: item.title, size: 15, ha: 'center', boxed: true, color: '#111111' }); setSelection('label', id);
    }));
  } else if (kind === 'label') {
    field(root, '标签内容', item.text, v => { item.text = v; }, { multiline: true });
    coordinateFields(root, item, item.nodeId ? '相对偏移' : '');
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
    root.append(html('p', `${item.vertices.length} 个手动顶点。双击管线添加，Alt+点击控制点删除。`, 'muted'));
    const buttons = html('div', undefined, 'button-row'); root.append(buttons);
    inspectorButton(buttons, '反向', () => edit(() => { [item.source, item.target] = [item.target, item.source]; item.vertices.reverse(); }));
    inspectorButton(buttons, '清除折点', () => edit(() => { item.vertices = []; }));
    inspectorButton(root, '在管路中间插入三通', () => splitEdge(item));
  }
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

function render() {
  if (!doc) return;
  $('title').value = doc.title;
  $('save-state').textContent = dirty ? '已修改 · 本机草稿' : 'JSON 图纸 · 本机编辑';
  $('undo').disabled = !undo.length; $('redo').disabled = !redo.length;
  $('counts').textContent = `${doc.nodes.length} 个设备 · ${doc.edges.length} 条管路`;
  document.querySelector('.canvas-hint').textContent = mode === 'move-all'
    ? '拖动任意位置整体移动全部内容 · Ctrl+Z 撤销 · Esc 退出'
    : '滚轮缩放 · 拖动空白平移 · 双击管线添加折点 · Esc 取消';
  document.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('active', b.dataset.tool === mode && !placement));
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
    doc.labels.push({ id: uid('label'), nodeId: id, x: 0, y: (params.h || 2 * params.r) / 2 + 24,
      text: entry.label, size: 15, ha: 'center', color: '#111111', boxed: false });
    setSelection('node', id); placement = null; mode = 'select';
  });
}

function onPort(ref) {
  if (mode === 'connect') {
    if (!pendingPort) { pendingPort = ref; status('已选择起点，请点击终点端口或三通'); }
    else if (!eqRef(pendingPort, ref)) edit(() => {
      const id = uid('edge'); doc.edges.push({ id, source: pendingPort, target: ref, vertices: [], head: true, headAt: [.55], color: '#111111', width: 1.8, linestyle: 'solid' });
      setSelection('edge', id); pendingPort = null;
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
  });
}

function removeJunction(junction) {
  const incident = doc.edges.filter(edge =>
    [edge.source, edge.target].some(ref => ref.junctionId === junction.id));
  const incoming = incident.find(edge => edge.target.junctionId === junction.id);
  const outgoing = incident.find(edge => edge.source.junctionId === junction.id);
  if (incident.length === 2 && incoming && outgoing) {
    const merged = { ...clone(incoming), target: clone(outgoing.target),
      vertices: [...incoming.vertices, ...outgoing.vertices] };
    doc.edges = doc.edges.filter(edge => edge !== incoming && edge !== outgoing);
    doc.edges.push(merged);
  } else {
    doc.edges = doc.edges.filter(edge =>
      ![edge.source, edge.target].some(ref => ref.junctionId === junction.id));
  }
  doc.junctions = doc.junctions.filter(item => item.id !== junction.id);
  ports = ports.filter(ref => ref.junctionId !== junction.id);
  pendingPort = null;
  clearSelection();
}

function removeSelected() {
  const item = findSelected(); if (!item) return;
  edit(() => {
    const key = selection.kind;
    if (key === 'junction') { removeJunction(item); return; }
    if (key === 'node' || key === 'junction') {
      const prop = key === 'node' ? 'nodeId' : 'junctionId';
      doc.edges = doc.edges.filter(e => e.source[prop] !== item.id && e.target[prop] !== item.id);
      doc.labels = doc.labels.filter(l => l.nodeId !== item.id);
      ports = ports.filter(p => p[prop] !== item.id); pendingPort = null;
    }
    const collection = { node: 'nodes', label: 'labels', edge: 'edges', junction: 'junctions' }[key];
    doc[collection] = doc[collection].filter(o => o.id !== item.id); clearSelection();
  });
}
function copySelected() {
  const item = findSelected(); if (!item || !['node', 'label', 'junction'].includes(selection.kind)) return;
  edit(() => {
    const n = clone(item); n.id = uid(selection.kind); n.x += 20; n.y += 20;
    if (selection.kind === 'node') {
      doc.nodes.push(n);
      doc.labels.filter(l => l.nodeId === item.id).forEach(l => doc.labels.push({ ...clone(l), id: uid('label'), nodeId: n.id }));
    } else doc[selection.kind === 'label' ? 'labels' : 'junctions'].push(n);
    setSelection(selection.kind, n.id);
  });
}
function history(direction) {
  const from = direction === 'undo' ? undo : redo, to = direction === 'undo' ? redo : undo;
  if (!from.length) return;
  to.push(clone(doc)); doc = from.pop(); clearSelection(); ports = []; pendingPort = null;
  revision++; dirty = true; saveDraft(); render(); void refresh();
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob), a = html('a'); a.href = url; a.download = filename;
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
}
function filename(extension) { return (doc.title || 'rrplot').replace(/[\\/:*?"<>|]/g, '_') + '.' + extension; }

const actions = {
  new: async () => { if (await confirmReplace()) await replaceDocument({ schemaVersion: 1, title: '未命名图纸', page: { width: 1000, height: 700 }, nodes: [], edges: [], junctions: [], labels: [] }); },
  open: () => $('file-input').click(),
  save: async () => {
    const version = revision;
    const result = await api('resolve', { document: clone(doc) });
    download(new Blob([JSON.stringify(result.document, null, 2)], { type: 'application/json' }), filename('json'));
    if (version === revision && !drag) { dirty = false; clearDraft(); }
    render(); status('图纸 JSON 已下载');
  },
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
  'toggle-library': () => { document.body.classList.toggle('library-open'); document.body.classList.remove('properties-open'); },
  'toggle-properties': () => { document.body.classList.toggle('properties-open'); document.body.classList.remove('library-open'); },
  undo: () => history('undo'), redo: () => history('redo'), copy: copySelected, delete: removeSelected,
  fit, 'zoom-in': () => zoom(.85), 'zoom-out': () => zoom(1 / .85),
  'align-x': () => alignPorts('x'), 'align-y': () => alignPorts('y'),
  'clear-ports': () => { ports = []; pendingPort = null; render(); },
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
  mode = tool; placement = null; pendingPort = null;
  if (tool === 'move-all') { clearSelection(); ports = []; }
  render();
  status('工具：' + { select: '选择', 'move-all': '整体移动：按住左键拖动全部内容', connect: '连线：点击起点和终点端口', junction: '在空白处放三通，或选中管路后在属性中插入', text: '在画布点击放置文字' }[tool]);
}

svg.addEventListener('pointerdown', event => {
  if (!doc || event.button > 1) return;
  const p = world(event), hit = event.target.closest('[data-kind]');
  if (event.button === 1 || spaceDown) return startPan(event);
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
  if (!hit) { clearSelection(); renderInspector(); return startPan(event); }
  const kind = hit.dataset.kind, id = hit.dataset.id;
  if (kind === 'vertex' && event.altKey) {
    edit(() => doc.edges.find(e => e.id === id).vertices.splice(Number(hit.dataset.index), 1)); return;
  }
  const selectedKind = kind === 'vertex' ? 'edge' : kind;
  const additive = event.shiftKey && ['node', 'label', 'junction'].includes(selectedKind);
  const keepMulti = !additive && multiSelection.length > 1
    && multiSelection.some(ref => ref.kind === selectedKind && ref.id === id);
  if (!keepMulti) setSelection(selectedKind, id, additive);
  if (additive) { render(); return; }
  const item = findSelected();
  if (kind === 'edge') {
    // Keep the clicked path alive so the browser can deliver a double click.
    svg.querySelectorAll('.selected').forEach(element => element.classList.remove('selected'));
    hit.classList.add('selected');
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
  if (!drag) return;
  if (drag.kind === 'pan') {
    view.x = drag.origin.x - (event.clientX - drag.client[0]) * view.w / svg.clientWidth;
    view.y = drag.origin.y - (event.clientY - drag.client[1]) * view.h / svg.clientHeight;
    updateView(); return;
  }
  const p = world(event), delta = p.map((v, i) => v - drag.start[i]);
  if (!drag.moved && Math.hypot(...delta) < 1) return;
  drag.moved = true;
  if (drag.kind === 'all') {
    doc = translateDocument(drag.before, ...delta.map(snapped));
    renderCanvas(); return;
  }
  if (drag.kind === 'multi') {
    doc = clone(drag.before);
    const movedNodes = new Set(multiSelection.filter(ref => ref.kind === 'node').map(ref => ref.id));
    const dx = snapped(delta[0]), dy = snapped(delta[1]);
    for (const ref of multiSelection) {
      if (ref.kind === 'node') {
        const item = doc.nodes.find(node => node.id === ref.id);
        item.x += dx; item.y += dy;
      } else if (ref.kind === 'junction') {
        const item = doc.junctions.find(junction => junction.id === ref.id);
        item.x += dx; item.y += dy;
      } else if (ref.kind === 'label') {
        const item = doc.labels.find(label => label.id === ref.id);
        if (item.nodeId && movedNodes.has(item.nodeId)) continue;
        if (item.nodeId) {
          const node = doc.nodes.find(candidate => candidate.id === item.nodeId);
          const local = rotate(delta, -node.rotation);
          item.x += snapped(local[0]); item.y += snapped(local[1]);
        } else {
          item.x += dx; item.y += dy;
        }
      }
    }
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
function endDrag(event) {
  if (!drag) return;
  const current = drag; drag = null; svg.classList.remove('panning');
  if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  if (current.kind !== 'pan') finishEdit(current.before);
}
svg.addEventListener('pointerup', endDrag);
function cancelDrag() {
  const current = drag;
  if (drag?.before) doc = drag.before;
  drag = null; svg.classList.remove('panning');
  if (current && svg.hasPointerCapture(current.pointerId)) svg.releasePointerCapture(current.pointerId);
  render();
}
svg.addEventListener('pointercancel', cancelDrag);
svg.addEventListener('dblclick', event => {
  if (mode === 'move-all') return;
  const hit = event.target.closest('[data-kind="edge"]'); if (!hit) return;
  const edge = doc.edges.find(e => e.id === hit.dataset.id), points = edgePoints(edge), p = world(event);
  const index = nearestSegment(points, p);
  edit(() => { const vertices = points.slice(1, -1); vertices.splice(index, 0, p.map(snapped)); edge.vertices = vertices; setSelection('edge', edge.id); });
});
svg.addEventListener('wheel', event => { event.preventDefault(); if (doc) zoom(event.deltaY > 0 ? 1.1 : 1 / 1.1, world(event)); }, { passive: false });
svg.addEventListener('dragover', event => event.preventDefault());
svg.addEventListener('drop', event => { event.preventDefault(); const type = event.dataTransfer.getData('text/rrplot-part'); if (catalog.some(c => c.type === type)) addNode(type, world(event)); });

$('title').addEventListener('change', event => edit(() => { doc.title = event.target.value; }));
$('grid').addEventListener('change', renderCanvas);
$('file-input').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 5000000) throw new Error('图纸文件超过 5 MB');
    const next = JSON.parse(await file.text());
    if (await confirmReplace()) await replaceDocument(next);
  } catch (error) { message('无法打开图纸：' + error.message); }
  event.target.value = '';
});
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('keydown', async event => {
  if (event.target.matches('input,textarea,select') || document.querySelector('dialog[open]')) return;
  const modifier = event.ctrlKey || event.metaKey;
  if (event.code === 'Space') { spaceDown = true; event.preventDefault(); }
  if (event.key === 'Escape') { mode = 'select'; placement = null; pendingPort = null; ports = []; cancelDrag(); }
  if (drag) return;
  if (modifier && event.key.toLowerCase() === 'a') { event.preventDefault(); setTool('move-all'); }
  if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); removeSelected(); }
  if (modifier && event.key.toLowerCase() === 'z') { event.preventDefault(); history(event.shiftKey ? 'redo' : 'undo'); }
  if (modifier && event.key.toLowerCase() === 'y') { event.preventDefault(); history('redo'); }
  if (modifier && event.key.toLowerCase() === 'd') { event.preventDefault(); copySelected(); }
  if (modifier && event.key.toLowerCase() === 's') { event.preventDefault(); try { await actions.save(); } catch (error) { message(error.message); } }
});
window.addEventListener('keyup', event => { if (event.code === 'Space') spaceDown = false; });
window.addEventListener('blur', () => { spaceDown = false; });
new ResizeObserver(() => { if (doc) updateView(); }).observe(svg);

async function init() {
  try {
    const data = await Promise.all([api('catalog'), api('templates'), api('templates/evi_ftvi')]);
    [catalog] = data;
    for (const entry of catalog) {
      const b = html('button', undefined, 'part-button'); b.dataset.part = entry.type; b.draggable = true;
      b.append(html('span', entry.label.slice(0, 1), 'part-icon'));
      const name = html('span', entry.label); name.append(html('small', entry.type)); b.append(name);
      b.addEventListener('click', () => { placement = entry.type; mode = 'select'; pendingPort = null; document.body.classList.remove('library-open'); render(); status('在画布点击放置：' + entry.label); });
      b.addEventListener('dragstart', event => event.dataTransfer.setData('text/rrplot-part', entry.type));
      $('palette').append(b);
    }
    for (const template of data[1]) {
      const b = html('button', template.title);
      b.addEventListener('click', async () => { try { if (await confirmReplace()) await replaceDocument(await api('templates/' + template.id)); } catch (error) { message(error.message); } });
      $('templates').append(b);
    }
    await replaceDocument(data[2], true);
    try { if (JSON.parse(localStorage.getItem(DRAFT))?.document) $('draft-banner').hidden = false; } catch { /* Ignore invalid old drafts. */ }
  } catch (error) { message('无法连接本机服务。请运行 python server/run.py。' + error.message); status('服务未连接'); }
}
void init();
