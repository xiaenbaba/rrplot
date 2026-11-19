import { MOUNT_TYPES, nearestMount, endpoint, editableSegments, selectInBox, moveSegment, translateDocument, detachNode, rotate, canMount, mountNode, nearestSegment } from '../geometry.js';
import { translateSelection } from '../document.js';
import { clone, uid } from './config.js';

/** Pointer gestures, palette drag/drop and tool transitions.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createPointerController(state, commands) {
  function beginPaletteDrag(event, type, button) {
    if (!state.doc || event.button !== 0 || state.drag || state.paletteDrag || state.pageLayoutBusy) return;
    state.suppressedPaletteClick = null;
    state.paletteDrag = { type, button, pointerId: event.pointerId,
      start: [event.clientX, event.clientY], moved: false };
    button.focus({ preventScroll: true });
    button.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function paletteInside(event) {
    const box = state.svg.getBoundingClientRect();
    return event.clientX >= box.left && event.clientX < box.right
      && event.clientY >= box.top && event.clientY < box.bottom;
  }

  function movePaletteDrag(event) {
    if (!state.paletteDrag || event.pointerId !== state.paletteDrag.pointerId) return;
    if (!state.paletteDrag.moved && Math.hypot(event.clientX - state.paletteDrag.start[0],
      event.clientY - state.paletteDrag.start[1]) < 4) return;
    state.paletteDrag.moved = true;
    state.mountPreview = commands.paletteInside(event) && state.pipeMountsSupported && MOUNT_TYPES.includes(state.paletteDrag.type)
      ? nearestMount(state.doc, { id: '__palette__', type: state.paletteDrag.type }, commands.currentNodes(), commands.world(event), commands.screenMatrix()) : null;
    commands.renderMountPreview();
    commands.status(state.mountPreview ? '松开挂接到管路 · Esc 取消' : '拖到画布松开放置 · Esc 取消');
  }

  function endPaletteDrag(event, cancelled = false) {
    if (!state.paletteDrag || event.pointerId !== state.paletteDrag.pointerId) return;
    const current = state.paletteDrag; state.paletteDrag = null;
    if (current.moved || cancelled) state.suppressedPaletteClick = current.button;
    if (current.button.hasPointerCapture(current.pointerId)) current.button.releasePointerCapture(current.pointerId);
    state.mountPreview = null; commands.renderMountPreview();
    if (!cancelled && current.moved && commands.paletteInside(event)) {
      state.reconnect = null; document.body.classList.remove('library-open');
      commands.addNode(current.type, commands.world(event));
    }
  }

  function setTool(tool) {
    state.mountPreview = null;
    if (state.drag?.kind === 'connection-vertex') commands.cancelDrag();
    state.junctionPreview = null;
    state.mode = tool; state.placement = null; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.reconnect = null;
    if (tool === 'move-all') { commands.clearSelection(); state.ports = []; }
    commands.render();
    commands.status('工具：' + { select: '选择', 'box-select': '框选：拖出矩形完整框住对象，Shift 可追加', 'move-all': '整体移动：按住左键拖动全部内容', connect: '连线：点击端口或三通，或 Shift+点击管路作为起点', junction: '点击管路按位置插入三通，或点击空白独立放置', text: '在画布点击放置文字' }[tool]);
  }

  function startPan(event) {
    commands.clearConnectionPreview();
    state.drag = { kind: 'pan', client: [event.clientX, event.clientY], origin: { ...state.view }, pointerId: event.pointerId };
    state.svg.setPointerCapture(event.pointerId); state.svg.classList.add('panning'); event.preventDefault();
    commands.renderConnectionTools();
  }

  function endDrag(event) {
    if (!state.drag) return;
    if (state.drag.kind === 'connection-vertex' && event.pointerId !== state.drag.pointerId) return;
    const current = state.drag; state.drag = null; state.svg.classList.remove('panning');
    if (current.kind === 'node' && current.moved && state.pipeMountsSupported) {
      const node = state.doc.nodes.find(n => n.id === current.id);
      const target = nearestMount(state.doc, node, commands.currentNodes(), [node.x, node.y], commands.screenMatrix());
      if (target) mountNode(state.doc, node.id, target.edgeId, target.at, current.before.nodes.find(n => n.id === node.id)?.mount?.reverse);
    }
    state.mountPreview = null;
    commands.renderConnectionTools();
    if (state.svg.hasPointerCapture(event.pointerId)) state.svg.releasePointerCapture(event.pointerId);
    if (current.kind === 'connection-vertex') {
      commands.resetConnectionVertexPreview(); commands.renderCanvas();
      commands.status('临时折点已调整 · Alt+点击折点可删除 · 点击终点完成 · Esc 取消连线');
      return;
    }
    if (current.kind === 'box') {
      if (!current.moved && !current.additive) commands.clearSelection();
      state.mode = 'select'; commands.render();
      commands.status(state.multiSelection.length ? `已选择 ${state.multiSelection.length} 项 · 可批量设置样式或删除，拖动设备、三通和文字可移动`
        : '未框选对象，请完整框住设备、管路、三通或文字');
      return;
    }
    if (current.kind !== 'pan') commands.finishEdit(current.before);
  }

  function cancelDrag() {
    state.mountPreview = null;
    const current = state.drag;
    if (current?.kind === 'connection-vertex') {
      state.connectionVertices = current.beforeVertices; commands.resetConnectionVertexPreview();
    }
    if (state.drag?.before) state.doc = state.drag.before;
    if (state.drag?.kind === 'box') {
      state.multiSelection = state.drag.beforeSelection;
      state.selection = state.multiSelection.at(-1) || null;
    }
    state.drag = null; state.svg.classList.remove('panning');
    if (current && state.svg.hasPointerCapture(current.pointerId)) state.svg.releasePointerCapture(current.pointerId);
    commands.render();
  }

  function bindPointerEvents() {
    state.svg.addEventListener('pointerdown', event => {
      if (!state.doc || event.button > 1) return;
      if (state.drag?.kind === 'connection-vertex') return;
      state.svg.focus({ preventScroll: true });
      const p = commands.world(event), hit = event.target.closest('[data-kind]');
      if (event.button === 1 || state.spaceDown) return commands.startPan(event);
      if (hit?.dataset.kind === 'connection-vertex') {
        event.preventDefault();
        const index = Number(hit.dataset.index), vertex = state.connectionVertices[index];
        if (state.mode !== 'connect' || !state.pendingPort || state.placement || state.drag || state.pageLayoutBusy
          || event.shiftKey || event.ctrlKey || event.metaKey || !Number.isInteger(index)
          || !vertex || hit.dataset.point !== JSON.stringify(vertex)) return;
        if (event.altKey) {
          state.connectionVertices.splice(index, 1); commands.resetConnectionVertexPreview(); commands.message(''); commands.renderCanvas();
          commands.status(`已删除指定折点 · 剩余 ${state.connectionVertices.length} 个 · 点击终点完成`);
        } else {
          state.drag = { kind: 'connection-vertex', index, start: p, origin: [...vertex],
            beforeVertices: clone(state.connectionVertices), pointerId: event.pointerId, moved: false };
          state.previewTarget = null; commands.message(''); commands.renderCanvas();
          state.svg.setPointerCapture(event.pointerId);
          commands.status('拖动调整临时折点 · Esc 取消本次拖动');
        }
        return;
      }
      if (state.mode === 'select' && !state.placement && hit?.dataset.kind === 'endpoint') {
        const edge = state.doc.edges.find(item => item.id === hit.dataset.id);
        if (state.multiSelection.length === 1 && commands.selected('edge', edge?.id)
          && ['source', 'target'].includes(hit.dataset.side)) {
          event.preventDefault(); commands.beginReconnect(edge, hit.dataset.side);
        }
        return;
      }
      if (state.mode === 'connect' || state.mode === 'reconnect') {
        const ref = commands.connectionRef(event, p);
        if (ref) { event.preventDefault(); commands.onPort(ref); return; }
        if ((state.mode === 'connect' || (state.mode === 'reconnect' && state.reconnect)) && event.shiftKey) {
          const target = commands.pipeConnectionTarget(event, p);
          if (target) { event.preventDefault(); commands.connectToPipe(target); return; }
        }
      }
      if (state.mode === 'reconnect') {
        event.preventDefault();
        commands.status('请点击端口或三通，或 Shift+点击其他管路重接 · 空格拖动平移 · Esc 取消');
        return;
      }
      if (state.mode === 'connect') {
        event.preventDefault();
        if (!hit && state.pendingPort && event.altKey && !event.shiftKey && !event.ctrlKey && !event.metaKey
          && !state.placement && !state.drag && !state.pageLayoutBusy) { commands.addConnectionVertex(p); return; }
        if (!hit) return commands.startPan(event);
        commands.status('请点击端口或三通连接 · 起点已选时可 Shift+点击管路接入 · Esc 取消');
        return;
      }
      if (state.mode === 'junction' && !state.placement) {
        event.preventDefault();
        const target = commands.junctionTarget(event, p);
        if (target) {
          commands.useJunctionTarget(target, !!event.shiftKey);
        } else if (!hit) {
          commands.message('');
          const point = p.map(commands.snapped);
          commands.edit(() => { const id = uid('junction'); state.doc.junctions.push({ id, x: point[0], y: point[1] }); commands.setSelection('junction', id); state.mode = 'select'; });
        } else commands.status('请点击管路内部插入三通，或点击空白独立放置 · Esc 取消');
        return;
      }
      if (state.mode === 'box-select' || (state.mode === 'select' && !state.placement && event.shiftKey && !hit)) {
        state.drag = { kind: 'box', start: p, point: p, candidates: commands.selectionCandidates(),
          beforeSelection: clone(state.multiSelection), additive: event.shiftKey, moved: false, pointerId: event.pointerId };
        state.svg.setPointerCapture(event.pointerId); event.preventDefault(); return;
      }
      if (state.mode === 'move-all') {
        ++state.request;
        state.drag = { kind: 'all', start: p, before: clone(state.doc), pointerId: event.pointerId, moved: false };
        state.svg.setPointerCapture(event.pointerId); event.preventDefault(); return;
      }
      if (hit?.dataset.kind === 'port') { event.preventDefault(); commands.onPort(JSON.parse(hit.dataset.ref)); return; }
      if (hit?.dataset.kind === 'junction' && state.mode === 'connect') { commands.onPort({ junctionId: hit.dataset.id }); return; }
      if (state.placement) { commands.addNode(state.placement, p); return; }
      if (state.mode === 'text' && !hit) {
        commands.edit(() => { const id = uid('label'); state.doc.labels.push({ id, text: '文字', x: commands.snapped(p[0]), y: commands.snapped(p[1]), size: 15, ha: 'center', color: '#111111', boxed: false }); commands.setSelection('label', id); state.mode = 'select'; }); return;
      }
      if (!hit) { commands.clearSelection(); commands.render(); return commands.startPan(event); }
      const kind = hit.dataset.kind, id = hit.dataset.id;
      if (kind === 'vertex' && event.altKey) {
        commands.edit(() => state.doc.edges.find(e => e.id === id).vertices.splice(Number(hit.dataset.index), 1)); return;
      }
      const selectedKind = ['vertex', 'segment'].includes(kind) ? 'edge' : kind;
      const additive = event.shiftKey && ['node', 'label', 'junction', 'edge'].includes(selectedKind);
      const keepMulti = !additive && state.multiSelection.length > 1
        && state.multiSelection.some(ref => ref.kind === selectedKind && ref.id === id);
      if (!keepMulti) commands.setSelection(selectedKind, id, additive);
      if (additive) { commands.render(); return; }
      const item = commands.findSelected();
      if (kind === 'segment') {
        ++state.request;
        const nodes = commands.currentNodes(), index = Number(hit.dataset.index);
        const source = endpoint(item.source, nodes, state.doc.junctions), target = endpoint(item.target, nodes, state.doc.junctions);
        const segment = editableSegments(source, target, item.vertices).find(s => s.index === index);
        if (!segment) return;
        state.drag = { kind, id, index, source, target, axis: segment.axis, coordinate: segment.point[segment.axis],
          vertices: clone(item.vertices), start: p, before: clone(state.doc), pointerId: event.pointerId, moved: false };
        state.svg.setPointerCapture(event.pointerId); event.preventDefault(); return;
      }
      if (kind === 'edge') {
        // Keep the clicked path alive so the browser can deliver a double click.
        state.svg.querySelectorAll('[data-kind="node"], [data-kind="edge"], [data-kind="label"], [data-kind="junction"]')
          .forEach(element => element.classList.toggle('selected', commands.selected(element.dataset.kind, element.dataset.id)));
        commands.renderInspector(); commands.renderVertices(); return;
      }
      if (['node', 'label', 'junction', 'vertex'].includes(kind)) {
        ++state.request;
        if (state.multiSelection.length > 1 && state.multiSelection.some(ref => ref.kind === selectedKind && ref.id === id)) {
          state.drag = { kind: 'multi', start: p, before: clone(state.doc), pointerId: event.pointerId, moved: false };
        } else {
          const pose = kind === 'node' && item.mount ? commands.currentNodes().find(n => n.id === id) : item;
          state.drag = { kind, id, start: p, before: clone(state.doc), origin: kind === 'vertex' ? [...item.vertices[Number(hit.dataset.index)]] : [pose.x, pose.y],
            index: Number(hit.dataset.index), pointerId: event.pointerId, moved: false };
        }
        state.svg.setPointerCapture(event.pointerId); event.preventDefault();
      }
      commands.render();
    });
    state.svg.addEventListener('pointermove', event => {
      if (!state.drag) {
        if (state.placement && state.pipeMountsSupported && MOUNT_TYPES.includes(state.placement)) {
          const candidate = { id: '__placement__', type: state.placement };
          state.mountPreview = nearestMount(state.doc, candidate, commands.currentNodes(), commands.world(event), commands.screenMatrix());
          commands.renderMountPreview(); return;
        }
        if (state.mode === 'junction' && !state.placement) {
          const next = state.spaceDown ? null : commands.junctionTarget(event, commands.world(event));
          if (JSON.stringify(next) !== JSON.stringify(state.junctionPreview)) {
            state.junctionPreview = next; commands.renderCanvas();
          }
          return;
        }
        if (state.mode === 'connect' || state.reconnect) {
          let next = commands.connectionTarget(event, commands.world(event));
          if (state.mode === 'connect' && !state.pendingPort && !next.ref && !next.pipeId) next = null;
          const changed = !!next !== !!state.previewTarget || (next && (next.point.some((value, index) => value !== state.previewTarget.point[index])
            || next.direction.some((value, index) => value !== state.previewTarget.direction[index])
            || JSON.stringify(next.ref) !== JSON.stringify(state.previewTarget.ref) || next.error !== state.previewTarget.error
            || next.pipeId !== state.previewTarget.pipeId || next.fraction !== state.previewTarget.fraction
            || next.version !== state.previewTarget.version));
          if (changed) { state.previewTarget = next; commands.renderCanvas(); }
        }
        return;
      }
      if (state.drag.kind === 'pan') {
        state.view.x = state.drag.origin.x - (event.clientX - state.drag.client[0]) * state.view.w / state.svg.clientWidth;
        state.view.y = state.drag.origin.y - (event.clientY - state.drag.client[1]) * state.view.h / state.svg.clientHeight;
        commands.updateView(); return;
      }
      const p = commands.world(event), delta = p.map((v, i) => v - state.drag.start[i]);
      if (state.drag.kind === 'connection-vertex') {
        if (event.pointerId !== state.drag.pointerId) return;
        if (!state.drag.moved && Math.hypot(...delta) < 1) return;
        let next;
        try { next = commands.connectionVertexPoint(state.drag.origin.map((v, i) => v + delta[i]), state.drag.index); }
        catch (error) { commands.message(error.message); return; }
        if (next.every((value, i) => value === state.connectionVertices[state.drag.index][i])) return;
        state.drag.moved = true; state.connectionVertices[state.drag.index] = next;
        state.previewTarget = { point: state.connectionVertices.at(-1), direction: [0, 0] };
        commands.message(''); commands.renderCanvas(); return;
      }
      if (state.drag.kind === 'box') {
        if (!state.drag.moved && Math.hypot(...delta) < 2) return;
        state.drag.moved = true; state.drag.point = p;
        state.multiSelection = selectInBox(state.drag.candidates, state.drag.start, p, state.drag.additive ? state.drag.beforeSelection : []);
        state.selection = state.multiSelection.at(-1) || null;
        commands.renderCanvas(); commands.renderInspector(); return;
      }
      if (state.drag.kind === 'segment') {
        if (!state.drag.moved && Math.abs(delta[state.drag.axis]) < 1) return;
        const offset = commands.snapped(state.drag.coordinate + delta[state.drag.axis]) - state.drag.coordinate;
        const vertices = moveSegment(state.drag.source, state.drag.target, state.drag.vertices, state.drag.index, offset);
        if (vertices.length > 100) return commands.message('管路折点已达上限，请先清除部分折点。');
        state.drag.moved = true;
        state.doc.edges.find(e => e.id === state.drag.id).vertices = vertices;
        commands.renderCanvas(); return;
      }
      if (!state.drag.moved && Math.hypot(...delta) < 1) return;
      state.drag.moved = true;
      if (state.drag.kind === 'all') {
        state.doc = translateDocument(state.drag.before, ...delta.map(commands.snapped));
        commands.renderCanvas(); return;
      }
      if (state.drag.kind === 'multi') {
        state.doc = translateSelection(state.drag.before, state.multiSelection, delta.map(commands.snapped));
        commands.renderCanvas(); return;
      }
      const item = commands.findSelected();
      if (state.drag.kind === 'node' && item.mount) {
        const pose = commands.currentNodes().find(n => n.id === item.id); detachNode(item, pose);
      }
      if (state.drag.kind === 'label' && item.nodeId) {
        const n = commands.currentNodes().find(n => n.id === item.nodeId), local = rotate(delta, -n.rotation);
        [item.x, item.y] = state.drag.origin.map((v, i) => commands.snapped(v + local[i]));
      } else if (state.drag.kind === 'vertex') item.vertices[state.drag.index] = state.drag.origin.map((v, i) => commands.snapped(v + delta[i]));
      else [item.x, item.y] = state.drag.origin.map((v, i) => commands.snapped(v + delta[i]));
      state.mountPreview = state.drag.kind === 'node' && state.pipeMountsSupported && canMount(state.doc, item)
        ? nearestMount(state.doc, item, commands.currentNodes(), [item.x, item.y], commands.screenMatrix()) : null;
      if (state.mountPreview) commands.status('松开挂接到管路 · 拖离管路可解除 · Esc 取消');
      commands.renderCanvas();
    });
    state.svg.addEventListener('pointerleave', () => {
      if (!state.drag && state.mountPreview) { state.mountPreview = null; commands.renderMountPreview(); }
      if (!state.drag) commands.clearConnectionPreview();
    });
    state.svg.addEventListener('pointerup', commands.endDrag);
    state.svg.addEventListener('pointercancel', commands.cancelDrag);
    state.svg.addEventListener('lostpointercapture', () => { if (state.drag?.kind === 'connection-vertex') commands.cancelDrag(); });
    state.svg.addEventListener('dblclick', event => {
      if (event.shiftKey || state.mode !== 'select' || state.placement || state.reconnect) return;
      if (event.target.closest('[data-kind="segment"]')) return;
      const hit = event.target.closest('[data-kind="edge"]'); if (!hit) return;
      const edge = state.doc.edges.find(e => e.id === hit.dataset.id), points = commands.edgePoints(edge), p = commands.world(event);
      const index = nearestSegment(points, p);
      commands.edit(() => { const vertices = points.slice(1, -1); vertices.splice(index, 0, p.map(commands.snapped)); edge.vertices = vertices; commands.setSelection('edge', edge.id); });
    });
    state.svg.addEventListener('wheel', event => { event.preventDefault(); if (state.doc) commands.zoom(event.deltaY > 0 ? 1.1 : 1 / 1.1, commands.world(event)); }, { passive: false });
    state.svg.addEventListener('dragover', event => {
      event.preventDefault();
      const type = state.draggingPart || event.dataTransfer.getData('text/rrplot-part');
      if (state.pipeMountsSupported && MOUNT_TYPES.includes(type)) {
        state.mountPreview = nearestMount(state.doc, { id: '__drop__', type }, commands.currentNodes(), commands.world(event), commands.screenMatrix());
        commands.renderMountPreview();
      }
    });
    state.svg.addEventListener('dragleave', event => {
      if (!state.mountPreview || state.svg.contains(event.relatedTarget)) return;
      const box = state.svg.getBoundingClientRect();
      if (event.clientX >= box.left && event.clientX < box.right
        && event.clientY >= box.top && event.clientY < box.bottom) return;
      state.mountPreview = null; commands.renderMountPreview();
    });
    state.svg.addEventListener('drop', event => {
      event.preventDefault();
      const type = state.draggingPart || event.dataTransfer.getData('text/rrplot-part');
      state.draggingPart = null; state.mountPreview = null; commands.renderMountPreview();
      if (state.catalog.some(c => c.type === type)) { state.reconnect = null; commands.addNode(type, commands.world(event)); }
    });
  }

  return { beginPaletteDrag, paletteInside, movePaletteDrag, endPaletteDrag, setTool, startPan, endDrag, cancelDrag, bindPointerEvents };
}
