import { uid, DRAFT_HISTORY, DRAFT, BENCHMARK, clone } from './config.js';

/** JSON loading/saving, download confirmation and local draft recovery.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createFilesController(state, commands) {
  function parseDraft(raw) {
    try {
      const saved = typeof raw === 'string' ? JSON.parse(raw) : raw;
      const d = saved?.document;
      return d && typeof d === 'object' && d.schemaVersion === 1 && typeof d.title === 'string'
        && d.page && ['nodes', 'edges', 'junctions', 'labels'].every(key => Array.isArray(d[key])) ? saved : null;
    } catch { return null; }
  }

  function draftHistory() {
    const raw = localStorage.getItem(DRAFT_HISTORY);
    try {
      const history = JSON.parse(raw || '[]');
      return Array.isArray(history) ? history.map(commands.parseDraft).filter(Boolean).slice(0, 5) : [];
    } catch { return []; }
  }

  function draftRecords() {
    const current = commands.parseDraft(localStorage.getItem(DRAFT)), seen = new Set();
    return [current, ...commands.draftHistory()].filter(saved => {
      if (!saved) return false;
      const key = JSON.stringify(saved.document);
      if (seen.has(key)) return false;
      seen.add(key); return true;
    });
  }

  function draftDate(saved) {
    const time = new Date(saved.time);
    return saved.time != null && Number.isFinite(Number(saved.time)) && Number.isFinite(time.getTime())
      ? time.toLocaleString() : '时间未知';
  }

  function renderDraftBanner() {
    if (BENCHMARK) { commands.$('draft-banner').hidden = true; return; }
    try {
      const current = localStorage.getItem(DRAFT);
      const records = commands.draftRecords();
      const recoverable = records.filter(saved => current !== state.ownedDraft
        || JSON.stringify(saved.document) !== JSON.stringify(state.doc));
      commands.$('draft-open').textContent = records.length ? `草稿 (${records.length})` : '草稿';
      commands.$('draft-description').textContent = recoverable.length
        ? `可恢复草稿：${recoverable[0].document.title || '未命名图纸'} · ${commands.draftDate(recoverable[0])}` : '';
      commands.$('draft-banner').hidden = state.draftBannerDismissed || !recoverable.length;
    } catch { commands.$('draft-banner').hidden = true; }
  }

  function saveDraft() {
    if (BENCHMARK) return true;
    try {
      const previous = localStorage.getItem(DRAFT), saved = commands.parseDraft(previous);
      if (previous !== state.ownedDraft && saved && JSON.stringify(saved.document) !== JSON.stringify(state.doc)) {
        const history = [saved, ...commands.draftHistory().filter(item =>
          JSON.stringify(item.document) !== JSON.stringify(saved.document))].slice(0, 5);
        // Preserve the previous document before replacing the active autosave.
        localStorage.setItem(DRAFT_HISTORY, JSON.stringify(history));
      }
      const next = JSON.stringify({ time: Date.now(), document: state.doc });
      localStorage.setItem(DRAFT, next); state.ownedDraft = next; state.draftError = false;
      commands.renderDraftBanner(); return true;
    } catch {
      state.draftError = true;
      commands.message('本机草稿未保存，原有草稿已保留。请使用“保存 JSON”保存当前图纸。');
      return false;
    }
  }

  function clearDraft() {
    if (BENCHMARK) return;
    try {
      if (state.ownedDraft !== null && localStorage.getItem(DRAFT) === state.ownedDraft) localStorage.removeItem(DRAFT);
      state.ownedDraft = null; state.draftError = false;
    } catch { /* Keep drafts written by another page or an earlier session. */ }
    commands.renderDraftBanner();
  }

  async function replaceDocument(next, preserveDraft = false, canApply = () => true) {
    if (!canApply()) return false;
    const started = BENCHMARK ? performance.now() : 0;
    const token = ++state.request, version = state.revision;
    const result = await commands.api('resolve', { document: next, sharedGlyphs: true });
    const resolved = BENCHMARK ? performance.now() : 0;
    if (token !== state.request || version !== state.revision || !canApply()) return false;
    state.edgeLabelsSupported = result.features?.includes('edgeLabels') || false;
    state.pipeMountsSupported = result.features?.includes('pipeMounts') || false;
    ++state.revision;
    state.doc = result.document; state.geometries = new Map(result.nodes.map(n => [n.id, n.geometry]));
    state.fontFamily = result.fontFamily; state.undo = []; state.redo = []; commands.clearSelection(); state.ports = [];
    state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.junctionPreview = null; state.reconnect = null; state.mode = 'select'; state.placement = null; state.dirty = false;
    state.clipboardPastes = 0;
    commands.$('object-search').value = ''; commands.$('object-kind').value = '';
    if (!preserveDraft && !BENCHMARK) commands.clearDraft();
    else state.ownedDraft = null;
    // Fit against the existing container before inserting the new SVG scene.
    // Reading clientWidth after attachment would force a full scene layout.
    commands.fit();
    const fitted = BENCHMARK ? performance.now() : 0;
    commands.render();
    const rendered = BENCHMARK ? performance.now() : 0;
    commands.status('图纸已打开 · 点击对象编辑'); commands.message('');
    if (BENCHMARK) state.loadMetrics = { resolveMs: resolved - started,
      applyRenderMs: rendered - fitted, fitMs: fitted - resolved,
      canvas: state.canvasMetrics };
    return true;
  }

  async function confirmReplace() {
    if (!state.dirty) return true;
    const dialog = commands.$('replace-dialog');
    dialog.returnValue = 'cancel';
    const answer = new Promise(resolve => dialog.addEventListener('close',
      () => resolve(dialog.returnValue === 'replace'), { once: true }));
    dialog.showModal();
    return answer;
  }

  function renderDocumentLoad() {
    commands.$('load-banner').hidden = !state.documentLoad;
    commands.$('load-description').textContent = state.documentLoad ? `正在载入：${state.documentLoad.label}…` : '';
  }

  function cancelDocumentLoad() {
    if (!state.documentLoad) return;
    state.documentLoad = null; commands.renderDocumentLoad();
    commands.status('载入已取消 · 当前图纸保留');
  }

  async function loadDocument(loader, label, key) {
    if (!state.doc || document.querySelector('dialog[open]')) return false;
    if (state.drag || state.placement || state.pendingPort || state.reconnect || state.pageLayoutBusy || state.spaceDown) {
      commands.message('请先完成当前操作或按 Esc，再载入图纸。'); return false;
    }
    if (state.documentLoad?.key === key) return false;
    const session = { label, key, version: state.revision };
    state.documentLoad = session; commands.renderDocumentLoad();
    const current = () => state.documentLoad === session && state.revision === session.version
      && !(state.drag || state.placement || state.pendingPort || state.reconnect || state.pageLayoutBusy || state.spaceDown)
      && !document.querySelector('dialog[open]');
    try {
      if (!await commands.confirmReplace() || !current()) return false;
      const next = await loader();
      if (!current()) return false;
      if (!await commands.replaceDocument(next, false, current)) return false;
      document.body.classList.remove('library-open');
      commands.status('已载入：' + label); return true;
    } catch (error) {
      if (current()) {
        commands.message('无法载入图纸：' + error.message);
        commands.status('载入失败 · 当前图纸与草稿保留');
      }
      return false;
    } finally {
      if (state.documentLoad === session) {
        state.documentLoad = null; commands.renderDocumentLoad();
      }
    }
  }

  function loadTemplate(template) {
    return commands.loadDocument(() => commands.api('templates/' + template.id), template.title, 'template:' + template.id);
  }

  function download(blob, filename) {
    const url = URL.createObjectURL(blob), a = commands.html('a'); a.href = url; a.download = filename;
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  function filename(extension) { return (state.doc.title || 'rrplot').replace(/[\\/:*?"<>|]/g, '_') + '.' + extension; }

  function renderSaveState() {
    commands.$('save-state').textContent = state.dirty ? (state.draftError ? '已修改 · 草稿未保存' : '已修改 · 本机草稿') : 'JSON 图纸 · 本机编辑';
    commands.$('save-json').disabled = state.saving || !state.doc || !!state.drag || state.pageLayoutBusy;
    commands.$('save-json').textContent = state.saving ? '保存中…' : '保存 JSON';
    if (state.pendingDownload?.version !== state.revision) state.pendingDownload = null;
    commands.$('download-banner').hidden = !state.pendingDownload;
  }

  function markJSONSaved(version) {
    if (version !== state.revision || state.drag) return false;
    // A clean template can coexist with an older recoverable draft at startup.
    if (state.dirty) commands.clearDraft();
    state.dirty = false; state.pendingDownload = null;
    return true;
  }

  async function saveJSON() {
    if (!state.doc || state.saving || document.querySelector('dialog[open]')) return;
    if (state.drag || state.pageLayoutBusy) return commands.message('请先完成拖动或页面排版，再保存图纸。');
    const snapshot = clone(state.doc), version = state.revision, name = commands.filename('json');
    state.saving = true; commands.renderSaveState();
    let writable = null;
    try {
      let handle = null;
      if (typeof window.showSaveFilePicker === 'function') {
        try {
          // Open before awaiting the server, while the click/shortcut is still active.
          handle = await window.showSaveFilePicker({ suggestedName: name, excludeAcceptAllOption: true,
            types: [{ description: 'rrplot JSON 图纸', accept: { 'application/json': ['.json'] } }] });
        } catch (error) {
          if (error.name === 'AbortError') { commands.status('已取消保存 · 图纸与本机草稿保留'); return; }
          if (!['SecurityError', 'NotSupportedError'].includes(error.name)) throw error;
        }
      }
      const result = await commands.api('resolve', { document: snapshot });
      const contents = JSON.stringify(result.document, null, 2);
      if (handle) {
        writable = await handle.createWritable();
        await writable.write(contents);
        await writable.close(); writable = null;
        const current = commands.markJSONSaved(version);
        commands.status(current ? '图纸 JSON 已保存：' + handle.name
          : '已保存操作开始时的图纸 · 当前图纸状态保留，请保存后续修改');
      } else {
        commands.download(new Blob([contents], { type: 'application/json' }), name);
        if (version === state.revision && !state.drag) {
          if (state.dirty) state.pendingDownload = { version };
          commands.status('JSON 下载已发起 · 请确认文件已保存');
        } else commands.status('已发起操作开始时图纸的 JSON 下载 · 当前图纸状态保留');
      }
    } catch (error) {
      if (writable) try { await writable.abort(); } catch { /* Preserve the original write error. */ }
      commands.message('保存 JSON 失败：' + error.message);
      commands.status('JSON 未保存完成 · 图纸与本机草稿保留');
    } finally { state.saving = false; commands.renderSaveState(); }
  }

  function confirmJSONDownload() {
    if (!state.pendingDownload || state.saving || document.querySelector('dialog[open]')) return;
    if (commands.markJSONSaved(state.pendingDownload.version)) commands.status('已确认 JSON 文件保存 · 后续修改将继续记录草稿');
    commands.renderSaveState();
  }

  function renderDraftList() {
    const root = commands.$('draft-list'); root.replaceChildren(); commands.$('draft-error').textContent = '';
    try {
      const records = commands.draftRecords();
      commands.$('draft-summary').textContent = records.length ? `共 ${records.length} 份可恢复草稿，点击恢复前会校验图纸。`
        : '暂无可恢复草稿。编辑后会自动记录当前图纸。';
      for (const saved of records) {
        const row = commands.html('div', undefined, 'draft-entry'), d = saved.document;
        row.append(commands.html('strong', d.title || '未命名图纸'), commands.html('span', commands.draftDate(saved), 'muted'),
          commands.html('span', `${d.nodes.length} 个设备 · ${d.edges.length} 条管路`, 'muted'));
        const button = commands.html('button', '恢复此草稿');
        button.addEventListener('click', () => commands.restoreDraft(clone(saved))); row.append(button); root.append(row);
      }
    } catch { commands.$('draft-error').textContent = '浏览器草稿不可用，请打开已保存的 JSON 文件。'; }
  }

  function showDrafts() {
    if (!state.doc || document.querySelector('dialog[open]')) return;
    if (state.drag || state.placement || state.pendingPort || state.reconnect || state.pageLayoutBusy) return commands.message('请先完成当前操作，再查看草稿。');
    commands.renderDraftList(); commands.$('drafts-dialog').showModal();
  }

  async function restoreDraft(saved) {
    if (state.restoringDraft || !commands.$('drafts-dialog').open) return;
    state.restoringDraft = true;
    try {
      if (!await commands.confirmReplace()) return;
      if (!commands.$('drafts-dialog').open) return;
      if (!await commands.replaceDocument(saved.document, true)) return;
      state.dirty = true; commands.saveDraft(); commands.render(); commands.renderDraftBanner();
      commands.$('drafts-dialog').close();
      commands.status(state.draftError ? '草稿已恢复 · 请保存 JSON' : '草稿已恢复 · 请保存 JSON 作为文件备份');
    } catch (error) { commands.$('draft-error').textContent = '恢复失败：' + error.message; }
    finally { state.restoringDraft = false; }
  }

  function closeDrafts() {
    if (state.restoringDraft) ++state.request;
    commands.$('drafts-dialog').close();
  }

  function bindFilesEvents() {
    commands.$('drafts-dialog').addEventListener('cancel', () => { if (state.restoringDraft) ++state.request; });
    commands.$('file-input').addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      event.target.value = '';
      await commands.loadDocument(async () => {
        if (file.size > 5000000) throw new Error('图纸文件超过 5 MB');
        return JSON.parse(await file.text());
      }, file.name, 'file:' + uid('load'));
    });
  }

  return { parseDraft, draftHistory, draftRecords, draftDate, renderDraftBanner, saveDraft, clearDraft, replaceDocument, confirmReplace, renderDocumentLoad, cancelDocumentLoad, loadDocument, loadTemplate, download, filename, renderSaveState, markJSONSaved, saveJSON, confirmJSONDownload, renderDraftList, showDrafts, restoreDraft, closeDrafts, bindFilesEvents };
}
