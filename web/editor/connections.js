import { endpoint, projectOnRoute, route, splitRoute, splitMounts } from '../geometry.js';
import { inspectDiagram } from '../checks.js';
import { reconnectEdge, splitEdgeLabels } from '../document.js';
import { uid, clone } from './config.js';

/** Port/junction targeting, branching, validation and reconnection.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createConnectionsController(state, commands) {
  function refName(ref) {
    if (ref.junctionId) return '三通 · ' + ref.junctionId.slice(-5);
    const n = state.doc.nodes.find(n => n.id === ref.nodeId);
    return (n?.title || ref.nodeId) + ' · ' + ref.portId;
  }

  function eqRef(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function connectionRef(event, point) {
    const hit = event.target.closest('[data-kind="port"], [data-kind="junction"]');
    const ref = hit?.dataset.kind === 'port' ? JSON.parse(hit.dataset.ref)
      : hit?.dataset.kind === 'junction' ? { junctionId: hit.dataset.id } : null;
    if (ref) return ref;
    const matrix = commands.screenMatrix();
    if (!matrix) return null;
    const nodes = commands.currentNodes();
    let nearest = null, distance = 12;
    const consider = candidate => {
      const target = endpoint(candidate, nodes, state.doc.junctions).point;
      const [dx, dy] = target.map((value, index) => value - point[index]);
      const pixels = Math.hypot(matrix.a * dx + matrix.c * dy, matrix.b * dx + matrix.d * dy);
      if (pixels <= 12 && (!nearest || pixels < distance - 1e-6)) { nearest = candidate; distance = pixels; }
    };
    for (const node of nodes) {
      if (node.mount) continue;
      const seen = new Set();
      for (const [id, port] of Object.entries(node.geometry.ports)) {
        const key = port.point.join(',');
        if (seen.has(key)) continue;
        seen.add(key); consider({ nodeId: node.id, portId: id });
      }
    }
    for (const junction of state.doc.junctions) consider({ junctionId: junction.id });
    return nearest;
  }

  function connectionTarget(event, point) {
    if (state.mode === 'connect' && state.pendingPort && event.target.closest('[data-kind]')?.dataset.kind === 'connection-vertex')
      return { point, direction: [0, 0] };
    const ref = commands.connectionRef(event, point);
    if (ref) {
      const target = { ...endpoint(ref, commands.currentNodes(), state.doc.junctions), ref, version: state.revision };
      const sameRef = state.previewTarget?.ref && ['nodeId', 'portId', 'junctionId'].every(key => state.previewTarget.ref[key] === ref[key]);
      target.error = sameRef && state.previewTarget.version === state.revision ? state.previewTarget.error : commands.connectionError(ref);
      return target;
    }
    if ((state.mode === 'connect' || (state.mode === 'reconnect' && state.reconnect))
      && event.shiftKey && !state.spaceDown) {
      const target = commands.pipeConnectionTarget(event, point);
      if (target) return target;
    }
    return { point, direction: [0, 0] };
  }

  function pipeConnectionTarget(event, point) {
    const split = commands.junctionTarget(event, point);
    if (!split) return null;
    const target = { pipeId: split.edgeId, point: split.point, direction: [0, 0],
      fraction: split.fraction, version: state.revision, error: split.error };
    if (!target.error) {
      if (state.previewTarget?.pipeId === target.pipeId && state.previewTarget.fraction === target.fraction
        && state.previewTarget.version === state.revision) target.error = state.previewTarget.error;
      else try { commands.preparePipeConnection(target); } catch (error) { target.error = error.message; }
    }
    return target;
  }

  function connectionError(ref) {
    try {
      if (state.mode === 'connect' && state.pendingPort)
        commands.checkConnection({ id: null, source: state.pendingPort, target: ref, vertices: state.connectionVertices });
      else if (state.mode === 'reconnect' && state.reconnect) {
        const edge = state.doc.edges.find(item => item.id === state.reconnect.edgeId);
        const previous = edge[state.reconnect.side];
        if (['nodeId', 'portId', 'junctionId'].some(key => previous[key] !== ref[key]))
          commands.checkConnection({ ...edge, [state.reconnect.side]: ref }, edge.id);
      }
      return '';
    } catch (error) { return error.message; }
  }

  function renderConnectionFeedback() {
    const active = state.mode === 'connect' || state.reconnect;
    const target = active && (state.previewTarget?.ref || state.previewTarget?.pipeId) ? state.previewTarget : null;
    const hint = document.querySelector('.canvas-hint');
    hint.classList.toggle('connection-valid-hint', !!target && !target.error);
    hint.classList.toggle('connection-invalid-hint', !!target?.error);
    if (target?.pipeId) hint.textContent = (target.error ? '不可接入管路：' + target.error
      : state.reconnect ? 'Shift+点击插入三通并重接' + (state.reconnect.side === 'source' ? '起点' : '终点')
      : state.pendingPort ? 'Shift+点击插入三通并接入管路' : 'Shift+点击插入三通并作为连线起点')
      + ' · X ' + target.point[0].toFixed(2) + ' / Y ' + target.point[1].toFixed(2) + ' · Esc 取消';
    else if (target) hint.textContent = (target.error ? '不可连接：' : state.mode === 'connect' && !state.pendingPort ? '点击起点：' : '点击连接：') + commands.refName(target.ref)
      + (target.error ? ' · ' + target.error : ' · Esc 取消');
    if (target && state.mode === 'connect' && state.pendingPort && state.connectionVertices.length)
      hint.textContent += ` · ${state.connectionVertices.length} 个折点 · 拖动方框调整 · Backspace 回退`;
    return target;
  }

  function clearConnectionPreview() {
    const connection = state.previewTarget && (state.mode === 'connect' || state.reconnect);
    if (!connection && !state.junctionPreview) return;
    if (connection) state.previewTarget = null;
    state.junctionPreview = null;
    commands.renderCanvas();
  }

  function junctionRefTarget(ref) {
    return { ref, point: endpoint(ref, commands.currentNodes(), state.doc.junctions).point, version: state.revision,
      error: ref.nodeId ? '此处已有设备端口，请使用“连线”连接，不要重复插入三通。' : '' };
  }

  function junctionTarget(event, point) {
    const hit = event.target.closest('[data-kind]');
    if (state.mode === 'junction' && (!hit || ['edge', 'vertex', 'segment', 'endpoint', 'port', 'junction'].includes(hit.dataset.kind))) {
      try {
        const ref = commands.connectionRef(event, point);
        if (ref) return commands.junctionRefTarget(ref);
      } catch { /* Ignore stale endpoint targets until geometry refreshes. */ }
    }
    if (hit && !['edge', 'vertex', 'segment', 'endpoint'].includes(hit.dataset.kind)) return null;
    const matrix = commands.screenMatrix();
    if (!hit && !matrix) return null;
    let nearest = null;
    for (const edge of hit ? state.doc.edges.filter(item => item.id === hit.dataset.id) : state.doc.edges) {
      let points;
      try { points = commands.edgePoints(edge); } catch { continue; }
      const projected = projectOnRoute(points, point, matrix);
      if ((!hit && projected.distance > 12) || (nearest && projected.distance >= nearest.projected.distance - 1e-6)) continue;
      nearest = { edge, points, projected };
    }
    if (!nearest) {
      // Preview the actual grid landing point too, before placing a free junction.
      if (state.mode === 'junction' && !hit) {
        const landing = point.map(commands.snapped), ref = commands.connectionRef(event, landing);
        if (ref) {
          const target = commands.junctionRefTarget(ref);
          if (target.point.every((v, i) => Math.abs(v - landing[i]) < 1e-6)) return target;
        }
      }
      return null;
    }
    const { edge, points, projected } = nearest;
    const target = { edgeId: edge.id, point: projected.point, fraction: projected.at, version: state.revision, error: '' };
    try { commands.junctionSplit(edge, target.fraction, points); commands.checkJunctionCapacity(); }
    catch (error) { target.error = error.message; }
    return target;
  }

  function renderJunctionFeedback() {
    if (state.junctionPreview && (state.mode !== 'junction' || state.placement || state.drag || state.junctionPreview.version !== state.revision))
      state.junctionPreview = null;
    const target = state.junctionPreview;
    const hint = document.querySelector('.canvas-hint');
    hint.classList.toggle('junction-valid-hint', !!target && !target.error);
    hint.classList.toggle('junction-invalid-hint', !!target?.error);
    if (target) hint.textContent = target.error ? '不可插入：' + target.error
      : (target.ref ? '点击选择已有三通 · Shift+点击接出支路' : '点击插入三通 · Shift+点击接出支路')
        + ' · X ' + target.point[0].toFixed(2) + ' / Y ' + target.point[1].toFixed(2) + ' · Esc 取消';
    return target;
  }

  function beginReconnect(edge, side) {
    if (state.drag?.kind === 'connection-vertex') commands.cancelDrag();
    commands.message('');
    state.reconnect = { edgeId: edge.id, side }; state.mode = 'reconnect'; state.placement = null; state.pendingPort = null; state.connectionVertices = []; state.ports = [];
    state.previewTarget = endpoint(edge[side], commands.currentNodes(), state.doc.junctions);
    commands.render(); commands.status('请选择新的' + (side === 'source' ? '起点' : '终点') + '端口或三通，或 Shift+点击其他管路 · Esc 取消');
  }

  function cancelReconnect() {
    commands.message('');
    state.reconnect = null; state.previewTarget = null; state.mode = 'select'; commands.render(); commands.status('已取消重接，管路保持原连接');
  }

  function checkConnection(edge, excludeId = null, document = state.doc) {
    if ([edge.source, edge.target].some(ref => document.nodes.find(n => n.id === ref.nodeId)?.mount))
      throw new Error('挂接阀件属于管路附件，请连接原管路或先解除挂接。');
    if (!excludeId && document.edges.length >= 2000)
      throw new Error('管路数量将超过 2000 项，请先减少对象。');
    const nodes = commands.currentNodes();
    const [a, b] = [edge.source, edge.target].map(ref => endpoint(ref, nodes, document.junctions));
    if (a.point.every((v, i) => Math.abs(v - b.point[i]) < 1e-6))
      throw new Error('管路两端不能连接到同一位置，请选择其他端口或三通。');
    const edges = document.edges.filter(item => item.id !== excludeId);
    const routes = new Map();
    for (const item of edges) {
      try { routes.set(item.id, route(endpoint(item.source, nodes, document.junctions),
        endpoint(item.target, nodes, document.junctions), item.vertices)); }
      catch { /* Unresolved unrelated geometry is checked after refresh. */ }
    }
    routes.set(edge.id, route(a, b, edge.vertices));
    const duplicate = inspectDiagram({ ...document, edges: [...edges, edge] }, { nodes, routes })
      .some(issue => issue.code === 'duplicate-edge' && issue.ref.id === edge.id);
    if (duplicate) throw new Error('这两个接点之间已有相同走线的管路，请选择其他接点，或先调整已有管路的走线。');
  }

  function onPort(ref) {
    if (state.doc.nodes.find(n => n.id === ref.nodeId)?.mount) return commands.message('请先解除阀件挂接，再连接其端口。');
    if (state.mode === 'reconnect' && state.reconnect) {
      try {
        const edge = state.doc.edges.find(e => e.id === state.reconnect.edgeId);
        const next = reconnectEdge(state.doc, edge.id, state.reconnect.side, ref);
        const previous = edge[state.reconnect.side];
        if (['nodeId', 'portId', 'junctionId'].some(key => previous[key] !== ref[key]))
          commands.checkConnection(next.edges.find(item => item.id === edge.id), edge.id);
        commands.message('');
        state.reconnect = null; state.previewTarget = null; state.mode = 'select';
        commands.edit(() => { state.doc = next; });
      } catch (error) { commands.message(error.message); }
      return;
    }
    if (state.mode === 'connect') {
      if (!state.pendingPort) {
        state.connectionVertices = [];
        state.pendingPort = ref;
        state.previewTarget = endpoint(ref, commands.currentNodes(), state.doc.junctions);
        commands.status('已选择起点，请点击终点端口或三通');
      }
      else {
        try {
          const id = uid('edge'), edge = { id, source: state.pendingPort, target: ref, vertices: clone(state.connectionVertices), head: true, headAt: [.55], color: '#111111', width: 1.8, linestyle: 'solid' };
          commands.checkConnection(edge);
          commands.message('');
          commands.edit(() => {
            state.doc.edges.push(edge); commands.setSelection('edge', id); state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null;
          });
        } catch (error) { commands.message(error.message); }
      }
      commands.render(); return;
    }
    state.ports = state.ports.filter(p => !commands.eqRef(p, ref));
    state.ports.push(ref); if (state.ports.length > 2) state.ports.shift(); commands.render();
  }

  function connectionVertexPoint(point, index = state.connectionVertices.length, vertices = state.connectionVertices, snap = true, source = state.pendingPort) {
    const next = snap ? point.map(commands.snapped) : [...point];
    if (next.some(value => !Number.isFinite(value) || Math.abs(value) > 100000))
      throw new Error('折点坐标超出允许范围，请选择画布中的其他位置。');
    const previous = vertices[index - 1] || endpoint(source, commands.currentNodes(), state.doc.junctions).point;
    if ([previous, vertices[index + 1]].filter(Boolean)
      .some(neighbor => next.every((value, axis) => Math.abs(value - neighbor[axis]) < 1e-6)))
      throw new Error('折点与相邻点重合，请选择其他位置。');
    return next;
  }

  function addConnectionVertex(point) {
    if (state.connectionVertices.length >= 100) return commands.message('管路折点已达 100 个上限，请按 Backspace 回退。');
    let next;
    try { next = commands.connectionVertexPoint(point); } catch (error) { return commands.message(error.message); }
    state.connectionVertices.push(next);
    state.previewTarget = { point: next, direction: [0, 0] };
    commands.message(''); commands.renderCanvas();
    commands.status(`已指定 ${state.connectionVertices.length} 个折点 · Backspace 回退 · 点击终点完成 · Esc 取消`);
  }

  function resetConnectionVertexPreview() {
    state.previewTarget = state.connectionVertices.length ? { point: state.connectionVertices.at(-1), direction: [0, 0] } : null;
  }

  function connectionToolsBusy() {
    return !!(state.drag || state.placement || state.reconnect || state.spaceDown || state.pageLayoutBusy);
  }

  function renderConnectionTools() {
    const active = !!(state.doc && state.mode === 'connect' && state.pendingPort && !state.reconnect);
    commands.$('connection-tools').hidden = !active;
    const text = active ? `连线中 · ${state.connectionVertices.length} 个临时折点` : '';
    if (commands.$('connection-summary').textContent !== text) commands.$('connection-summary').textContent = text;
    const busy = commands.connectionToolsBusy();
    commands.$('connection-back').disabled = commands.$('connection-clear').disabled = commands.$('connection-coordinates').disabled = !active || busy || !state.connectionVertices.length;
    commands.$('connection-cancel').disabled = !active || busy;
  }

  function reduceConnectionVertices(all = false) {
    if (!state.doc || state.mode !== 'connect' || !state.pendingPort || commands.connectionToolsBusy() || !state.connectionVertices.length) return;
    if (all) state.connectionVertices = []; else state.connectionVertices.pop();
    commands.resetConnectionVertexPreview(); commands.message(''); commands.renderCanvas(); state.svg.focus({ preventScroll: true });
    commands.status(`${all ? '已清空临时折点' : '已回退折点'} · 剩余 ${state.connectionVertices.length} 个 · 点击终点完成 · Esc 取消`);
  }

  function cancelPendingConnection() {
    if (!state.doc || state.mode !== 'connect' || !state.pendingPort || commands.connectionToolsBusy()) return;
    state.ports = []; commands.setTool('select'); commands.message(''); state.svg.focus({ preventScroll: true });
    commands.status('已取消未完成连线 · 已插入的三通保留，可 Ctrl+Z 撤销');
  }

  function junctionSplit(edge, fraction, points = commands.edgePoints(edge)) {
    if (!Number.isFinite(fraction) || fraction <= 1e-6 || fraction >= 1 - 1e-6)
      throw new Error('请在管路内部插入三通，端点处请直接使用已有端口或三通。');
    const split = splitRoute(points, fraction), { point: p, prefix, suffix } = split;
    if (prefix.length > 100 || suffix.length > 100)
      throw new Error('分段后的管路折点超过上限，请先减少折点。');
    if (points.every(point => point.every((v, i) => Math.abs(v - p[i]) < 1e-6)))
      throw new Error('管路长度为零，无法插入三通。');
    return split;
  }

  function checkJunctionCapacity(extraEdges = 1) {
    if (state.doc.junctions.length >= 2000 || state.doc.edges.length + extraEdges > 2000)
      throw new Error('三通或管路数量将超过 2000 项，请先减少对象。');
  }

  function applyJunctionSplit(document, edgeId, split, fraction, id, otherId) {
    const edge = document.edges.find(item => item.id === edgeId);
    const { point: p, prefix, suffix } = split;
    document.junctions.push({ id, x: p[0], y: p[1] });
    // Explicit split vertices keep both routes anchored at the junction.
    const other = { ...clone(edge), id: otherId, source: { junctionId: id }, vertices: suffix };
    edge.target = { junctionId: id }; edge.vertices = prefix;
    document.edges.push(other);
    document.labels = splitEdgeLabels(document.labels, edge.id, other.id, fraction);
    if (document.nodes.some(n => n.mount?.edgeId === edge.id)) splitMounts(document, edge.id, other.id, fraction);
  }

  function preparePipeConnection(target, createId = null) {
    const rejoining = state.mode === 'reconnect' && state.reconnect;
    const connecting = state.mode === 'connect' && state.pendingPort && !state.reconnect;
    const starting = state.mode === 'connect' && !state.pendingPort && !state.reconnect;
    if ((!connecting && !rejoining && !starting) || state.placement || state.drag || state.spaceDown || state.pageLayoutBusy)
      throw new Error('请先切换连线工具或选择重接端点，再按住 Shift 点击目标管路。');
    const edge = state.doc.edges.find(item => item.id === target.pipeId);
    if (!edge) throw new Error('目标管路已不存在，请重新选择。');
    if (rejoining) {
      if (!state.doc.edges.some(item => item.id === rejoining.edgeId) || !['source', 'target'].includes(rejoining.side))
        throw new Error('找不到需要重接的管路端点。');
      if (rejoining.edgeId === edge.id) throw new Error('不能将管路重接到自身，请选择其他管路或已有接点。');
    }
    const split = commands.junctionSplit(edge, target.fraction);
    commands.checkJunctionCapacity(rejoining || starting ? 1 : 2);
    let next = clone(state.doc);
    // Hover checks use local IDs and never consume real object IDs or edit history.
    const used = new Set(['nodes', 'edges', 'junctions', 'labels'].flatMap(key => next[key].map(item => item.id)));
    let serial = 0;
    const idFor = createId || (prefix => {
      let id; do { id = prefix + '-preview-' + serial++; } while (used.has(id));
      used.add(id); return id;
    });
    const junctionId = idFor('junction');
    commands.applyJunctionSplit(next, edge.id, split, target.fraction, junctionId, idFor('edge'));
    if (starting) return { document: next, startId: junctionId };
    if (rejoining) {
      next = reconnectEdge(next, rejoining.edgeId, rejoining.side, { junctionId });
      const edited = next.edges.find(item => item.id === rejoining.edgeId);
      commands.checkConnection(edited, edited.id, next);
      return { document: next, branchId: edited.id, reconnected: true };
    }
    const branch = { id: idFor('edge'), source: clone(state.pendingPort), target: { junctionId },
      vertices: clone(state.connectionVertices), head: true, headAt: [.55], color: '#111111', width: 1.8, linestyle: 'solid' };
    commands.checkConnection(branch, null, next);
    next.edges.push(branch);
    return { document: next, branchId: branch.id };
  }

  function connectToPipe(target) {
    try {
      const next = commands.preparePipeConnection(target, uid);
      commands.message('');
      commands.edit(() => {
        state.doc = next.document;
        if (next.startId) { commands.setSelection('junction', next.startId); state.mode = 'select'; }
        else commands.setSelection('edge', next.branchId);
        state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.junctionPreview = null; state.ports = [];
        if (next.reconnected) { state.reconnect = null; state.mode = 'select'; }
      });
      if (next.startId) { commands.beginBranch(next.startId); return; }
      commands.status((next.reconnected ? '已插入三通并完成重接' : '已插入三通并接入管路') + ' · Ctrl+Z 可一次撤销');
    } catch (error) {
      state.previewTarget = { ...target, error: error.message };
      commands.message(error.message); commands.renderCanvas();
    }
  }

  function branchBusy() {
    return !['select', 'junction'].includes(state.mode) || !!(state.placement || state.pendingPort || state.reconnect || state.drag || state.spaceDown || state.pageLayoutBusy);
  }

  function beginBranch(junctionId) {
    if (commands.branchBusy()) return commands.message('请先完成当前操作或按 Esc，再接出支路。');
    if (!state.doc.junctions.some(item => item.id === junctionId)) return commands.message('找不到支路起点三通。');
    commands.message('');
    state.mode = 'connect'; state.placement = null; state.ports = []; state.junctionPreview = null;
    state.pendingPort = { junctionId };
    state.connectionVertices = [];
    state.previewTarget = endpoint(state.pendingPort, commands.currentNodes(), state.doc.junctions);
    commands.render(); commands.status('三通已选为支路起点 · 点击终点端口或三通 · Esc 取消连线并保留三通');
  }

  function useJunctionTarget(target, branch = false) {
    state.junctionPreview = target;
    if (target.error) { commands.message(target.error); commands.renderCanvas(); return; }
    if (!target.ref) {
      commands.splitEdge(state.doc.edges.find(item => item.id === target.edgeId), target.fraction, branch);
      return;
    }
    commands.message('');
    commands.setSelection('junction', target.ref.junctionId); state.mode = 'select'; state.ports = []; state.junctionPreview = null;
    commands.render(); commands.status('已选择已有三通 · 未新增三通或管路');
    if (branch) commands.beginBranch(target.ref.junctionId);
  }

  function splitEdge(edge, fraction = .5, branch = false) {
    if (branch && commands.branchBusy()) return commands.message('请先完成当前操作或按 Esc，再接出支路。');
    let split;
    try { split = commands.junctionSplit(edge, fraction); commands.checkJunctionCapacity(); }
    catch (error) { return commands.message(error.message); }
    const id = uid('junction');
    commands.message('');
    commands.edit(() => {
      commands.applyJunctionSplit(state.doc, edge.id, split, fraction, id, uid('edge'));
      commands.setSelection('junction', id);
      state.mode = 'select'; state.ports = []; state.junctionPreview = null;
    });
    if (branch) commands.beginBranch(id);
  }

  return { refName, eqRef, connectionRef, connectionTarget, pipeConnectionTarget, connectionError, renderConnectionFeedback, clearConnectionPreview, junctionRefTarget, junctionTarget, renderJunctionFeedback, beginReconnect, cancelReconnect, checkConnection, onPort, connectionVertexPoint, addConnectionVertex, resetConnectionVertexPreview, connectionToolsBusy, renderConnectionTools, reduceConnectionVertices, cancelPendingConnection, junctionSplit, checkJunctionCapacity, applyJunctionSplit, preparePipeConnection, connectToPipe, branchBusy, beginBranch, useJunctionTarget, splitEdge };
}
