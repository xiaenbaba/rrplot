import { mountedNodes } from '../geometry.js';
import { createLatestQueue } from '../requests.js';
import { clone } from './config.js';

/** Document session, selection, resolve scheduling and undo history.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createSessionController(state, commands) {
  function currentNodes(strict = false) {
    const nodes = state.doc.nodes.map(n => ({ ...n, geometry: state.geometries.get(n.id) })).filter(n => n.geometry);
    return nodes.some(n => n.mount) ? mountedNodes(state.doc, nodes, { strict }) : nodes;
  }

  function syncMounts() {
    if (!state.doc?.nodes.some(n => n.mount)) return;
    for (const n of commands.currentNodes(true)) if (n.mount) {
      const item = state.doc.nodes.find(item => item.id === n.id);
      Object.assign(item, { x: n.x, y: n.y, rotation: n.rotation });
    }
  }

  function findSelected() {
    if (!state.selection) return null;
    return state.doc[{ node: 'nodes', edge: 'edges', label: 'labels', junction: 'junctions' }[state.selection.kind]]
      ?.find(item => item.id === state.selection.id);
  }

  function selected(kind, id) {
    return state.multiSelection.some(item => item.kind === kind && item.id === id);
  }

  function setSelection(kind, id, additive = false) {
    const key = item => item.kind + ':' + item.id;
    const item = { kind, id };
    if (additive && ['node', 'label', 'junction', 'edge'].includes(kind)) {
      const index = state.multiSelection.findIndex(existing => key(existing) === key(item));
      if (index >= 0) state.multiSelection.splice(index, 1);
      else state.multiSelection.push(item);
      state.selection = state.multiSelection.at(-1) || null;
    } else {
      state.multiSelection = [item];
      state.selection = item;
    }
  }

  function clearSelection() { state.selection = null; state.multiSelection = []; }

  async function refresh() {
    const token = ++state.request, version = state.revision;
    commands.status('正在更新图纸…');
    try {
      state.resolveQueue ||= createLatestQueue(body => commands.api('resolve', body));
      const result = await state.resolveQueue({ document: clone(state.doc), sharedGlyphs: true });
      if (!result) return;
      if (token !== state.request || version !== state.revision) return;
      commands.requestFailure();
      state.geometries = new Map(result.nodes.map(n => [n.id, n.geometry]));
      commands.syncMounts();
      state.junctionPreview = null;
      state.fontFamily = result.fontFamily;
      if (state.dirty) commands.saveDraft();
      commands.renderSaveState();
      // Keep input focus and the editor-owned objects while geometry arrives.
      // Replacing inspector fields here can discard a value being typed.
      commands.renderCanvas();
      commands.status(state.draftError ? '已更新 · 草稿未保存，请保存 JSON' : '已更新 · 本机草稿自动保存');
    } catch (error) {
      if (token === state.request) { commands.requestFailure(error); commands.message(error.message); commands.status('更新未完成 · 图纸和历史已保留，可重试'); }
    }
  }

  function finishEdit(before, { merge = false, deferRefresh = false } = {}) {
    try { commands.syncMounts(); }
    catch (error) {
      state.doc = before; commands.message(error.message); commands.render(); return false;
    }
    if (JSON.stringify(before) === JSON.stringify(state.doc)) return commands.render();
    commands.cancelDocumentLoad();
    if (!merge || !state.undo.length) { state.undo.push(before); if (state.undo.length > 80) state.undo.shift(); }
    state.redo = [];
    state.dirty = true; state.revision++; commands.saveDraft(); commands.render();
    if (!deferRefresh) void commands.refresh();
    return true;
  }

  function edit(fn) {
    if (!state.doc) return;
    const before = clone(state.doc); fn(); commands.finishEdit(before);
  }

  function history(direction, { deferRefresh = false } = {}) {
    if (state.drag?.kind === 'connection-vertex') commands.cancelDrag();
    if (state.reconnect) commands.cancelReconnect();
    const from = direction === 'undo' ? state.undo : state.redo, to = direction === 'undo' ? state.redo : state.undo;
    if (!from.length) return;
    commands.cancelDocumentLoad();
    to.push(clone(state.doc)); state.doc = from.pop(); commands.clearSelection(); state.ports = []; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null;
    state.revision++; state.dirty = true; commands.saveDraft(); commands.render(); if (!deferRefresh) void commands.refresh();
  }

  return { currentNodes, syncMounts, findSelected, selected, setSelection, clearSelection, refresh, finishEdit, edit, history };
}
