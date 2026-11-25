import { connectedSelection, moveContents, editSelectedEdges, deleteSelection, copySelection, captureSelection, pasteFragment } from '../document.js';
import { projectOnRoute, detachNode, rotate, along, MOUNT_TYPES, nearestMount, mountNode, endpoint, transformedBox, layoutPage } from '../geometry.js';
import { uid, clone } from './config.js';

/** Selection edits, clipboard, layout and precise movement.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createSelectionController(state, commands) {
  function selectConnected() {
    if (!state.doc || document.querySelector('dialog[open]')) return;
    if (state.mode !== 'select' || state.placement || state.pendingPort || state.reconnect || state.drag || state.spaceDown || state.pageLayoutBusy)
      return commands.message('请先完成当前操作或按 Esc，再选择相连对象。');
    const next = connectedSelection(state.doc, state.multiSelection);
    if (!next.length) return commands.message('请先选择设备、管路、三通或附着标签。');
    const unchanged = JSON.stringify(next) === JSON.stringify(state.multiSelection);
    state.multiSelection = next;
    state.selection = next.find(ref => ref.kind === state.selection?.kind && ref.id === state.selection?.id) || next.at(-1);
    commands.render();
    const count = kind => next.filter(ref => ref.kind === kind).length;
    commands.status(`${unchanged ? '相连对象已全部选中' : '已选择相连对象'} · ${count('node')} 个设备 · ${count('edge')} 条管路 · ${count('junction')} 个三通 · ${count('label')} 个文字`);
  }

  function connectedSelectionButton(root) {
    const button = commands.inspectorButton(root, '选择相连对象', commands.selectConnected);
    button.title = '沿设备和三通的管路连接扩展选择，包含附着标签；同一设备的所有接管视为相连';
    button.disabled = state.mode !== 'select' || !!(state.placement || state.pendingPort || state.reconnect || state.drag || state.spaceDown || state.pageLayoutBusy);
    root.append(commands.html('p', '按设备级连接扩展，包含所有分支和附着标签；线条交叉不代表相连。', 'muted'));
  }

  function attachLabelToEdge(label, edgeId) {
    const p = commands.labelPosition(label);
    delete label.edgeId; delete label.at;
    if (edgeId) {
      const projected = projectOnRoute(commands.edgePoints(state.doc.edges.find(e => e.id === edgeId)), p);
      label.edgeId = edgeId; label.at = projected.at;
      [label.x, label.y] = p.map((v, i) => v - projected.point[i]);
    } else [label.x, label.y] = p;
  }

  function addStateLabel(edge) {
    if (!state.edgeLabelsSupported) return commands.message('管路状态点需要新版服务，请保存图纸后重启 start-web.cmd，再刷新页面。');
    if (state.doc.labels.length >= 2000) return commands.message('标签数量已达上限，请先删除部分标签。');
    const used = new Set(state.doc.labels.map(l => l.text));
    let number = 1; while (used.has(String(number))) number++;
    commands.edit(() => {
      const id = uid('label');
      state.doc.labels.push({ id, edgeId: edge.id, at: .5, x: 0, y: -16, text: String(number),
        size: 12, ha: 'center', boxed: true, color: '#111111' });
      commands.setSelection('label', id);
    });
  }

  function moveBusy() {
    return !['select', 'move-all'].includes(state.mode) || state.placement || state.pendingPort || state.reconnect || state.drag || state.spaceDown || state.pageLayoutBusy;
  }

  function showMoveDialog(scope) {
    if (!state.doc || commands.moveBusy() || document.querySelector('dialog[open]')) return;
    state.moveSession = { revision: state.revision, selection: clone(state.multiSelection) };
    commands.$('move-scope').value = scope;
    commands.$('move-x').value = '0'; commands.$('move-y').value = '0';
    commands.renderMoveState(); commands.$('move-dialog').showModal();
  }

  function renderMoveState() {
    if (!state.moveSession) return;
    const scope = commands.$('move-scope').value;
    const refs = scope === 'all' ? ['nodes', 'junctions', 'labels'].flatMap(name => state.doc[name])
      : state.moveSession.selection.filter(ref => ['node', 'junction', 'label'].includes(ref.kind));
    const valid = ['move-x', 'move-y'].every(id => commands.$(id).value.trim() !== ''
      && Number.isFinite(Number(commands.$(id).value)) && Math.abs(Number(commands.$(id).value)) <= 100000);
    const changed = ['move-x', 'move-y'].some(id => Number(commands.$(id).value) !== 0);
    commands.$('move-summary').textContent = scope === 'all' ? `整张图纸 · ${state.doc.nodes.length} 个设备 · ${state.doc.junctions.length} 个三通 · ${state.doc.labels.length} 个文字`
      : `已选可移动对象 ${refs.length} 项 · 管路按端点跟随`;
    commands.$('move-error').textContent = state.revision !== state.moveSession.revision ? '图纸已变化，请关闭后重新打开精确平移。'
      : !refs.length ? '没有可移动对象，请选择设备、三通或文字，或切换到整张图纸。'
      : !valid ? 'X、Y 位移必须为 -100000～100000 的数字。' : '';
    commands.$('move-apply').disabled = !refs.length || !valid || !changed || state.revision !== state.moveSession.revision || !!commands.moveBusy();
  }

  function applyMove(event) {
    event.preventDefault();
    commands.renderMoveState();
    if (!state.moveSession || !commands.$('move-dialog').open || commands.$('move-apply').disabled) return;
    try {
      const next = moveContents(state.doc, state.moveSession.selection, commands.$('move-scope').value,
        [Number(commands.$('move-x').value), Number(commands.$('move-y').value)]);
      if (JSON.stringify(next) === JSON.stringify(state.doc)) return;
      commands.edit(() => { state.doc = next; });
      commands.$('move-dialog').close();
      commands.status('已精确平移 · Ctrl+Z 可一次撤销');
    } catch (error) { commands.$('move-error').textContent = error.message; }
  }

  function pipeActionsBusy() {
    return state.mode !== 'select' || state.placement || state.pendingPort || state.reconnect || state.drag || state.spaceDown || state.pageLayoutBusy;
  }

  function renderPipeActions(root, count) {
    root.append(commands.html('div', `管路操作（已选 ${count} 条）`, 'section-label'));
    const buttons = commands.html('div', undefined, 'button-row'); root.append(buttons);
    for (const [action, caption] of [['reverse', '反转流向'], ['clear-vertices', '清除折点']]) {
      const button = commands.inspectorButton(buttons, caption, () => commands.operateSelectedPipes(action));
      button.dataset.pipeAction = action;
      button.disabled = !!commands.pipeActionsBusy() || (action === 'clear-vertices'
        && !state.doc.edges.some(edge => commands.selected('edge', edge.id) && edge.vertices.length));
    }
    const routing = commands.inspectorButton(buttons, '自动避障布线', () => commands.autoRoute('selection'));
    routing.disabled = !!commands.pipeActionsBusy();
    routing.title = '重新计算所选管路折点，绕开设备并保持端口和三通连接；Ctrl+Z 撤销';
    root.append(commands.html('p', '仅处理直接选中的管路。反转保留走线及状态点位置；清除折点恢复基础走线。避障布线替换手动折点并绕开设备，状态点和挂接阀件沿新路径跟随；每次操作可一次撤销。', 'muted'));
  }

  function operateSelectedPipes(action) {
    if (!state.doc || commands.pipeActionsBusy() || document.querySelector('dialog[open]')) return;
    const edges = state.doc.edges.filter(edge => commands.selected('edge', edge.id));
    if (!edges.length) return;
    try {
      const routes = new Map(action === 'reverse' ? edges.map(edge => [edge.id, commands.edgePoints(edge)]) : []);
      const next = editSelectedEdges(state.doc, state.multiSelection, action, routes);
      const changed = edges.filter(edge => JSON.stringify(edge) !== JSON.stringify(next.edges.find(e => e.id === edge.id))).length;
      if (!changed) return commands.status('所选管路无需修改');
      commands.edit(() => { state.doc = next; });
      commands.status(`${action === 'reverse' ? '已反转流向' : '已清除折点'} · ${changed} 条管路 · Ctrl+Z 撤销`);
    } catch (error) { commands.message(error.message); }
  }

  function coordinateFields(parent, item, prefix = '') {
    const pair = commands.html('div', undefined, 'field-pair'); parent.append(pair);
    for (const axis of ['x', 'y']) commands.field(pair, `${prefix}${axis.toUpperCase()}`, item[axis], v => { item[axis] = v; }, { min: -100000, max: 100000 });
  }

  function layoutRefs() {
    return state.multiSelection.filter(ref => ['node', 'junction', 'label'].includes(ref.kind))
      .map(ref => ({ ref, item: state.doc[{ node: 'nodes', junction: 'junctions', label: 'labels' }[ref.kind]]
        .find(item => item.id === ref.id) })).filter(entry => entry.item);
  }

  function layoutBox(entry) {
    const { ref, item } = entry;
    if (ref.kind === 'node') {
      const geometry = state.geometries.get(item.id), rotated = item.rotation % 180 !== 0;
      if (!geometry) return { x: item.x, y: item.y, left: item.x, right: item.x, top: item.y, bottom: item.y, width: 0, height: 0 };
      const width = rotated ? geometry.height : geometry.width, height = rotated ? geometry.width : geometry.height;
      return { x: item.x, y: item.y, left: item.x - width / 2, right: item.x + width / 2,
        top: item.y - height / 2, bottom: item.y + height / 2, width, height };
    }
    const [x, y] = ref.kind === 'label' ? commands.labelPosition(item) : [item.x, item.y];
    return { x, y, left: x, right: x, top: y, bottom: y, width: 0, height: 0 };
  }

  function moveLayoutRef(entry, x, y) {
    const { ref, item } = entry;
    if (ref.kind === 'node' && item.mount) detachNode(item, commands.currentNodes().find(n => n.id === item.id));
    if (ref.kind === 'node' || ref.kind === 'junction') { item.x = +x.toFixed(4); item.y = +y.toFixed(4); return; }
    if (item.nodeId) {
      const node = commands.currentNodes().find(candidate => candidate.id === item.nodeId)
        || state.doc.nodes.find(candidate => candidate.id === item.nodeId);
      const local = rotate([x - node.x, y - node.y], -node.rotation);
      item.x = +local[0].toFixed(4); item.y = +local[1].toFixed(4);
    } else if (item.edgeId) {
      const anchor = along(commands.edgePoints(state.doc.edges.find(e => e.id === item.edgeId)), item.at).point;
      item.x = +(x - anchor[0]).toFixed(4); item.y = +(y - anchor[1]).toFixed(4);
    } else { item.x = +x.toFixed(4); item.y = +y.toFixed(4); }
  }

  function batchLayout(action) {
    const entries = commands.layoutRefs();
    if (entries.length < 2) return commands.message('请至少多选两个设备、三通或文字。');
    const boxes = entries.map(commands.layoutBox), before = clone(state.doc);
    const minLeft = Math.min(...boxes.map(box => box.left)), maxRight = Math.max(...boxes.map(box => box.right));
    const minTop = Math.min(...boxes.map(box => box.top)), maxBottom = Math.max(...boxes.map(box => box.bottom));
    const moves = [];
    if (action === 'distribute-x' || action === 'distribute-y') {
      if (entries.length < 3) return commands.message('均匀分布至少需要三个对象。');
      const axis = action === 'distribute-x' ? 'x' : 'y';
      const order = entries.map((entry, index) => ({ entry, box: boxes[index] })).sort((a, b) => a.box[axis] - b.box[axis]);
      const first = order[0].box[axis], step = (order.at(-1).box[axis] - first) / (order.length - 1);
      order.forEach(({ entry, box }, index) => moves.push({ entry,
        x: axis === 'x' ? first + step * index : box.x,
        y: axis === 'y' ? first + step * index : box.y }));
    } else {
      const target = { 'align-left': minLeft, 'align-center-x': (minLeft + maxRight) / 2, 'align-right': maxRight,
        'align-top': minTop, 'align-center-y': (minTop + maxBottom) / 2, 'align-bottom': maxBottom }[action];
      entries.forEach((entry, index) => {
        const box = boxes[index];
        const x = action === 'align-left' ? target + box.width / 2 : action === 'align-right' ? target - box.width / 2
          : action === 'align-center-x' ? target : box.x;
        const y = action === 'align-top' ? target + box.height / 2 : action === 'align-bottom' ? target - box.height / 2
          : action === 'align-center-y' ? target : box.y;
        moves.push({ entry, x, y });
      });
    }
    // Place parents first so attached labels use the final node/pipe geometry.
    const parents = moves.filter(move => move.entry.ref.kind !== 'label');
    const labels = moves.filter(move => move.entry.ref.kind === 'label');
    for (const { entry, x, y } of [...parents, ...labels]) commands.moveLayoutRef(entry, x, y);
    commands.finishEdit(before);
  }

  function addNode(type, position) {
    if (state.doc.nodes.length >= 2000 || state.doc.labels.length >= 2000)
      return commands.message('添加设备会超过对象上限（设备、标签各最多 2000 项），请先减少对象。');
    state.mountPreview = null;
    const entry = state.catalog.find(c => c.type === type), id = uid('node');
    commands.edit(() => {
      const params = Object.fromEntries(Object.entries(entry.fields).map(([k, v]) => [k, v.default]));
      state.doc.nodes.push({ id, type, title: entry.label, x: commands.snapped(position[0]), y: commands.snapped(position[1]), params, rotation: 0 });
      const node = state.doc.nodes.at(-1);
      if (state.pipeMountsSupported && MOUNT_TYPES.includes(type)) {
        const target = nearestMount(state.doc, node, commands.currentNodes(), position, commands.screenMatrix());
        if (target) { mountNode(state.doc, id, target.edgeId, target.at); state.ports = []; }
      }
      state.doc.labels.push({ id: uid('label'), nodeId: id, x: 0, y: (params.h || 2 * params.r) / 2 + 24 + (type === 'four_way_valve' && params.mark ? 30 : 0),
        text: entry.label, size: 15, ha: 'center', color: '#111111', boxed: false });
      commands.setSelection('node', id); state.placement = null; state.mode = 'select';
    });
  }

  function alignPorts(axis) {
    if (state.ports.length !== 2) return;
    const [a, b] = state.ports.map(p => endpoint(p, commands.currentNodes(), state.doc.junctions));
    const first = state.ports[0].nodeId || state.ports[0].junctionId;
    const second = state.ports[1].nodeId || state.ports[1].junctionId;
    if (first === second) return commands.message('请选择两个不同设备或三通上的端口。');
    commands.edit(() => {
      const ref = state.ports[1], n = ref.nodeId ? state.doc.nodes.find(n => n.id === ref.nodeId) : state.doc.junctions.find(j => j.id === ref.junctionId);
      n[axis] = +(n[axis] + a.point[axis === 'x' ? 0 : 1] - b.point[axis === 'x' ? 0 : 1]).toFixed(4);
    });
  }

  function removeSelected() {
    if (state.reconnect) return commands.message('请先完成重接，或按 Esc 取消。');
    if (!state.multiSelection.length) return;
    try {
      const routes = new Map();
      for (const edge of state.doc.edges) {
        try { routes.set(edge.id, commands.edgePoints(edge)); } catch { /* Newly placed geometry may still be loading. */ }
      }
      const next = deleteSelection(state.doc, state.multiSelection, routes);
      commands.edit(() => {
        state.doc = next;
        state.ports = state.ports.filter(ref => ref.nodeId ? state.doc.nodes.some(n => n.id === ref.nodeId)
          : state.doc.junctions.some(j => j.id === ref.junctionId));
        state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; commands.clearSelection();
      });
    } catch (error) { commands.message(error.message); }
  }

  function copySelected() {
    if (state.reconnect) return commands.message('请先完成重接，或按 Esc 取消。');
    if (!state.multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind))) return;
    try {
      const result = copySelection(state.doc, state.multiSelection, uid);
      for (const copy of result.document.nodes.slice(state.doc.nodes.length)) {
        const original = state.doc.nodes.find(n => n.type === copy.type && JSON.stringify(n.params) === JSON.stringify(copy.params));
        const geometry = original && state.geometries.get(original.id);
        if (geometry) state.geometries.set(copy.id, geometry);
      }
      commands.edit(() => {
        state.doc = result.document; state.multiSelection = result.selection; state.selection = state.multiSelection.at(-1) || null;
        state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.mode = 'select'; state.placement = null;
      });
    } catch (error) { commands.message(error.message); }
  }

  function clipboardReady() {
    if (!state.doc) return false;
    if (state.drag || state.reconnect || state.pendingPort || state.placement || state.mode !== 'select') {
      commands.message('请先完成当前操作或切回选择模式，再复制粘贴。'); return false;
    }
    return true;
  }

  function showPageLayout() {
    if (state.drag || state.reconnect || state.pendingPort) return commands.message('请先完成当前连接或拖动，或按 Esc 取消，再进行页面排版。');
    state.mode = 'select'; state.placement = null; state.ports = []; state.previewTarget = null; commands.clearSelection(); commands.render();
    document.body.classList.remove('library-open'); document.body.classList.add('properties-open');
    document.querySelector('.properties').scrollTop = 0;
    commands.status('页面排版 · 内容居中或按内容调整页面尺寸');
  }

  function pageContentBoxes(resolved, refs = null) {
    const includes = (kind, id) => !refs || refs.has(kind + ':' + id);
    const boxes = resolved.nodes.filter(n => includes('node', n.id))
      .map(n => transformedBox(n.geometry.box, [n.x, n.y], n.rotation));
    for (const j of state.doc.junctions) if (includes('junction', j.id)) boxes.push([j.x - 4, j.y - 4, 8, 8]);
    // Measure at the origin and a fixed scale: SVG font hinting can otherwise
    // change text bounds as fitting changes the canvas zoom or label position.
    const measurement = commands.shape('svg', { width: 100, height: 100, viewBox: '0 0 100 100',
      style: 'position:fixed;left:-10000px;top:-10000px;visibility:hidden;pointer-events:none',
      'aria-hidden': 'true' }, document.body);
    try {
      const labels = new Map(resolved.labels.map(label => [label.id, label]));
      for (const element of state.svg.querySelectorAll('.diagram-label')) {
        if (!includes('label', element.dataset.id)) continue;
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
      if (!includes('edge', edge.id)) continue;
      const xs = edge.points.map(p => p[0]), ys = edge.points.map(p => p[1]);
      const x = Math.min(...xs), y = Math.min(...ys), pad = Math.max(edge.width * 100 / 144, edge.head ? 4 : 0);
      boxes.push([x - pad, y - pad, Math.max(...xs) - x + pad * 2, Math.max(...ys) - y + pad * 2]);
    }
    return boxes;
  }

  async function applyPageLayout(action) {
    if (state.pageLayoutBusy) return;
    if (state.drag || state.reconnect || state.pendingPort || state.placement || state.mode !== 'select')
      return commands.message('请先完成当前编辑操作，再进行页面排版。');
    const input = commands.$('page-margin');
    if (action === 'fit' && input && !input.checkValidity()) { input.reportValidity(); return; }
    const version = state.revision, before = clone(state.doc), margin = state.pageMargin;
    state.pageLayoutBusy = true; commands.message(''); commands.renderInspector(); commands.status('正在计算整张图纸的内容范围…');
    try {
      const resolved = await commands.api('resolve', { document: before });
      if (version !== state.revision || state.drag || state.reconnect || state.pendingPort || state.placement || state.mode !== 'select') {
        commands.status('图纸或操作已变化，请重新进行页面排版'); return;
      }
      state.geometries = new Map(resolved.nodes.map(n => [n.id, n.geometry])); state.fontFamily = resolved.fontFamily; commands.renderCanvas();
      const boxes = commands.pageContentBoxes(resolved);
      const next = layoutPage(state.doc, boxes, action, margin);
      const changed = JSON.stringify(next) !== JSON.stringify(state.doc);
      commands.edit(() => { state.doc = next; }); commands.fit();
      commands.status(changed ? (action === 'fit' ? '页面已适配内容' : '内容已在页面中居中') + ' · Ctrl+Z 撤销' : '内容已符合当前排版设置');
    } catch (error) { commands.message(error.message); commands.status('未应用页面排版'); }
    finally {
      state.pageLayoutBusy = false;
      commands.updateStyleButton();
      const empty = !['nodes', 'edges', 'junctions', 'labels'].some(name => state.doc[name].length);
      document.querySelectorAll('[data-page-layout]').forEach(button => { button.disabled = empty; });
      if (commands.$('page-margin')) commands.$('page-margin').disabled = false;
    }
  }

  function copyToClipboard() {
    if (!commands.clipboardReady()) return;
    if (!state.multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind)))
      return commands.message('请先选择设备、三通或文字；组内管路会随设备一起复制。');
    try {
      const positions = new Map(state.multiSelection.filter(ref => ref.kind === 'label')
        .map(ref => { const label = state.doc.labels.find(l => l.id === ref.id); return [ref.id, commands.labelPosition(label)]; }));
      const fragment = captureSelection(state.doc, state.multiSelection, positions);
      const geometry = new Map(fragment.nodes.map(node => {
        const value = state.geometries.get(node.id);
        if (!value) throw new Error('图元正在更新，请稍后再复制。');
        return [node.id, clone(value)];
      }));
      state.editorClipboard = { fragment, geometry }; state.clipboardPastes = 0;
      commands.render(); commands.status(`已复制 ${fragment.nodes.length} 台设备、${fragment.junctions.length} 个三通、${fragment.edges.length} 条管路、${fragment.labels.length} 个标签 · 可切换图纸后 Ctrl+V 粘贴`);
    } catch (error) { commands.message(error.message); }
  }

  function pasteClipboard() {
    if (!commands.clipboardReady()) return;
    if (!state.editorClipboard) return commands.message('编辑器剪贴板为空，请先选择对象并按 Ctrl+C。');
    try {
      const offset = 20 * (state.clipboardPastes + 1);
      const result = pasteFragment(state.doc, state.editorClipboard.fragment, uid, [offset, offset]);
      const originals = state.editorClipboard.fragment.selection.filter(ref => ref.kind === 'node');
      result.selection.filter(ref => ref.kind === 'node').forEach((ref, index) => {
        state.geometries.set(ref.id, state.editorClipboard.geometry.get(originals[index].id));
      });
      commands.edit(() => {
        state.doc = result.document; state.multiSelection = result.selection; state.selection = state.multiSelection.at(-1) || null;
        state.ports = []; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null;
      });
      state.clipboardPastes++;
      document.body.classList.remove('library-open');
      state.svg.focus({ preventScroll: true });
      commands.status('已粘贴 · 可拖动整组调整位置 · Ctrl+Z 撤销');
    } catch (error) { commands.message(error.message); }
  }

  function bindSelectionEvents() {
    commands.$('move-scope').addEventListener('change', commands.renderMoveState);
    for (const id of ['move-x', 'move-y']) commands.$(id).addEventListener('input', commands.renderMoveState);
    commands.$('move-form').addEventListener('submit', commands.applyMove);
    commands.$('move-dialog').addEventListener('close', () => { if (!commands.$('move-dialog').open) state.moveSession = null; });
  }

  return { selectConnected, connectedSelectionButton, attachLabelToEdge, addStateLabel, moveBusy, showMoveDialog, renderMoveState, applyMove, pipeActionsBusy, renderPipeActions, operateSelectedPipes, coordinateFields, layoutRefs, layoutBox, moveLayoutRef, batchLayout, addNode, alignPorts, removeSelected, copySelected, clipboardReady, showPageLayout, pageContentBoxes, applyPageLayout, copyToClipboard, pasteClipboard, bindSelectionEvents };
}
