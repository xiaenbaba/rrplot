import { nudgeSelection } from '../document.js';
import { SHORTCUTS, CANVAS_PREFERENCES, BENCHMARK } from './config.js';

/** Keyboard shortcuts, nudge transactions and focus/resize guards.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createKeyboardController(state, commands) {
  function readShortcutPreference() {
    try { return localStorage.getItem(SHORTCUTS) !== 'false'; }
    catch { return true; }
  }

  function restoreCanvasPreferences() {
    for (const [id, key] of Object.entries(CANVAS_PREFERENCES)) {
      try { commands.$(id).checked = localStorage.getItem(key) !== 'false'; }
      catch { commands.$(id).checked = true; }
    }
  }

  function saveCanvasPreference(id) {
    try { localStorage.setItem(CANVAS_PREFERENCES[id], String(commands.$(id).checked)); }
    catch { commands.message('设置已在当前页面生效，但浏览器未能记住设置；刷新后请重新检查。'); }
  }

  function renderShortcutPreference() {
    commands.$('single-key-shortcuts').checked = state.singleKeyShortcuts;
    commands.$('shortcut-preference-status').textContent = state.shortcutPreferenceSaved
      ? '此设置仅保存在当前浏览器与服务地址；不影响 Ctrl+S、撤销等组合键。'
      : '设置已在当前页面生效，但浏览器未能记住设置；刷新后请重新检查。';
  }

  function showHelp() {
    if (document.querySelector('dialog[open]')) return;
    if (state.drag || state.placement || state.pendingPort || state.reconnect || state.pageLayoutBusy || state.spaceDown)
      return commands.message('请先完成当前操作或按 Esc，再查看帮助。');
    commands.renderShortcutPreference(); commands.$('help-dialog').showModal();
    commands.$('help-body').scrollTop = 0;
  }

  function handleEditorShortcut(event) {
    if (!state.singleKeyShortcuts) return false;
    if (!state.doc && event.key !== '?') return false;
    if (event.defaultPrevented || event.repeat || event.ctrlKey || event.metaKey || event.altKey
      || !(event.target === document.body || event.target === state.svg || state.svg.contains(event.target))) return false;
    const tools = { v: 'select', b: 'box-select', m: 'move-all', c: 'connect', j: 'junction', t: 'text' };
    const help = event.key === '?', tool = !event.shiftKey && tools[event.key.toLowerCase()];
    if ((!help && (!tool || !state.doc)) || state.drag || state.placement || state.pendingPort || state.reconnect || state.pageLayoutBusy || state.spaceDown) return false;
    event.preventDefault();
    if (help) commands.showHelp(); else commands.setTool(tool);
    return true;
  }

  function endNudge() {
    if (!state.nudge) return;
    state.nudge = null;
    if (state.doc) void commands.refresh();
  }

  function nudgeSelected(event) {
    if (!state.doc || state.mode !== 'select' || state.placement || state.reconnect || state.pendingPort || state.drag || state.spaceDown
      || !state.multiSelection.some(ref => ['node', 'junction', 'label'].includes(ref.kind))) return;
    const refs = JSON.stringify(state.multiSelection);
    try {
      const next = nudgeSelection(state.doc, state.multiSelection, event.key, event.shiftKey);
      const merge = !!event.repeat && state.nudge?.key === event.key && state.nudge.refs === refs && state.nudge.version === state.revision;
      const before = state.doc; state.doc = next;
      ++state.request;
      if (commands.finishEdit(before, { merge, deferRefresh: true }) === false) { commands.endNudge(); return; }
      state.nudge = { key: event.key, refs, version: state.revision };
      commands.status(`已微调 ${event.shiftKey ? 10 : 1} 单位 · 松开方向键结束 · Ctrl+Z 撤销`);
    } catch (error) { commands.endNudge(); commands.message(error.message); }
  }

  function bindKeyboardEvents() {
    commands.$('single-key-shortcuts').addEventListener('change', () => {
      state.singleKeyShortcuts = commands.$('single-key-shortcuts').checked;
      state.shortcutPreferenceSaved = true;
      try { localStorage.setItem(SHORTCUTS, String(state.singleKeyShortcuts)); } catch { state.shortcutPreferenceSaved = false; }
      commands.renderShortcutPreference();
    });
    document.addEventListener('pointerdown', commands.endNudge, true);
    document.addEventListener('focusin', commands.endNudge);
    window.addEventListener('beforeunload', event => { if (state.dirty && !BENCHMARK) { event.preventDefault(); event.returnValue = ''; } });
    window.addEventListener('keydown', async event => {
      if (event.target.matches('input,textarea,select') || event.target.isContentEditable || event.isComposing || document.querySelector('dialog[open]')) return;
      if (event.key.startsWith('Arrow') && !event.ctrlKey && !event.metaKey && !event.altKey
        && (event.target === document.body || event.target === state.svg || state.svg.contains(event.target))) {
        event.preventDefault(); commands.nudgeSelected(event); return;
      }
      if (!['Shift', 'Alt', 'Control', 'Meta'].includes(event.key)) commands.endNudge();
      if (event.key === 'Escape' && state.paletteDrag) {
        event.preventDefault(); commands.endPaletteDrag({ pointerId: state.paletteDrag.pointerId }, true);
        commands.status('已取消图元拖放'); return;
      }
      if (event.key === 'Escape' && state.drag?.kind === 'connection-vertex') {
        event.preventDefault(); commands.cancelDrag(); commands.status('已取消本次折点拖动 · 保留连线起点和原折点'); return;
      }
      if (state.mode === 'connect' && state.pendingPort && ['Backspace', 'Delete'].includes(event.key)) {
        event.preventDefault();
        if (event.key === 'Backspace' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.repeat
          && !state.drag && !state.spaceDown && !state.placement && !state.pageLayoutBusy && state.connectionVertices.length) {
          commands.reduceConnectionVertices();
        } else commands.status('连线中 Backspace 回退折点 · Esc 取消连线后可删除对象');
        return;
      }
      if (event.key === 'Escape' && state.reconnect) { event.preventDefault(); commands.cancelReconnect(); return; }
      const modifier = event.ctrlKey || event.metaKey;
      if (event.code === 'Space') { state.spaceDown = true; event.preventDefault(); commands.renderConnectionTools(); }
      if (event.key === 'Escape') { state.mode = 'select'; state.placement = null; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.junctionPreview = null; state.ports = []; commands.cancelDrag(); }
      if (state.drag) return;
      if (commands.handleEditorShortcut(event)) return;
      if (modifier && event.key.toLowerCase() === 'a') { event.preventDefault(); commands.setTool('move-all'); }
      if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); commands.removeSelected(); }
      if (modifier && event.key.toLowerCase() === 'z') { event.preventDefault(); commands.history(event.shiftKey ? 'redo' : 'undo'); }
      if (modifier && event.key.toLowerCase() === 'y') { event.preventDefault(); commands.history('redo'); }
      if (modifier && event.key.toLowerCase() === 'd') { event.preventDefault(); commands.copySelected(); }
      if (modifier && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'c') { event.preventDefault(); commands.copyToClipboard(); }
      if (modifier && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'v') { event.preventDefault(); commands.pasteClipboard(); }
      if (modifier && event.key.toLowerCase() === 's') { event.preventDefault(); try { await commands.actions.save(); } catch (error) { commands.message(error.message); } }
    });
    window.addEventListener('keyup', event => {
      if (event.key === state.nudge?.key) commands.endNudge();
      if (event.key === 'Shift' && state.previewTarget?.pipeId) commands.clearConnectionPreview();
      if (event.code === 'Space') state.spaceDown = false;
      if (event.code === 'Space') commands.renderConnectionTools();
    });
    window.addEventListener('blur', () => { state.spaceDown = false; commands.endNudge(); if (state.drag?.kind === 'connection-vertex') commands.cancelDrag(); if (state.previewTarget?.pipeId) commands.clearConnectionPreview(); commands.renderConnectionTools(); });
    new ResizeObserver(() => { if (state.doc) { commands.clearConnectionPreview(); commands.updateView(); } }).observe(state.svg);
    new ResizeObserver(() => {
      commands.$('editor').style.setProperty('--toolbar-height', `${commands.$('canvas-toolbar').offsetHeight}px`);
    }).observe(commands.$('canvas-toolbar'));
  }

  return { readShortcutPreference, restoreCanvasPreferences, saveCanvasPreference, renderShortcutPreference, showHelp, handleEditorShortcut, endNudge, nudgeSelected, bindKeyboardEvents };
}
