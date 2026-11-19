import { along, rotate, transformedBox, route, endpoint, fitViewport } from '../geometry.js';
import { styleTargets } from '../styles.js';
import { clone } from './config.js';

/** Coordinate conversion, bounds, pan/zoom and drawing focus.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createViewportController(state, commands) {
  function snapped(v) { return +(commands.$('snap').checked ? Math.round(v / 10) * 10 : v).toFixed(2); }

  function world(event) {
    const point = state.svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
    const p = point.matrixTransform(state.svg.getScreenCTM().inverse());
    return [p.x, p.y];
  }

  function labelPosition(label, scene = null) {
    if (label.edgeId) {
      const edge = scene ? scene.edges.get(label.edgeId) : state.doc.edges.find(e => e.id === label.edgeId);
      const points = scene ? scene.routes.get(edge.id) || route(endpoint(edge.source, scene.nodes, scene.junctions),
        endpoint(edge.target, scene.nodes, scene.junctions), edge.vertices) : commands.edgePoints(edge);
      return along(points, label.at).point.map((v, i) => v + [label.x, label.y][i]);
    }
    if (!label.nodeId) return [label.x, label.y];
    const n = (scene ? scene.nodes.get(label.nodeId) : commands.currentNodes().find(n => n.id === label.nodeId)) || state.doc.nodes.find(n => n.id === label.nodeId);
    const p = rotate([label.x, label.y], n.rotation);
    return [n.x + p[0], n.y + p[1]];
  }

  function selectionCandidates() {
    const candidates = commands.currentNodes().map(n => ({ kind: 'node', id: n.id,
      box: transformedBox(n.geometry.box, [n.x, n.y], n.rotation) }));
    for (const edge of state.doc.edges) {
      try {
        const points = commands.edgePoints(edge), xs = points.map(p => p[0]), ys = points.map(p => p[1]);
        candidates.push({ kind: 'edge', id: edge.id, box: [Math.min(...xs), Math.min(...ys),
          Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)] });
      } catch { /* Geometry for a newly placed endpoint may still be loading. */ }
    }
    for (const j of state.doc.junctions) candidates.push({ kind: 'junction', id: j.id, box: [j.x - 4, j.y - 4, 8, 8] });
    for (const element of state.svg.querySelectorAll('.diagram-label')) {
      const b = element.querySelector('text').getBBox();
      candidates.push({ kind: 'label', id: element.dataset.id, box: [b.x, b.y, b.width, b.height] });
    }
    return candidates;
  }

  function edgePoints(edge) {
    const nodes = commands.currentNodes();
    return route(endpoint(edge.source, nodes, state.doc.junctions), endpoint(edge.target, nodes, state.doc.junctions), edge.vertices);
  }

  function screenMatrix() {
    const matrix = state.svg.getScreenCTM?.();
    return matrix && [matrix.a, matrix.b, matrix.c, matrix.d].every(Number.isFinite)
      && Math.abs(matrix.a * matrix.d - matrix.b * matrix.c) >= 1e-12 ? matrix : null;
  }

  function updateView({ measure = true } = {}) {
    ++state.viewRevision;
    if (measure || state.viewportWidth === null) state.viewportWidth = state.svg.clientWidth;
    const value = `${state.view.x} ${state.view.y} ${state.view.w} ${state.view.h}`;
    if (state.svg.getAttribute?.('viewBox') !== value) state.svg.setAttribute('viewBox', value);
    commands.$('zoom').textContent = Math.round((state.viewportWidth / state.view.w) * 100) + '%';
  }

  function fit() {
    if (!state.doc) return;
    commands.clearConnectionPreview();
    const ratio = state.svg.clientWidth / state.svg.clientHeight;
    const width = state.doc.page.width + 80, height = state.doc.page.height + 80;
    state.view.w = Math.max(width, height * ratio); state.view.h = state.view.w / ratio;
    state.view.x = (state.doc.page.width - state.view.w) / 2; state.view.y = (state.doc.page.height - state.view.h) / 2;
    commands.updateView();
  }

  function zoom(factor, at) {
    commands.clearConnectionPreview();
    const center = at || [state.view.x + state.view.w / 2, state.view.y + state.view.h / 2];
    const w = Math.max(100, Math.min(10000, state.view.w * factor)), k = w / state.view.w;
    state.view = { x: center[0] + (state.view.x - center[0]) * k, y: center[1] + (state.view.y - center[1]) * k, w, h: state.view.h * k };
    commands.updateView();
  }

  async function focusDrawing(scope) {
    if (!state.doc || document.querySelector('dialog[open]')) return;
    const busy = () => state.drag || state.placement || state.pendingPort || state.reconnect || state.pageLayoutBusy || state.spaceDown;
    if (busy()) return commands.message('请先完成当前操作或按 Esc，再定位画布内容。');
    if (scope === 'selection' && !state.multiSelection.length) return commands.message('请先选择要定位的设备、管路、三通或文字。');
    if (!['nodes', 'edges', 'junctions', 'labels'].some(key => state.doc[key].length)) {
      commands.fit(); commands.status('图纸为空 · 已适应页面'); return;
    }
    const session = { scope, revision: state.revision, viewRevision: state.viewRevision, selection: JSON.stringify(state.multiSelection),
      width: state.svg.clientWidth, height: state.svg.clientHeight };
    if (JSON.stringify(state.navigationSession) === JSON.stringify(session)) return;
    state.navigationSession = session;
    const current = () => state.navigationSession === session && state.revision === session.revision
      && state.viewRevision === session.viewRevision && !busy() && !document.querySelector('dialog[open]')
      && state.svg.clientWidth === session.width && state.svg.clientHeight === session.height
      && (scope !== 'selection' || JSON.stringify(state.multiSelection) === session.selection);
    commands.status(scope === 'selection' ? '正在定位所选内容…' : '正在适应全部内容…');
    try {
      const resolved = await commands.api('resolve', { document: clone(state.doc) });
      if (!current()) return;
      let refs = null;
      if (scope === 'selection') {
        const targets = styleTargets(state.doc, state.multiSelection);
        refs = new Set([...state.multiSelection.map(ref => ref.kind + ':' + ref.id),
          ...targets.edges.map(id => 'edge:' + id), ...targets.labels.map(id => 'label:' + id)]);
      }
      const boxes = commands.pageContentBoxes(resolved, refs);
      if (!current()) return;
      state.view = fitViewport(boxes, state.svg.clientWidth, state.svg.clientHeight); commands.updateView();
      commands.status(scope === 'selection' ? '已定位所选内容 · 仅调整视图' : '已适应全部内容 · 仅调整视图');
    } catch (error) {
      if (current()) { commands.message(error.message); commands.status('视图定位未完成 · 原视图保留'); }
    } finally { if (state.navigationSession === session) state.navigationSession = null; }
  }

  return { snapped, world, labelPosition, selectionCandidates, edgePoints, screenMatrix, updateView, fit, zoom, focusDrawing };
}
