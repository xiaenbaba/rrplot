import { clone } from './config.js';

/** Formal preview, output settings and export lifecycle.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createExportController(state, commands) {
  function exportOptions() {
    const format = commands.$('export-format').value;
    if (!['svg', 'png', 'pdf'].includes(format)) throw new Error('请选择 SVG、PNG 或 PDF 格式。');
    const dpi = format === 'png' ? Number(commands.$('export-dpi').value) : 140;
    if (!Number.isInteger(dpi) || dpi < 72 || dpi > 600) throw new Error('PNG 分辨率须为 72～600 之间的整数。');
    const width = state.doc.page.width * dpi / 100, height = state.doc.page.height * dpi / 100;
    if (format === 'png' && width * height > 40000000) throw new Error('PNG 超过 4000 万像素，请降低 DPI 或先缩小页面。');
    return { format, dpi, width: Math.floor(width), height: Math.floor(height) };
  }

  function renderPreviewState() {
    const ready = !!state.previewSession?.ready;
    commands.$('preview-open').disabled = !state.doc || !!state.previewSession?.loading;
    commands.$('preview-open').textContent = state.previewSession?.loading ? '预览中…' : '预览';
    commands.$('preview-minus').disabled = !ready || state.previewSession.scale <= .1;
    commands.$('preview-plus').disabled = !ready || state.previewSession.scale >= 8;
    commands.$('preview-fit').disabled = !ready;
    commands.$('preview-actual').disabled = !ready;
    commands.$('preview-retry').hidden = !state.previewSession?.error;
    commands.$('preview-scale').textContent = ready ? Math.round(state.previewSession.scale * 100) + '%' : '—';
  }

  function releasePreviewImage(session = state.previewSession) {
    if (session?.url) { URL.revokeObjectURL(session.url); session.url = null; }
    commands.$('preview-image').removeAttribute('src'); commands.$('preview-image').hidden = true;
  }

  function closePreview() {
    commands.releasePreviewImage(); state.previewSession = null; commands.renderPreviewState();
    if (commands.$('preview-dialog').open) commands.$('preview-dialog').close();
  }

  function resizePreviewImage() {
    const s = state.previewSession;
    if (!s?.ready) return;
    commands.$('preview-image').style.width = s.width * s.scale + 'px';
    commands.$('preview-image').style.height = s.height * s.scale + 'px';
    commands.renderPreviewState();
  }

  function fitPreview() {
    const s = state.previewSession, viewport = commands.$('preview-viewport');
    if (!s?.ready) return;
    s.fit = true;
    s.scale = Math.min(8, Math.max(1, viewport.clientWidth - 40) / s.width,
      Math.max(1, viewport.clientHeight - 40) / s.height);
    commands.resizePreviewImage(); viewport.scrollLeft = 0; viewport.scrollTop = 0;
  }

  function zoomPreview(scale, anchor) {
    const s = state.previewSession, viewport = commands.$('preview-viewport'), image = commands.$('preview-image');
    if (!s?.ready || !Number.isFinite(scale)) return;
    const bounds = viewport.getBoundingClientRect(), before = image.getBoundingClientRect();
    const point = anchor || [bounds.left + viewport.clientWidth / 2, bounds.top + viewport.clientHeight / 2];
    const fraction = [(point[0] - before.left) / before.width, (point[1] - before.top) / before.height]
      .map(value => Math.max(0, Math.min(1, value)));
    s.fit = false; s.scale = Math.max(.1, Math.min(8, scale)); commands.resizePreviewImage();
    const after = image.getBoundingClientRect();
    viewport.scrollLeft += after.left + fraction[0] * after.width - point[0];
    viewport.scrollTop += after.top + fraction[1] * after.height - point[1];
  }

  async function showPreview() {
    if (!state.doc || state.previewSession?.loading || state.previewSession?.ready) return;
    const dialog = commands.$('preview-dialog');
    if (document.querySelector('dialog[open]') && !dialog.open) return;
    if (state.drag || state.pageLayoutBusy || state.placement || state.pendingPort || state.reconnect) return commands.message('请先完成当前编辑操作，再预览图纸。');
    commands.releasePreviewImage();
    const snapshot = clone(state.doc), session = { version: state.revision, loading: true, ready: false, scale: 1 };
    state.previewSession = session;
    commands.$('preview-caption').textContent = snapshot.title + ` · 纸面 ${snapshot.page.width} × ${snapshot.page.height}`;
    commands.$('preview-message').textContent = '正在生成正式预览…'; commands.$('preview-message').hidden = false;
    commands.renderPreviewState();
    if (!dialog.open) dialog.showModal();
    commands.status('正在生成正式预览…');
    try {
      const blob = await commands.api('preview', { document: snapshot });
      if (session !== state.previewSession) return;
      if (session.version !== state.revision || state.drag) throw new Error('图纸已变化，请重新生成预览。');
      session.url = URL.createObjectURL(blob);
      const image = commands.$('preview-image'); image.src = session.url;
      await image.decode();
      if (session !== state.previewSession) return;
      if (session.version !== state.revision || state.drag) throw new Error('图纸已变化，请重新生成预览。');
      if (!image.naturalWidth || !image.naturalHeight) throw new Error('预览图片未能正确加载，请重试。');
      session.width = image.naturalWidth; session.height = image.naturalHeight; session.ready = true;
      image.hidden = false; commands.$('preview-message').hidden = true;
      commands.fitPreview(); commands.status('正式预览已生成 · 可缩放或滚动查看');
    } catch (error) {
      if (session !== state.previewSession) return;
      commands.releasePreviewImage(session); session.error = true;
      commands.$('preview-message').textContent = '预览失败：' + error.message;
      commands.status('预览未生成 · 图纸与本机草稿保留');
    } finally {
      if (session === state.previewSession) { session.loading = false; commands.renderPreviewState(); }
    }
  }

  function renderExportState() {
    commands.$('export-open').disabled = state.exporting || !state.doc;
    commands.$('export-open').textContent = state.exporting ? '导出中…' : '导出 ↓';
    commands.$('export-format').disabled = state.exporting;
    commands.$('export-dpi').disabled = state.exporting || commands.$('export-format').value !== 'png';
    commands.$('export-png').hidden = commands.$('export-format').value !== 'png';
    commands.$('export-close').textContent = state.exporting ? '关闭' : '取消';
    commands.$('export-error').textContent = '';
    commands.$('export-submit').disabled = state.exporting || !state.doc;
    commands.$('export-submit').textContent = state.exporting ? '正在生成…' : '导出文件';
    if (!state.doc) return;
    try {
      const options = commands.exportOptions();
      commands.$('export-summary').textContent = state.exporting ? '正在生成点击导出时的图纸，完成后将发起下载；可关闭此窗口继续编辑。'
        : options.format === 'png' ? `预计尺寸：${options.width} × ${options.height} 像素（${options.dpi} DPI）。`
        : '矢量格式可缩放，清晰度不受 PNG 分辨率设置影响。';
    } catch (error) {
      commands.$('export-summary').textContent = '';
      commands.$('export-error').textContent = error.message;
      commands.$('export-submit').disabled = true;
    }
  }

  function showExportSettings() {
    if (!state.doc || state.exporting || document.querySelector('dialog[open]')) return;
    if (state.drag || state.pageLayoutBusy || state.placement || state.pendingPort || state.reconnect) return commands.message('请先完成当前编辑操作，再导出图纸。');
    commands.renderExportState(); commands.$('export-dialog').showModal();
  }

  async function exportDiagram() {
    if (!state.doc || state.exporting || !commands.$('export-dialog').open) return;
    if (state.drag || state.pageLayoutBusy || state.placement || state.pendingPort || state.reconnect) return;
    let options;
    try { options = commands.exportOptions(); }
    catch { commands.renderExportState(); return; }
    const snapshot = clone(state.doc), version = state.revision, name = commands.filename(options.format);
    state.exporting = true; commands.renderExportState(); commands.status('正在生成导出文件…');
    try {
      const blob = await commands.api('export/' + options.format, { document: snapshot, dpi: options.dpi });
      commands.download(blob, name);
      if (commands.$('export-dialog').open) commands.$('export-dialog').close();
      commands.status(version === state.revision ? options.format.toUpperCase() + ' 下载已发起 · 继续编辑请保存 JSON'
        : '操作开始时的图纸下载已发起 · 后续修改请重新导出');
    } catch (error) {
      state.exporting = false; commands.renderExportState();
      commands.$('export-error').textContent = error.message;
      if (!commands.$('export-dialog').open) commands.message('导出失败：' + error.message);
      commands.status('导出失败 · 图纸与本机草稿保留');
      return;
    } finally {
      if (state.exporting) { state.exporting = false; commands.renderExportState(); }
    }
  }

  function bindExportEvents() {
    commands.$('export-format').addEventListener('change', commands.renderExportState);
    commands.$('export-dpi').addEventListener('input', commands.renderExportState);
    commands.$('export-form').addEventListener('submit', async event => { event.preventDefault(); await commands.exportDiagram(); });
    commands.$('preview-dialog').addEventListener('close', () => { if (!commands.$('preview-dialog').open) commands.closePreview(); });
    commands.$('preview-viewport').addEventListener('wheel', event => {
      if (!event.ctrlKey || !event.deltaY || !state.previewSession?.ready) return;
      event.preventDefault();
      commands.zoomPreview(state.previewSession.scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15), [event.clientX, event.clientY]);
    }, { passive: false });
    new ResizeObserver(() => { if (state.previewSession?.fit) commands.fitPreview(); }).observe(commands.$('preview-viewport'));
  }

  return { exportOptions, renderPreviewState, releasePreviewImage, closePreview, resizePreviewImage, fitPreview, zoomPreview, showPreview, renderExportState, showExportSettings, exportDiagram, bindExportEvents };
}
