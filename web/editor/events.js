import { SHORTCUTS, DRAFT, DRAFT_HISTORY } from './config.js';

/** Page action dispatch and top-level form/preference bindings.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createEventsController(state, commands) {
  function bindPageEvents() {
    commands.actions = {
      'retry-service': commands.retryService,
      help: commands.showHelp, 'close-help': () => commands.$('help-dialog').close(),
      new: () => commands.loadDocument(() => ({ schemaVersion: 1, title: '未命名图纸', page: { width: 1000, height: 700 }, nodes: [], edges: [], junctions: [], labels: [] }), '新建空白图纸', 'new'),
      open: () => { if (!document.querySelector('dialog[open]')) commands.$('file-input').click(); },
      'cancel-load': commands.cancelDocumentLoad,
      save: commands.saveJSON,
      'confirm-download': commands.confirmJSONDownload,
      'dismiss-download': () => { state.pendingDownload = null; commands.renderSaveState(); },
      export: commands.showExportSettings,
      'close-export': () => commands.$('export-dialog').close(),
      preview: commands.showPreview, 'retry-preview': commands.showPreview, 'close-preview': commands.closePreview,
      'preview-fit': commands.fitPreview, 'preview-actual': () => commands.zoomPreview(1),
      'preview-minus': () => commands.zoomPreview(state.previewSession?.scale / 1.25),
      'preview-plus': () => commands.zoomPreview(state.previewSession?.scale * 1.25),
      check: commands.runChecks, 'close-checks': () => commands.$('checks-dialog').close(),
      'toggle-library': () => { document.body.classList.toggle('library-open'); document.body.classList.remove('properties-open'); },
      'toggle-properties': () => { document.body.classList.toggle('properties-open'); document.body.classList.remove('library-open'); },
      undo: () => commands.history('undo'), redo: () => commands.history('redo'), copy: commands.copySelected, delete: commands.removeSelected,
      'connection-back': () => commands.reduceConnectionVertices(), 'connection-clear': () => commands.reduceConnectionVertices(true),
      'connection-cancel': commands.cancelPendingConnection,
      'connection-coordinates': commands.showConnectionCoordinates,
      'add-coordinate-row': () => commands.changeCoordinateRows(state.connectionCoordinates, state.connectionCoordinates?.controls.length, false),
      'import-coordinate-rows': commands.importCoordinateRows,
      'copy-coordinate-rows': commands.copyCoordinateRows,
      'clear-coordinate-rows': () => commands.resetCoordinateRows(),
      'reset-coordinate-rows': () => commands.resetCoordinateRows(true),
      'undo-coordinate-form': () => commands.coordinateFormHistory('undo'),
      'redo-coordinate-form': () => commands.coordinateFormHistory('redo'),
      'previous-coordinate-row': () => commands.navigateCoordinateRows(-1),
      'next-coordinate-row': () => commands.navigateCoordinateRows(1),
      'close-connection-coordinates': () => commands.$('connection-coordinates-dialog').close(),
      'clipboard-copy': commands.copyToClipboard, 'clipboard-paste': commands.pasteClipboard,
      'page-layout': commands.showPageLayout, 'batch-styles': commands.showBatchStyles,
      'auto-route': () => commands.autoRoute(),
      'close-styles': () => commands.$('styles-dialog').close(),
      'close-move': () => commands.$('move-dialog').close(),
      fit: commands.fit, 'fit-content': () => commands.focusDrawing('all'), 'fit-selection': () => commands.focusDrawing('selection'),
      'zoom-in': () => commands.zoom(.85), 'zoom-out': () => commands.zoom(1 / .85),
      'align-x': () => commands.alignPorts('x'), 'align-y': () => commands.alignPorts('y'),
      'clear-ports': () => { if (state.drag?.kind === 'connection-vertex') commands.cancelDrag(); state.ports = []; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; commands.render(); },
      restore: commands.showDrafts, drafts: commands.showDrafts,
      'close-drafts': commands.closeDrafts,
      'dismiss-draft': () => { state.draftBannerDismissed = true; commands.$('draft-banner').hidden = true; }
    };
    window.addEventListener('storage', event => {
      if (event.key === SHORTCUTS || event.key === null) {
        state.singleKeyShortcuts = commands.readShortcutPreference(); state.shortcutPreferenceSaved = true; commands.renderShortcutPreference();
        if (event.key === SHORTCUTS) return;
      }
      if (event.key !== null && ![DRAFT, DRAFT_HISTORY].includes(event.key)) return;
      commands.renderDraftBanner();
      if (commands.$('drafts-dialog').open && !state.restoringDraft) commands.renderDraftList();
    });
    document.addEventListener('click', async event => {
      const action = event.target.closest('[data-action]')?.dataset.action;
      if (action && (state.doc || ['help', 'close-help'].includes(action))) try { await commands.actions[action]?.(); } catch (error) { commands.message(error.message); }
      const tool = event.target.closest('[data-tool]')?.dataset.tool;
      if (tool) commands.setTool(tool);
    });
    commands.$('title').addEventListener('change', event => commands.edit(() => { state.doc.title = event.target.value; }));
    document.addEventListener('input', event => {
      if (event.target === commands.$('title') || event.target.closest('#inspector')) commands.cancelDocumentLoad();
    });
    commands.restoreCanvasPreferences();
    commands.$('grid').addEventListener('change', () => {
      commands.saveCanvasPreference('grid');
      if (state.doc) commands.renderCanvas();
      commands.status(commands.$('grid').checked ? '网格已显示' : '网格已隐藏');
    });
    commands.$('snap').addEventListener('change', () => {
      commands.saveCanvasPreference('snap');
      commands.status(commands.$('snap').checked ? '网格吸附已开启' : '网格吸附已关闭');
    });
  }

  return { bindPageEvents };
}
