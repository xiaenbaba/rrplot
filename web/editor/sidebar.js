import { objectIndex, filterObjects } from '../objects.js';
import { inspectDiagram } from '../checks.js';
import { clone } from './config.js';

/** Library filtering, object navigation and diagram checks.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createSidebarController(state, commands) {
  function objectName(ref) {
    const item = state.doc[{ node: 'nodes', edge: 'edges', junction: 'junctions', label: 'labels' }[ref.kind]].find(i => i.id === ref.id);
    if (ref.kind === 'edge') return '管路：' + commands.refName(item.source) + ' → ' + commands.refName(item.target);
    return ref.kind === 'node' ? '设备：' + item.title : ref.kind === 'label' ? '文字：' + item.text : '三通 · ' + item.id.slice(-5);
  }

  function locateObject(ref, additive = false) {
    if (state.drag || state.reconnect || state.pendingPort) return commands.message('请先完成当前连接或拖动，或按 Esc 取消，再定位对象。');
    state.mode = 'select'; state.placement = null; state.reconnect = null; state.pendingPort = null; state.connectionVertices = []; state.previewTarget = null; state.ports = [];
    commands.setSelection(ref.kind, ref.id, additive); commands.render();
    let box = commands.selectionCandidates().find(item => item.kind === ref.kind && item.id === ref.id)?.box;
    if (ref.kind === 'edge') {
      const points = commands.edgePoints(state.doc.edges.find(item => item.id === ref.id)), xs = points.map(p => p[0]), ys = points.map(p => p[1]);
      box = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
    }
    if (box) {
      const [x, y, w, h] = box, ratio = state.svg.clientWidth / state.svg.clientHeight;
      state.view.w = Math.max(state.view.w, w + 80, (h + 80) * ratio); state.view.h = state.view.w / ratio;
      state.view.x = x + w / 2 - state.view.w / 2; state.view.y = y + h / 2 - state.view.h / 2; commands.updateView();
    }
    document.body.classList.remove('library-open'); document.body.classList.add('properties-open');
    document.querySelector('.properties').scrollTop = 0;
    state.svg.focus({ preventScroll: true }); commands.status('已定位：' + commands.objectName(ref));
  }

  function locateIssue(ref) {
    commands.$('checks-dialog').close(); commands.locateObject(ref);
  }

  function renderObjectList() {
    if (!state.doc || commands.$('objects-panel').hidden) return;
    const entries = objectIndex(state.doc, state.catalog), found = filterObjects(entries, commands.$('object-search').value, commands.$('object-kind').value);
    commands.$('object-count').textContent = `显示 ${Math.min(found.length, 200)} / 匹配 ${found.length} / 共 ${entries.length} 项`;
    const root = commands.$('object-list'); root.replaceChildren();
    for (const entry of found.slice(0, 200)) {
      const active = commands.selected(entry.kind, entry.id);
      const button = commands.html('button', undefined, 'object-entry' + (active ? ' active' : ''));
      button.dataset.kind = entry.kind; button.dataset.id = entry.id;
      button.setAttribute('aria-pressed', active);
      button.title = `${entry.type}：${entry.title}\nID：${entry.id}\n${entry.detail}`;
      button.append(commands.html('strong', `${entry.type} · ${entry.title}`), commands.html('small', entry.id));
      button.addEventListener('click', event => commands.locateObject(entry, event.shiftKey)); root.append(button);
    }
    if (!found.length) root.append(commands.html('p', entries.length ? '没有匹配的对象，请调整搜索或类型。' : '图纸为空，请从图元库添加设备。', 'muted'));
    if (found.length > 200) root.append(commands.html('p', '仅显示前 200 项，请搜索名称或 ID 缩小范围。', 'muted'));
  }

  function filterPalette() {
    const words = commands.$('part-search').value.normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean);
    let count = 0;
    document.querySelectorAll('[data-part]').forEach(button => {
      button.hidden = !words.every(word => button.textContent.normalize('NFKC').toLowerCase().includes(word));
      if (!button.hidden) count++;
    });
    commands.$('part-count').textContent = `显示 ${count} / 共 ${state.catalog.length} 种图元`;
    commands.$('part-empty').hidden = count > 0;
  }

  function filterTemplates() {
    const words = commands.$('template-search').value.normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean);
    const buttons = [...document.querySelectorAll('[data-template]')];
    let count = 0;
    for (const button of buttons) {
      const text = `${button.textContent} ${button.dataset.template}`.normalize('NFKC').toLowerCase();
      button.hidden = !words.every(word => text.includes(word));
      if (!button.hidden) count++;
    }
    commands.$('template-count').textContent = `显示 ${count} / 共 ${buttons.length} 个模板`;
    commands.$('template-empty').hidden = count > 0;
  }

  async function runChecks() {
    if (state.reconnect || state.drag || state.pendingPort) return commands.message('请先完成当前连接或拖动，或按 Esc 取消，再检查图纸。');
    const version = state.revision;
    commands.status('正在检查图纸…');
    let result;
    try { result = await commands.api('resolve', { document: clone(state.doc) }); }
    catch (error) { commands.status('检查未完成，请查看提示'); throw error; }
    if (version !== state.revision || state.drag || state.reconnect || state.pendingPort) {
      commands.status('图纸已变化，请重新检查');
      return commands.message('图纸或当前操作已变化，请完成后重新点击“检查”。');
    }
    state.geometries = new Map(result.nodes.map(n => [n.id, n.geometry])); state.fontFamily = result.fontFamily; commands.renderCanvas();
    const routes = new Map(state.doc.edges.map(edge => [edge.id, commands.edgePoints(edge)]));
    const issues = inspectDiagram(state.doc, { nodes: commands.currentNodes(), routes, bounds: commands.selectionCandidates(), visual: true });
    const root = commands.$('checks-results'); root.replaceChildren();
    commands.$('checks-summary').textContent = issues.length ? `发现 ${issues.length} 项待核对，点击结果定位并查看属性。排版提示按包围框估算，不修改图纸。` : '未发现连接、页面越界或排版提示。';
    for (const issue of issues.slice(0, 100)) {
      const button = commands.html('button', undefined, 'check-result');
      button.append(commands.html('strong', (issue.severity === 'hint' ? '排版提示 · ' : '') + issue.title), commands.html('span', commands.objectName(issue.ref), 'check-object'), commands.html('span', issue.detail, 'check-detail'), commands.html('span', '定位 →', 'check-locate'));
      button.addEventListener('click', () => commands.locateIssue(issue.ref)); root.append(button);
    }
    if (issues.length > 100) root.append(commands.html('p', '仅显示前 100 项；修改后再次检查可查看剩余结果。', 'muted'));
    if (!commands.$('checks-dialog').open) commands.$('checks-dialog').showModal();
    commands.status(issues.length ? `检查完成 · ${issues.length} 项待核对` : '检查完成 · 未发现问题');
  }

  function bindSidebarEvents() {
    const libraryPanes = [['show-parts', 'library-parts'], ['show-templates', 'templates-panel'], ['show-objects', 'objects-panel']];
    for (const [id] of libraryPanes) {
      commands.$(id).addEventListener('click', () => {
        for (const [buttonId, paneId] of libraryPanes) {
          const active = buttonId === id;
          commands.$(paneId).hidden = !active;
          commands.$(buttonId).classList.toggle('active', active); commands.$(buttonId).setAttribute('aria-pressed', active);
        }
        commands.renderObjectList();
      });
    }
    commands.$('object-search').addEventListener('input', commands.renderObjectList);
    commands.$('object-kind').addEventListener('change', commands.renderObjectList);
    commands.$('part-search').addEventListener('input', commands.filterPalette);
    commands.$('template-search').addEventListener('input', commands.filterTemplates);
  }

  return { objectName, locateObject, locateIssue, renderObjectList, filterPalette, filterTemplates, runChecks, bindSidebarEvents };
}
