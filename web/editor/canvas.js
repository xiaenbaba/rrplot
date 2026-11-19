import { createCanvasRenderer } from '../canvas.js';
import { endpoint, route, along, glyphRotation, editableSegments } from '../geometry.js';
import { BENCHMARK } from './config.js';

/** SVG scene and transient overlays; delegates group reuse to canvas.js.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createCanvasController(state, commands) {
  // Only current-scene glyph definitions are kept; legacy responses without a
  // glyphId use their image data and bounds as the identity.
  let glyphIds = new Map(), nextGlyphId = 0;
  let nodeTemplates = new Map();
  function renderMountPreview() {
    let marker = state.svg.querySelector('.mount-target');
    if (!state.mountPreview) { marker?.setAttribute('visibility', 'hidden'); return; }
    if (!marker) marker = commands.shape('circle', { r: 11, class: 'mount-target',
      'pointer-events': 'none', 'vector-effect': 'non-scaling-stroke' });
    else if (state.canvasPass) state.canvasRenderer.place(marker);
    marker.setAttribute('cx', state.mountPreview.point[0]);
    marker.setAttribute('cy', state.mountPreview.point[1]);
    marker.setAttribute('visibility', 'visible');
  }

  function renderCanvas() {
    if (!state.doc) return;
    const metrics = BENCHMARK ? {} : null;
    let last = metrics ? performance.now() : 0;
    const measured = key => { if (metrics) { const now = performance.now(); metrics[key] = now - last; last = now; } };
    if (state.viewportWidth === null) state.viewportWidth = state.svg.clientWidth;
    commands.renderHint();
    const connection = commands.renderConnectionFeedback();
    const junction = commands.renderJunctionFeedback();
    const previewClass = 'connection-preview' + (connection?.error ? ' invalid' : '');
    state.canvasRenderer ||= createCanvasRenderer(state.svg);
    state.canvasRenderer.begin(); state.canvasPass = true;
    const labelBackgrounds = [];
    const nextTemplates = new Map();
    const rememberTemplate = (key, group) => {
      if (nextTemplates.size >= 64 || !group.cloneNode) return;
      nextTemplates.set(key, [...group.childNodes].map(element => ({
        element: element.cloneNode(true), portId: JSON.parse(element.getAttribute('data-ref') || 'null')?.portId
      })));
    };
    try {
      state.svg.classList.toggle('connecting', state.mode === 'connect' || state.mode === 'reconnect');
      state.svg.classList.toggle('moving-all', state.mode === 'move-all');
      state.svg.classList.toggle('box-selecting', state.mode === 'box-select' || state.drag?.kind === 'box');
      state.svg.classList.toggle('placing', !!state.placement || ['junction', 'text'].includes(state.mode));
      const definitions = state.canvasRenderer.group('aux:defs', 'defs', {}, 'grid-v1');
      if (definitions.changed) {
        const pattern = commands.shape('pattern', { id: 'grid-pattern', width: 10, height: 10, patternUnits: 'userSpaceOnUse' }, definitions.element);
        commands.shape('path', { d: 'M 10 0 L 0 0 0 10', fill: 'none', stroke: '#c6d6d1', 'stroke-width': .65 }, pattern);
      }
      state.canvasRenderer.group('aux:page', 'rect', { x: 0, y: 0, width: state.doc.page.width, height: state.doc.page.height, fill: '#fff', class: 'page' }, 'page-v1');
      state.canvasRenderer.group('aux:grid', 'rect', { width: state.doc.page.width, height: state.doc.page.height,
        fill: 'url(#grid-pattern)', opacity: .65, 'pointer-events': 'none', visibility: commands.$('grid').checked ? 'visible' : 'hidden' }, 'grid-v1');
      const nodes = commands.currentNodes();
      const sceneGlyphs = new Map();
      for (const node of nodes) {
        const geometry = node.geometry;
        const key = JSON.stringify([geometry.glyphId || geometry.image, geometry.box]);
        if (sceneGlyphs.has(key)) continue;
        const id = glyphIds.get(key) || 'rrplot-glyph-' + ++nextGlyphId;
        sceneGlyphs.set(key, id);
        const definition = state.canvasRenderer.group('glyph:' + id, 'defs', {}, key);
        if (definition.changed) {
          const [x, y, width, height] = geometry.box;
          commands.shape('image', { id, x, y, width, height, href: geometry.image }, definition.element);
        }
      }
      glyphIds = sceneGlyphs;
      const nodeMap = new Map(nodes.map(n => [n.id, n]));
      const junctionMap = new Map(state.doc.junctions.map(j => [j.id, j]));
      const edgeMap = new Map(state.doc.edges.map(e => [e.id, e]));
      const edgeRoutes = new Map();
      const resolveEndpoint = ref => endpoint(ref, nodeMap, junctionMap);
      measured('setupMs');
      for (const edge of state.doc.edges) {
        let points;
        try { points = route(resolveEndpoint(edge.source), resolveEndpoint(edge.target), edge.vertices); } catch { continue; }
        edgeRoutes.set(edge.id, points);
        const cached = state.canvasRenderer.group('edge:' + edge.id, 'g', { class: 'edge' + (commands.selected('edge', edge.id) ? ' selected' : '')
          + (junction?.edgeId === edge.id ? ' junction-candidate' + (junction.error ? ' invalid' : '') : '')
          + (connection?.pipeId === edge.id ? ' connection-candidate' + (connection.error ? ' invalid' : '') : '')
          + (state.reconnect?.edgeId === edge.id ? ' reconnecting-edge' : ''), 'data-kind': 'edge', 'data-id': edge.id },
          JSON.stringify([points, edge.color, edge.width, edge.linestyle, edge.head, edge.headAt]));
        if (!cached.changed) continue;
        const g = cached.element;
        const p = points.map(p => p.join(',')).join(' ');
        commands.shape('polyline', { points: p, class: 'edge-hit' }, g);
        commands.shape('polyline', { points: p, class: 'edge-visible', fill: 'none', stroke: edge.color,
          'stroke-width': edge.width * 100 / 72, 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
          'stroke-dasharray': edge.linestyle === 'dashed' ? '7 5' : undefined }, g);
        if (edge.head) for (const at of edge.headAt || [.55]) {
          const info = along(points, at); if (info.length < 1) continue;
          const half = Math.min(20, info.length / 2), direction = info.direction;
          const center = info.point.map((v, i) => Math.max(Math.min(info.start[i], info.end[i]) + (direction[i] ? half : 0), Math.min(Math.max(info.start[i], info.end[i]) - (direction[i] ? half : 0), v)));
          const tip = center.map((v, i) => v + direction[i] * (half - 2));
          const base = tip.map((v, i) => v - direction[i] * 7);
          commands.shape('polygon', { points: [tip, [base[0] - direction[1] * 2.7, base[1] + direction[0] * 2.7],
            [base[0] + direction[1] * 2.7, base[1] - direction[0] * 2.7]].map(p => p.join(',')).join(' '), fill: edge.color, 'pointer-events': 'none' }, g);
        }
      }
      measured('edgesMs');
      if (state.mode === 'connect' && state.pendingPort && state.previewTarget) {
        try {
          const start = endpoint(state.pendingPort, nodes, state.doc.junctions);
          const points = route(start, state.previewTarget, state.connectionVertices);
          commands.shape('polyline', { points: points.map(p => p.join(',')).join(' '), class: previewClass });
        } catch { /* The source may have been removed while connecting. */ }
      }
      if (state.mode === 'reconnect' && state.reconnect && state.previewTarget) {
        try {
          const edge = state.doc.edges.find(e => e.id === state.reconnect.edgeId);
          const source = state.reconnect.side === 'source' ? state.previewTarget : endpoint(edge.source, nodes, state.doc.junctions);
          const target = state.reconnect.side === 'target' ? state.previewTarget : endpoint(edge.target, nodes, state.doc.junctions);
          const points = route(source, target, edge.vertices);
          commands.shape('polyline', { points: points.map(p => p.join(',')).join(' '), class: previewClass });
        } catch { /* Geometry may still be loading. */ }
      }
      for (const n of nodes) {
        const chosenPorts = new Set([...state.ports, state.pendingPort].filter(ref => ref?.nodeId === n.id).map(ref => ref.portId));
        const contentKey = JSON.stringify([n.title, n.geometry.glyphId || n.geometry.image, n.geometry.box,
          n.geometry.ports, !!n.mount, n.params, glyphRotation(n), [...chosenPorts]]);
        const template = nextTemplates.get(contentKey) || nodeTemplates.get(contentKey);
        if (template && nextTemplates.size < 64) nextTemplates.set(contentKey, template);
        const cached = state.canvasRenderer.group('node:' + n.id, 'g', { class: 'node' + (commands.selected('node', n.id) ? ' selected' : ''),
          'data-kind': 'node', 'data-id': n.id, transform: `translate(${n.x} ${n.y}) rotate(${n.rotation})` },
          contentKey);
        if (!cached.changed) continue;
        const g = cached.element;
        if (template && g.cloneNode) {
          for (const { element, portId } of template) {
            const child = element.cloneNode(true);
            if (portId !== undefined) child.setAttribute('data-ref', JSON.stringify({ nodeId: n.id, portId }));
            g.append(child);
          }
          continue;
        }
        const [x, y, w, h] = n.geometry.box;
        commands.shape('title', {}, g).textContent = n.title;
        if (n.mount) commands.shape('rect', { x: -(n.params.w || 2*n.params.r)/2, y: -(n.params.h || 2*n.params.r)/2,
          width: n.params.w || 2*n.params.r, height: n.params.h || 2*n.params.r, fill: '#fff', 'pointer-events': 'none' }, g);
        const glyphId = glyphIds.get(JSON.stringify([n.geometry.glyphId || n.geometry.image, n.geometry.box]));
        commands.shape('use', { href: '#' + glyphId, class: 'node-image',
          transform: `rotate(${glyphRotation(n)})` }, g);
        commands.shape('rect', { x: x - 3, y: y - 3, width: w + 6, height: h + 6, rx: 2, class: 'node-hit' }, g);
        const seen = new Set();
        if (n.mount) { rememberTemplate(contentKey, g); continue; }
        for (const [id, p] of Object.entries(n.geometry.ports)) {
          const key = p.point.join(','); if (seen.has(key)) continue; seen.add(key);
          const ref = { nodeId: n.id, portId: id };
          const chosen = chosenPorts.has(id);
          commands.shape('circle', { cx: p.point[0], cy: p.point[1], r: 10,
            class: 'port-hit', 'data-kind': 'port', 'data-ref': JSON.stringify(ref) }, g);
          const circle = commands.shape('circle', { cx: p.point[0], cy: p.point[1], r: 4.5,
            class: 'port' + (chosen ? ' chosen' : ''), 'data-kind': 'port', 'data-ref': JSON.stringify(ref) }, g);
          commands.shape('title', {}, circle).textContent = id;
        }
        rememberTemplate(contentKey, g);
      }
      nodeTemplates = nextTemplates;
      measured('nodesMs');
      if (state.mountPreview) commands.renderMountPreview();
      for (const j of state.doc.junctions) {
        const cached = state.canvasRenderer.group('junction:' + j.id, 'g', { class: 'junction' + (commands.selected('junction', j.id) ? ' selected' : ''),
          'data-kind': 'junction', 'data-id': j.id }, JSON.stringify([j.x, j.y]));
        if (!cached.changed) continue;
        const g = cached.element;
        commands.shape('circle', { cx: j.x, cy: j.y, r: 10, class: 'junction-hit' }, g);
        const c = commands.shape('circle', { cx: j.x, cy: j.y, r: 4, class: 'junction-dot', 'pointer-events': 'none' }, g);
        commands.shape('title', {}, c).textContent = '三通';
      }
      for (const label of state.doc.labels) {
        const [x, y] = commands.labelPosition(label, { nodes: nodeMap, junctions: junctionMap, edges: edgeMap, routes: edgeRoutes });
        const cached = state.canvasRenderer.group('label:' + label.id, 'g', { class: 'diagram-label' + (commands.selected('label', label.id) ? ' selected' : ''),
          'data-kind': 'label', 'data-id': label.id }, JSON.stringify([label, x, y, state.fontFamily, commands.selected('label', label.id)]));
        if (!cached.changed) continue;
        const g = cached.element;
        const text = commands.shape('text', { x, y, fill: label.color, 'font-family': state.fontFamily,
          'font-size': label.size * 100 / 72, 'text-anchor': { left: 'start', center: 'middle', right: 'end' }[label.ha],
          'dominant-baseline': 'central' }, g);
        const lines = label.text.split('\n');
        lines.forEach((line, i) => commands.shape('tspan', { x, dy: i ? '1.2em' : `${-(lines.length - 1) * .6}em` }, text).textContent = line);
        if (label.boxed || commands.selected('label', label.id)) {
          labelBackgrounds.push({ g, text, boxed: label.boxed });
        }
      }
      measured('labelsMs');
      if (state.mode === 'connect' && state.pendingPort) state.connectionVertices.forEach(([x, y], index) => {
        const g = commands.shape('g', { 'data-kind': 'connection-vertex', 'data-index': index,
          'data-point': JSON.stringify([x, y]), class: 'connection-waypoint-handle' });
        commands.shape('rect', { x: x - 10, y: y - 10, width: 20, height: 20, fill: 'transparent' }, g);
        const marker = commands.shape('rect', { x: x - 4, y: y - 4, width: 8, height: 8, rx: 1,
          class: 'connection-waypoint', 'vector-effect': 'non-scaling-stroke' }, g);
        commands.shape('title', {}, marker).textContent = '拖动调整临时折点；Alt+点击删除；Esc 取消本次拖动';
      });
      if (connection) commands.shape('circle', { cx: connection.point[0], cy: connection.point[1], r: 9,
        class: 'connection-target' + (connection.error ? ' invalid' : ''), 'vector-effect': 'non-scaling-stroke' });
      commands.renderVertices();
      if (junction) {
        const attrs = { cx: junction.point[0], cy: junction.point[1], 'pointer-events': 'none' };
        commands.shape('circle', { ...attrs, r: 9, class: 'junction-preview' + (junction.error ? ' invalid' : ''),
          'vector-effect': 'non-scaling-stroke' });
        commands.shape('circle', { ...attrs, r: 3, class: 'junction-preview-dot' + (junction.error ? ' invalid' : '') });
      }
      if (state.drag?.kind === 'box' && state.drag.moved) {
        const [x, y] = state.drag.start, [ex, ey] = state.drag.point;
        commands.shape('rect', { x: Math.min(x, ex), y: Math.min(y, ey), width: Math.abs(ex - x),
          height: Math.abs(ey - y), class: 'selection-marquee' });
      }
    } finally { state.canvasRenderer.end(); state.canvasPass = false; }
    // SVG text bounds require attached text. Read all bounds before adding any
    // backgrounds, avoiding one forced layout for each boxed label in a new scene.
    const boxes = labelBackgrounds.map(({ text }) => text.getBBox());
    labelBackgrounds.forEach(({ g, text, boxed }, index) => {
      const b = boxes[index];
      const bg = commands.shape('rect', { x: b.x - 2, y: b.y - 2, width: b.width + 4, height: b.height + 4,
        fill: boxed ? '#fff' : '#d6eee4', opacity: boxed ? 1 : .55 }, g);
      g.insertBefore(bg, text);
    });
    measured('overlaysCommitMs');
    commands.updateView({ measure: false });
    measured('viewLayoutMs');
    if (metrics) state.canvasMetrics = metrics;
  }

  function renderVertices() {
    state.svg.querySelectorAll('[data-kind="vertex"], [data-kind="segment"], [data-kind="endpoint"]').forEach(element => element.remove());
    if (state.mode === 'reconnect' || state.multiSelection.length > 1) return;
    const e = state.selection?.kind === 'edge' && commands.findSelected();
    if (e && state.mode === 'select') {
      const nodes = commands.currentNodes();
      const source = endpoint(e.source, nodes, state.doc.junctions), target = endpoint(e.target, nodes, state.doc.junctions);
      for (const { index, axis, point: [x, y] } of editableSegments(source, target, e.vertices)) {
        const handle = commands.shape('rect', { x: x - (axis ? 9 : 4), y: y - (axis ? 4 : 9),
          width: axis ? 18 : 8, height: axis ? 8 : 18, rx: 3,
          class: 'segment-handle ' + (axis ? 'horizontal' : 'vertical'),
          'data-kind': 'segment', 'data-id': e.id, 'data-index': index });
        commands.shape('title', {}, handle).textContent = axis ? '上下拖动水平线段' : '左右拖动垂直线段';
      }
    }
    if (e) e.vertices.forEach((v, i) => {
      const c = commands.shape('rect', { x: v[0] - 4, y: v[1] - 4, width: 8, height: 8,
        class: 'vertex', 'data-kind': 'vertex', 'data-id': e.id, 'data-index': i });
      commands.shape('title', {}, c).textContent = '拖动折点；Alt+点击删除';
    });
    if (e && state.mode === 'select' && !state.placement) {
      const nodes = commands.currentNodes();
      for (const side of ['source', 'target']) {
        const { point: [x, y] } = endpoint(e[side], nodes, state.doc.junctions);
        const handle = commands.shape('circle', { cx: x, cy: y, r: 7, class: 'endpoint-handle',
          'data-kind': 'endpoint', 'data-id': e.id, 'data-side': side,
          'vector-effect': 'non-scaling-stroke' });
        commands.shape('title', {}, handle).textContent = (side === 'source' ? '重接起点' : '重接终点') + '：点击后选择端口、三通，或 Shift+点击其他管路';
      }
    }
  }

  function renderHint() {
    commands.renderConnectionTools();
    document.querySelector('.canvas-hint').textContent = state.mode === 'move-all'
      ? '拖动任意位置整体移动全部内容 · Ctrl+Z 撤销 · Esc 退出'
      : state.mode === 'box-select' ? '拖出矩形完整框住对象 · Shift 追加选择 · Esc 取消'
      : state.mode === 'reconnect' ? '点击端口或三通，或 Shift+点击其他管路完成重接 · Esc 取消'
      : state.mode === 'connect' ? (state.pendingPort ? `起点已选 · Alt+点击空白加折点（${state.connectionVertices.length}）· Backspace 回退 · 点击端口或三通，或 Shift+点击管路接入 · Esc 取消` : '点击端口或三通，或 Shift+点击管路作为起点 · Esc 退出')
      : state.placement ? '点击画布放置设备 · Esc 取消'
      : state.mode === 'junction' ? '点击管路插入三通 · Shift+点击接出支路 · 点击空白独立放置 · Esc 取消'
      : state.mode === 'text' ? '点击画布空白放置文字 · Esc 取消'
      : state.mode === 'select' && !state.placement && state.multiSelection.some(ref => ['node', 'junction', 'label'].includes(ref.kind)) ? '方向键微调 1 单位 · Shift+方向键 10 单位 · Ctrl+Z 撤销'
      : state.mode === 'select' && state.multiSelection.some(ref => ref.kind === 'edge') ? 'Shift+点击追加管路 · 批量样式统一外观 · 单选管路调整走线'
      : '滚轮缩放 · 空白拖动平移 · Shift+空白拖动框选 · 双击管线加折点';
    commands.renderConnectionFeedback();
    commands.renderJunctionFeedback();
  }

  function render() {
    if (!state.doc) return;
    commands.$('title').value = state.doc.title;
    commands.renderSaveState();
    commands.renderExportState();
    commands.renderPreviewState();
    commands.$('undo').disabled = !state.undo.length; commands.$('redo').disabled = !state.redo.length;
    const clipboardBusy = state.mode !== 'select' || state.placement || state.pendingPort || state.reconnect || state.drag;
    commands.$('clipboard-copy').disabled = !!clipboardBusy || !state.multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind));
    document.querySelector('[data-action="copy"]').disabled = !!clipboardBusy
      || !state.multiSelection.some(ref => ['node', 'label', 'junction'].includes(ref.kind));
    commands.$('clipboard-paste').disabled = !!clipboardBusy || !state.editorClipboard;
    commands.updateStyleButton();
    commands.$('counts').textContent = `${state.doc.nodes.length} 个设备 · ${state.doc.edges.length} 条管路`;
    document.querySelectorAll('[data-tool]').forEach(b => {
      const active = b.dataset.tool === state.mode && !state.placement;
      b.classList.toggle('active', active); b.setAttribute('aria-pressed', active);
    });
    document.querySelectorAll('[data-part]').forEach(b => b.classList.toggle('active', b.dataset.part === state.placement));
    commands.$('align-description').textContent = state.ports.length ? state.ports.map(commands.refName).join(' → ') : '选择模式下依次点击两个端口，移动第二个对象。';
    for (const action of ['align-x', 'align-y']) document.querySelector(`[data-action="${action}"]`).disabled = state.ports.length !== 2;
    commands.renderCanvas(); commands.renderInspector();
  }

  return { renderMountPreview, renderCanvas, renderVertices, renderHint, render };
}
