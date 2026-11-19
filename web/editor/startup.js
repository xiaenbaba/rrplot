import { monitorService } from '../service.js';
import { configureGlyphCapabilities } from '../geometry.js';
import { glyphImage } from '../inspector.js';
import { BENCHMARK, clone } from './config.js';

/** Catalog/template startup and isolated benchmark adapter.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createStartupController(state, commands) {
  async function init() {
    if (!BENCHMARK && !state.serviceMonitored) { state.serviceMonitored = true; monitorService(commands.$('service-state')); }
    try {
      const data = await Promise.all([commands.api('catalog'), commands.api('templates'), commands.api('templates/evi_ftvi')]);
      [state.catalog] = data;
      configureGlyphCapabilities(state.catalog);
      commands.$('palette').replaceChildren(); commands.$('templates').replaceChildren();
      for (const entry of state.catalog) {
        const b = commands.html('button', undefined, 'part-button'); b.dataset.part = entry.type; b.draggable = false;
        const icon = commands.html('span', undefined, 'part-icon');
        icon.append(glyphImage(entry.type, {}, '')); b.append(icon);
        const name = commands.html('span', entry.label); name.append(commands.html('small', entry.type)); b.append(name);
        b.addEventListener('click', event => {
          if (state.suppressedPaletteClick === b && event.detail !== 0) { state.suppressedPaletteClick = null; return; }
          state.mountPreview = null; state.placement = entry.type; state.mode = 'select'; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.reconnect = null; document.body.classList.remove('library-open'); commands.render(); commands.status('在画布点击放置：' + entry.label);
        });
        b.addEventListener('pointerdown', event => commands.beginPaletteDrag(event, entry.type, b));
        b.addEventListener('pointermove', commands.movePaletteDrag);
        b.addEventListener('pointerup', event => commands.endPaletteDrag(event));
        b.addEventListener('pointercancel', event => commands.endPaletteDrag(event, true));
        b.addEventListener('lostpointercapture', event => commands.endPaletteDrag(event, true));
        b.addEventListener('dragstart', event => { state.draggingPart = entry.type; event.dataTransfer.setData('text/rrplot-part', entry.type); });
        b.addEventListener('dragend', () => { state.draggingPart = null; state.mountPreview = null; if (state.doc) commands.renderMountPreview(); });
        commands.$('palette').append(b);
      }
      for (const template of data[1]) {
        const b = commands.html('button', template.title); b.dataset.template = template.id;
        b.addEventListener('click', () => commands.loadTemplate(template));
        commands.$('templates').append(b);
      }
      commands.filterPalette();
      commands.filterTemplates();
      await commands.replaceDocument(data[2], true);
      commands.requestFailure();
      commands.renderDraftBanner();
      if (BENCHMARK) parent.postMessage({ type: 'benchmark-ready' }, location.origin);
    } catch (error) { commands.requestFailure(error); commands.message(error.message); commands.status('服务未连接 · 可点击重新连接'); }
  }

  function bindBenchmarkEvents() {
    if (BENCHMARK) {
      let benchmarkBusy = false;
      window.addEventListener('message', async event => {
        if (event.origin !== location.origin || event.source !== parent || event.data?.type !== 'benchmark-run' || benchmarkBusy) return;
        benchmarkBusy = true;
        try {
          const { runBenchmark } = await import('../benchmark.js');
          const result = await runBenchmark({
            load: d => commands.replaceDocument(d, true), render: () => commands.renderCanvas(),
            select: () => { commands.setSelection('node', state.doc.nodes[Math.floor(state.doc.nodes.length / 2)].id); commands.render(); },
            move: () => { const before = clone(state.doc); state.doc.nodes[Math.floor(state.doc.nodes.length / 2)].x += 10; commands.finishEdit(before, { deferRefresh: true }); },
            undo: () => commands.history('undo', { deferRefresh: true }), elements: () => state.svg.querySelectorAll('*').length,
            loadMetrics: () => state.loadMetrics
          });
          parent.postMessage({ type: 'benchmark-result', result }, location.origin);
        } catch (error) { parent.postMessage({ type: 'benchmark-error', error: error.message }, location.origin); }
        finally { benchmarkBusy = false; }
      });
    }
  }

  return { init, bindBenchmarkEvents };
}
