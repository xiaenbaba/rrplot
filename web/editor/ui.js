import { requestResource } from '../requests.js';
import { createGlyphCache } from '../glyphs.js';
import { NS } from './config.js';

/** DOM primitives, notifications, requests and recovery.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createUiController(state, commands) {
  const $ = id => document.getElementById(id);

  function html(tag, text, className) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (className) e.className = className;
    return e;
  }

  function shape(tag, attrs = {}, parent = state.svg) {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => { if (v !== undefined) e.setAttribute(k, v); });
    if (state.canvasPass && parent === state.svg) state.canvasRenderer.place(e); else parent.append(e);
    return e;
  }

  function status(text) { commands.$('status').textContent = text; }

  function message(text) {
    clearTimeout(state.messageTimer);
    commands.$('message').textContent = text;
    commands.$('message').hidden = !text;
    if (text) state.messageTimer = setTimeout(() => { commands.$('message').hidden = true; }, 7000);
  }

  async function api(path, body) {
    if (path === 'resolve') body = { ...body, sharedGlyphs: true };
    if (body?.document?.nodes?.some(node => node.mount) && !state.pipeMountsSupported)
      throw new Error('阀件挂接需要新版服务，请保存图纸后重启服务，再刷新页面。');
    if (body?.document?.labels?.some(label => label.edgeId) && !state.edgeLabelsSupported)
      throw new Error('管路状态点需要新版服务，请保存当前图纸后重启 start-web.cmd，再刷新页面。');
    const result = await requestResource('/api/' + path, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }, { timeoutMs: path.startsWith('export/') || path === 'preview' ? 60000 : 20000 });
    if (path === 'resolve') { state.hydrateGlyphs ||= createGlyphCache(); return state.hydrateGlyphs(result); }
    return result;
  }

  function requestFailure(error = null) {
    const banner = commands.$('request-banner');
    banner.hidden = !error;
    if (error) commands.$('request-description').textContent = error.message;
  }

  async function retryService() {
    const button = commands.$('request-retry');
    if (button.disabled) return;
    button.disabled = true;
    try { if (state.doc) await commands.refresh(); else await commands.init(); }
    finally { button.disabled = false; }
  }

  return { $, html, shape, status, message, api, requestFailure, retryService };
}
