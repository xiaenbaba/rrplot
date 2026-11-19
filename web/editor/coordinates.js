import { endpoint, route } from '../geometry.js';
import { clone } from './config.js';

/** Coordinate dialog, local form history, clipboard and route preview.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createCoordinatesController(state, commands) {
  function showConnectionCoordinates() {
    if (!state.doc || state.mode !== 'connect' || !state.pendingPort || commands.connectionToolsBusy() || !state.connectionVertices.length
      || document.querySelector('dialog[open]')) return;
    state.connectionCoordinates = { revision: state.revision, source: clone(state.pendingPort), vertices: clone(state.connectionVertices), controls: [] };
    commands.openCoordinateForm();
  }

  function showEdgeCoordinates(id) {
    if (!state.doc || commands.pipeActionsBusy() || document.querySelector('dialog[open]') || state.multiSelection.length !== 1
      || !commands.selected('edge', id)) return;
    const edge = state.doc.edges.find(item => item.id === id);
    if (!edge) return;
    state.connectionCoordinates = { kind: 'edge', revision: state.revision, edge: clone(edge), vertices: clone(edge.vertices),
      selection: clone(state.multiSelection), controls: [] };
    commands.openCoordinateForm();
  }

  function openCoordinateForm() {
    const session = state.connectionCoordinates;
    session.formUndo = []; session.formRedo = [];
    commands.$('connection-coordinate-import').open = false; commands.$('connection-coordinate-text').value = '';
    commands.$('connection-coordinate-export').open = false;
    commands.coordinateImportStatus();
    commands.$('connection-coordinates-heading').textContent = session.kind === 'edge' ? '编辑管路折点坐标' : '编辑临时折点坐标';
    commands.$('connection-coordinate-note').textContent = session.kind === 'edge'
      ? '应用后可 Ctrl+Z 一次撤销。端口、样式和状态点附着关系保留，状态点沿新走线跟随；取消或 Esc 保留原走线。'
      : '应用后继续连线，最终完成时随整条管路保存和撤销；取消或 Esc 保留原折点。';
    commands.renderCoordinateRows(session.vertices);
    commands.$('connection-coordinates-dialog').showModal();
    (session.controls[0]?.[0] || commands.$('connection-coordinate-add')).focus();
  }

  function renderCoordinateRows(vertices) {
    const session = state.connectionCoordinates;
    const root = commands.$('connection-coordinate-list'); root.replaceChildren(); session.controls = []; session.rowErrors = [];
    session.rowElements = []; session.previewPoints = [];
    session.activeIndex = vertices.length ? Math.max(0, Math.min(session.activeIndex ?? 0, vertices.length - 1)) : -1;
    const navigator = commands.$('connection-coordinate-jump'); navigator.replaceChildren();
    (vertices.length ? vertices.map((_, index) => [`折点 ${index + 1} / ${vertices.length}`, index])
      : [['无折点', '']]).forEach(([label, value]) => {
      const option = commands.html('option', label); option.value = value; navigator.append(option);
    });
    const rows = session.controls;
    vertices.forEach((point, index) => {
      const row = commands.html('fieldset', undefined, 'connection-coordinate-row');
      row.append(commands.html('legend', `折点 ${index + 1}`)); root.append(row); session.rowElements.push(row);
      const pair = commands.html('div', undefined, 'field-pair'); row.append(pair);
      const controls = point.map((value, axis) => {
        const input = commands.field(pair, axis ? 'Y' : 'X', value, () => {},
          { type: 'number', min: -100000, max: 100000, required: true, transient: true, deferValidation: true });
        input.setAttribute('aria-label', `折点 ${index + 1} ${axis ? 'Y' : 'X'}`);
        input.setAttribute('aria-describedby', `coordinate-row-error-${index}`);
        input.addEventListener('focus', () => {
          if (state.connectionCoordinates === session && session.controls === rows) {
            session.activeAxis = axis; session.inputGroup = null; commands.highlightCoordinateRow(session, index);
          }
        });
        input.addEventListener('input', () => {
          if (state.connectionCoordinates !== session || session.controls !== rows) return;
          commands.recordCoordinateChange(session, input); commands.renderCoordinatePreview();
        });
        for (const event of ['change', 'blur']) input.addEventListener(event, () => {
          if (state.connectionCoordinates === session && session.controls === rows) session.inputGroup = null;
        });
        return input;
      });
      session.controls.push(controls);
      const actions = commands.html('div', undefined, 'button-row connection-coordinate-actions'); row.append(actions);
      const insert = commands.inspectorButton(actions, '在此前插入', () => commands.changeCoordinateRows(session, index, false));
      insert.type = 'button'; insert.disabled = vertices.length >= 100;
      insert.setAttribute('aria-label', `在折点 ${index + 1} 前插入`);
      const remove = commands.inspectorButton(actions, '删除此折点', () => commands.changeCoordinateRows(session, index, true));
      remove.type = 'button'; remove.setAttribute('aria-label', `删除折点 ${index + 1}`);
      const order = commands.html('div', undefined, 'button-row connection-coordinate-actions'); row.append(order);
      for (const [caption, delta] of [['上移', -1], ['下移', 1]]) {
        const button = commands.inspectorButton(order, caption, () => commands.reorderCoordinateRows(session, rows, index, delta));
        button.type = 'button'; button.disabled = index + delta < 0 || index + delta >= vertices.length;
        button.setAttribute('aria-label', `${caption}折点 ${index + 1}`);
      }
      const error = commands.html('p', '', 'coordinate-row-error');
      error.id = `coordinate-row-error-${index}`; error.setAttribute('role', 'status');
      row.append(error); session.rowErrors.push(error);
    });
    commands.$('connection-coordinate-add').disabled = vertices.length >= 100;
    commands.$('connection-coordinate-summary').textContent = vertices.length
      ? `共 ${vertices.length} 个折点 · 坐标、增删和排序将在应用后生效`
      : session.kind === 'edge' ? '无手动折点 · 应用后使用自动走线，可添加折点指定路径'
        : '无临时折点 · 应用后恢复自动走线，保留连线起点';
    commands.$('connection-coordinate-error').textContent = '';
    commands.recordCoordinateChange(session);
    commands.renderCoordinatePreview();
  }

  function coordinateImportStatus(text = '', error = false) {
    commands.$('connection-coordinate-import-status').textContent = text;
    commands.$('connection-coordinate-import-status').setAttribute('data-error', String(error));
  }

  function parseCoordinateText(text) {
    if (text.length > 20000) throw new Error('坐标文本过长，请保留最多 100 行坐标。');
    const lines = text.split(/\r\n?|\n/).map((line, index) => ({ text: line.trim(), line: index + 1 }))
      .filter(line => line.text);
    if (!lines.length) throw new Error('请先粘贴坐标；清空折点请使用“清空列表”。');
    if (lines.length > 100) throw new Error('最多载入 100 个折点，请减少坐标行数。');
    return lines.map(({ text, line }) => {
      const pair = /[,，]/.test(text) ? text.split(/[,，]/).map(value => value.trim())
        : text.includes('\t') ? text.split('\t').map(value => value.trim()) : text.split(/\s+/);
      if (pair.length !== 2 || pair.some(value => !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value)))
        throw new Error(`第 ${line} 行：请填写两个数字，用制表符、逗号或空格分隔 X/Y。`);
      if (pair.some(value => !Number.isFinite(Number(value)) || Math.abs(Number(value)) > 100000))
        throw new Error(`第 ${line} 行：坐标须在 -100000～100000 范围内。`);
      return pair.map(value => value.replace(/^\+/, '').replace(/\.(?=e|$)/i, ''));
    });
  }

  function importCoordinateRows() {
    const session = state.connectionCoordinates;
    if (!session || !commands.$('connection-coordinates-dialog').open) return;
    let vertices;
    try {
      const edge = commands.coordinateSessionEdge(session);
      vertices = commands.parseCoordinateText(commands.$('connection-coordinate-text').value);
      const numbers = vertices.map(point => point.map(Number));
      if (!edge || JSON.stringify(numbers) !== JSON.stringify(session.vertices)) commands.validateCoordinateVertices(numbers, edge);
    } catch (error) { commands.coordinateImportStatus(`未载入：${error.message}`, true); return; }
    commands.recordCoordinateChange(session); session.activeIndex = 0; session.activeAxis = 0;
    commands.renderCoordinateRows(vertices);
    commands.$('connection-coordinate-import').open = false;
    commands.coordinateImportStatus(`已载入 ${vertices.length} 个折点 · 仅替换窗口列表，可撤销输入，应用后生效。`);
    session.controls[0][0].focus(); session.controls[0][0].scrollIntoView({ block: 'center', inline: 'nearest' });
  }

  function resetCoordinateCopy(session) {
    session.copyRequest = null;
    commands.$('connection-coordinate-output').value = '';
    commands.$('connection-coordinate-copy-status').textContent = '';
    commands.$('connection-coordinate-copy').disabled = !session.controls.length;
  }

  async function copyCoordinateRows() {
    const session = state.connectionCoordinates;
    if (!session || !commands.$('connection-coordinates-dialog').open || session.copyRequest) return;
    const status = commands.$('connection-coordinate-copy-status'), output = commands.$('connection-coordinate-output');
    try { commands.coordinateSessionEdge(session); commands.readCoordinateVertices(session); }
    catch (error) {
      output.value = ''; status.textContent = `未复制：${error.message}`;
      commands.markCoordinateError(session, error, true); return;
    }
    if (!session.controls.length) { status.textContent = '无手动折点可复制。'; return; }
    const text = session.controls.map(row => row.map(input => input.value).join('\t')).join('\n');
    const request = {}; session.copyRequest = request;
    output.value = text; commands.$('connection-coordinate-copy').disabled = true;
    const current = () => {
      if (state.connectionCoordinates !== session || session.copyRequest !== request
        || !commands.$('connection-coordinates-dialog').open) return false;
      try { commands.coordinateSessionEdge(session); return true; }
      catch { commands.resetCoordinateCopy(session); return false; }
    };
    const fallback = () => {
      output.focus(); output.select();
      status.textContent = '坐标文本已生成并选中，请按 Ctrl+C 复制。';
    };
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) { fallback(); return; }
      await navigator.clipboard.writeText(text);
      if (current()) status.textContent = `已复制 ${session.controls.length} 个折点 · 可粘贴为表格两列或载入另一条管路。`;
    } catch { if (current()) fallback(); }
    finally { if (current()) { session.copyRequest = null; commands.$('connection-coordinate-copy').disabled = false; } }
  }

  function coordinateFormState(session) {
    return { vertices: session.controls.map(row => row.map(input => input.value)),
      index: session.activeIndex, axis: session.activeAxis ?? 0 };
  }

  function renderCoordinateHistory(session) {
    commands.$('connection-coordinate-undo').disabled = !session.formUndo.length;
    commands.$('connection-coordinate-redo').disabled = !session.formRedo.length;
  }

  function recordCoordinateChange(session, group = null) {
    if (session.restoringForm) return;
    const next = commands.coordinateFormState(session), before = session.formCurrent;
    if (before && JSON.stringify(before.vertices) !== JSON.stringify(next.vertices)) {
      if (!group || group !== session.inputGroup) {
        session.formUndo.push(clone(before));
        if (session.formUndo.length > 100) session.formUndo.shift();
      }
      session.formRedo = [];
    }
    session.formCurrent = next; session.inputGroup = group; commands.renderCoordinateHistory(session);
  }

  function coordinateFormHistory(direction) {
    const session = state.connectionCoordinates;
    if (!session || !commands.$('connection-coordinates-dialog').open) return;
    try { commands.coordinateSessionEdge(session); }
    catch (error) { commands.$('connection-coordinate-error').textContent = error.message; return; }
    commands.recordCoordinateChange(session);
    const from = direction === 'undo' ? session.formUndo : session.formRedo;
    const to = direction === 'undo' ? session.formRedo : session.formUndo;
    if (!from.length) return;
    to.push(commands.coordinateFormState(session));
    const savedForm = from.pop(); session.restoringForm = true;
    session.activeIndex = savedForm.index; session.activeAxis = savedForm.axis;
    try { commands.renderCoordinateRows(savedForm.vertices); }
    finally { session.restoringForm = false; }
    session.formCurrent = commands.coordinateFormState(session); session.inputGroup = null;
    commands.renderCoordinateHistory(session);
    const input = session.controls[session.activeIndex]?.[session.activeAxis];
    if (input) { input.focus(); input.scrollIntoView({ block: 'center', inline: 'nearest' }); }
    else commands.$('connection-coordinate-add').focus();
  }

  function coordinateSessionEdge(session) {
    const edge = session.kind === 'edge' && state.doc?.edges.find(item => item.id === session.edge.id);
    const stale = session.kind === 'edge'
      ? commands.pipeActionsBusy() || !edge || JSON.stringify(edge) !== JSON.stringify(session.edge)
        || JSON.stringify(state.multiSelection) !== JSON.stringify(session.selection)
      : state.mode !== 'connect' || commands.connectionToolsBusy() || !commands.eqRef(state.pendingPort, session.source)
        || JSON.stringify(state.connectionVertices) !== JSON.stringify(session.vertices);
    if (!state.doc || state.revision !== session.revision || stale)
      throw new Error('连线或图纸已变化，请关闭窗口后重新编辑。');
    return edge;
  }

  function readCoordinateVertices(session) {
    return session.controls.map((controls, index) => controls.map((input, axis) => {
      if (input.value === '' || !input.checkValidity() || !Number.isFinite(Number(input.value))) {
        throw Object.assign(new Error(`折点 ${index + 1}：请输入 -100000～100000 范围内的坐标。`),
          { coordinateIndex: index, coordinateAxis: axis });
      }
      return Number(input.value);
    }));
  }

  function validateCoordinateVertices(vertices, edge) {
    vertices.forEach((point, index) => {
      try {
        commands.connectionVertexPoint(point, index, vertices, false, edge ? edge.source : state.pendingPort);
        if (edge && index === vertices.length - 1
          && point.every((value, axis) => Math.abs(value - endpoint(edge.target, commands.currentNodes(), state.doc.junctions).point[axis]) < 1e-6))
          throw new Error('折点与终点重合，请选择其他位置。');
      } catch (error) {
        throw Object.assign(new Error(`折点 ${index + 1}：${error.message}`), { coordinateIndex: index });
      }
    });
    if (edge) commands.checkConnection({ ...edge, vertices }, edge.id);
  }

  function markCoordinateError(session, error, focus = false) {
    const index = error.coordinateIndex, controls = session.controls[index];
    if (!controls || !Number.isInteger(index)) return;
    session.rowErrors[index].textContent = error.message;
    controls.forEach((input, axis) => input.setAttribute('aria-invalid',
      String(error.coordinateAxis === undefined || error.coordinateAxis === axis)));
    if (focus) {
      const input = controls[error.coordinateAxis ?? 0];
      input.focus(); input.scrollIntoView({ block: 'center', inline: 'nearest' });
    }
  }

  function highlightCoordinateRow(session, index) {
    session.activeIndex = index;
    if (session.formCurrent) { session.formCurrent.index = index; session.formCurrent.axis = session.activeAxis ?? 0; }
    commands.$('connection-coordinate-previous').disabled = index <= 0;
    commands.$('connection-coordinate-next').disabled = index < 0 || index >= session.controls.length - 1;
    commands.$('connection-coordinate-jump').disabled = !session.controls.length;
    commands.$('connection-coordinate-jump').value = index < 0 ? '' : String(index);
    session.rowElements.forEach((row, i) => row.setAttribute('data-active', String(i === index)));
    session.previewPoints.forEach((point, i) => {
      point.setAttribute('data-active', String(i === index));
      point.setAttribute('aria-pressed', String(i === index));
    });
  }

  function focusCoordinateRow(session, rows, index, marker) {
    if (state.connectionCoordinates !== session || session.controls !== rows
      || !commands.$('connection-coordinates-dialog').open || (marker && !session.previewPoints.includes(marker))) return;
    const input = rows[index]?.[0];
    if (!input) return;
    session.activeAxis = 0; session.inputGroup = null;
    commands.highlightCoordinateRow(session, index);
    input.focus(); input.scrollIntoView({ block: 'center', inline: 'nearest' });
  }

  function navigateCoordinateRows(delta, value) {
    const session = state.connectionCoordinates;
    if (!session || !commands.$('connection-coordinates-dialog').open) return;
    const index = delta ? session.activeIndex + delta : value === '' ? -1 : Number(value);
    if (!Number.isInteger(index) || index < 0 || index >= session.controls.length) return;
    commands.focusCoordinateRow(session, session.controls, index);
  }

  function renderCoordinatePreview() {
    const session = state.connectionCoordinates;
    const canvas = commands.$('connection-coordinate-preview'); canvas.replaceChildren();
    if (!session) return;
    commands.coordinateImportStatus();
    commands.resetCoordinateCopy(session);
    session.previewPoints = [];
    commands.$('connection-coordinate-error').textContent = '';
    session.controls.forEach((row, index) => {
      session.rowErrors[index].textContent = '';
      row.forEach(input => input.setAttribute('aria-invalid', 'false'));
    });
    commands.$('connection-coordinate-clear').disabled = !session.controls.length;
    commands.$('connection-coordinate-reset').disabled = JSON.stringify(session.controls.map(row => row.map(input => input.value)))
      === JSON.stringify(session.vertices.map(point => point.map(String)));
    const caption = commands.$('connection-coordinate-preview-status');
    try {
      const edge = commands.coordinateSessionEdge(session), vertices = commands.readCoordinateVertices(session);
      // Unchanged legacy routes may contain coincident points; applying them is a no-op.
      const changed = JSON.stringify(vertices) !== JSON.stringify(session.vertices);
      if (!edge || changed) commands.validateCoordinateVertices(vertices, edge);
      const nodes = commands.currentNodes(), source = endpoint(edge ? edge.source : session.source, nodes, state.doc.junctions);
      const target = edge && endpoint(edge.target, nodes, state.doc.junctions);
      const pointsFor = points => target ? route(source, target, points)
        : points.length ? route(source, { point: points.at(-1), direction: [0, 0] }, points) : [source.point];
      const original = pointsFor(session.vertices), proposed = pointsFor(vertices);
      const all = [...original, ...proposed];
      const left = Math.min(...all.map(p => p[0])), top = Math.min(...all.map(p => p[1]));
      const width = Math.max(...all.map(p => p[0])) - left, height = Math.max(...all.map(p => p[1])) - top;
      const scale = Math.min(432 / Math.max(width, 1), 112 / Math.max(height, 1));
      const map = ([x, y]) => [240 + (x - left - width / 2) * scale, 80 + (y - top - height / 2) * scale];
      for (const [points, className] of [[original, 'coordinate-route-original'], [proposed, 'coordinate-route-proposed']])
        commands.shape('polyline', { points: points.map(p => map(p).join(',')).join(' '), class: className }, canvas);
      const marker = (point, text, className) => {
        const [cx, cy] = map(point);
        const circle = commands.shape('circle', { cx, cy, r: 4, class: className }, canvas);
        commands.shape('title', {}, circle).textContent = `${text} (${point.join(', ')})`;
        return circle;
      };
      marker(source.point, '起点', 'coordinate-source');
      if (target) marker(target.point, '终点', 'coordinate-target');
      vertices.forEach((point, index) => {
        const control = marker(point, `折点 ${index + 1}`, 'coordinate-waypoint'), rows = session.controls;
        control.setAttribute('r', 8); control.setAttribute('tabindex', 0);
        control.setAttribute('role', 'button');
        control.setAttribute('aria-label', `定位折点 ${index + 1} 坐标`);
        session.previewPoints.push(control);
        control.addEventListener('click', () => commands.focusCoordinateRow(session, rows, index, control));
        control.addEventListener('keydown', event => {
          if (!['Enter', ' '].includes(event.key)) return;
          event.preventDefault(); commands.focusCoordinateRow(session, rows, index, control);
        });
        if (vertices.length <= 12) {
          const [x, y] = map(point);
          commands.shape('text', { x: x + 6, y: y - 7, class: 'coordinate-point-number' }, canvas).textContent = index + 1;
        }
      });
      caption.textContent = edge ? `${changed ? '新走线预览' : '原走线'} · ${vertices.length} 个折点 · 应用后生效`
        : vertices.length ? '临时走线预览 · 起点至最后折点，终点待选' : '无临时折点 · 应用后恢复自动走线，终点待选';
      canvas.toggleAttribute('hidden', false);
    } catch (error) {
      commands.markCoordinateError(session, error);
      canvas.toggleAttribute('hidden', true); caption.textContent = `暂无法预览：${error.message}`;
    }
    commands.highlightCoordinateRow(session, session.activeIndex);
  }

  function changeCoordinateRows(session, index, remove) {
    if (!session || session !== state.connectionCoordinates || !commands.$('connection-coordinates-dialog').open) return;
    const vertices = session.controls.map(row => row.map(input => input.value));
    if (!Number.isInteger(index) || index < 0 || index > vertices.length || (remove && index === vertices.length)) return;
    if (!remove && vertices.length >= 100) {
      commands.$('connection-coordinate-error').textContent = '折点已达 100 个上限，请先删除部分折点。'; return;
    }
    vertices.splice(index, remove ? 1 : 0, ...(!remove ? [['', '']] : []));
    commands.recordCoordinateChange(session); session.activeIndex = Math.min(index, vertices.length - 1); session.activeAxis = 0;
    commands.renderCoordinateRows(vertices);
    (session.controls[Math.min(index, vertices.length - 1)]?.[0] || commands.$('connection-coordinate-add')).focus();
  }

  function reorderCoordinateRows(session, rows, index, delta) {
    if (!session || session !== state.connectionCoordinates || session.controls !== rows
      || !commands.$('connection-coordinates-dialog').open || !Number.isInteger(index) || ![-1, 1].includes(delta)) return;
    const next = index + delta;
    if (index < 0 || index >= rows.length || next < 0 || next >= rows.length) return;
    const vertices = rows.map(pair => pair.map(input => input.value));
    [vertices[index], vertices[next]] = [vertices[next], vertices[index]];
    commands.recordCoordinateChange(session); session.activeIndex = next; session.activeAxis = 0;
    commands.renderCoordinateRows(vertices);
    session.controls[next][0].focus();
  }

  function resetCoordinateRows(restore = false) {
    const session = state.connectionCoordinates;
    if (!session || !commands.$('connection-coordinates-dialog').open) return;
    try { commands.coordinateSessionEdge(session); }
    catch (error) { commands.$('connection-coordinate-error').textContent = error.message; return; }
    const vertices = restore ? session.vertices : [];
    if (JSON.stringify(session.controls.map(row => row.map(input => input.value)))
      === JSON.stringify(vertices.map(point => point.map(String)))) return;
    commands.recordCoordinateChange(session); session.activeIndex = 0; session.activeAxis = 0;
    commands.renderCoordinateRows(vertices);
    (session.controls[0]?.[0] || commands.$('connection-coordinate-add')).focus();
  }

  function applyConnectionCoordinates(event) {
    event.preventDefault();
    const session = state.connectionCoordinates;
    if (!session || !commands.$('connection-coordinates-dialog').open) return;
    const fail = error => {
      commands.$('connection-coordinate-error').textContent = error.message; commands.markCoordinateError(session, error, true);
    };
    let edge, vertices;
    try { edge = commands.coordinateSessionEdge(session); vertices = commands.readCoordinateVertices(session); }
    catch (error) { return fail(error); }
    const changed = JSON.stringify(vertices) !== JSON.stringify(session.vertices);
    if (edge && !changed) {
      commands.$('connection-coordinates-dialog').close(); commands.status('折点坐标未改变 · 原管路保持'); return;
    }
    try {
      commands.validateCoordinateVertices(vertices, edge);
    } catch (error) { return fail(error); }
    if (edge) {
      commands.edit(() => { edge.vertices = vertices; }); commands.message(''); commands.$('connection-coordinates-dialog').close();
      commands.status('已更新管路折点坐标 · Ctrl+Z 一次撤销'); return;
    }
    if (changed) { state.connectionVertices = vertices; commands.resetConnectionVertexPreview(); commands.message(''); commands.renderCanvas(); }
    commands.$('connection-coordinates-dialog').close();
    commands.status(changed ? '已应用临时折点坐标 · 点击终点完成连线 · Esc 取消' : '折点坐标未改变 · 继续连线');
  }

  function bindCoordinatesEvents() {
    commands.$('connection-coordinate-form').addEventListener('submit', commands.applyConnectionCoordinates);
    commands.$('connection-coordinate-jump').addEventListener('change', event => commands.navigateCoordinateRows(0, event.target.value));
    commands.$('connection-coordinate-text').addEventListener('input', () => commands.coordinateImportStatus());
    commands.$('connection-coordinates-dialog').addEventListener('close', () => {
      if (commands.$('connection-coordinates-dialog').open) return;
      state.connectionCoordinates = null;
      commands.$('connection-coordinate-output').value = ''; commands.$('connection-coordinate-copy-status').textContent = '';
      commands.$('connection-coordinate-preview').replaceChildren();
      commands.$('connection-coordinate-preview-status').textContent = '';
      if (state.doc) state.svg.focus({ preventScroll: true });
    });
  }

  return { showConnectionCoordinates, showEdgeCoordinates, openCoordinateForm, renderCoordinateRows, coordinateImportStatus, parseCoordinateText, importCoordinateRows, resetCoordinateCopy, copyCoordinateRows, coordinateFormState, renderCoordinateHistory, recordCoordinateChange, coordinateFormHistory, coordinateSessionEdge, readCoordinateVertices, validateCoordinateVertices, markCoordinateError, highlightCoordinateRow, focusCoordinateRow, navigateCoordinateRows, renderCoordinatePreview, changeCoordinateRows, reorderCoordinateRows, resetCoordinateRows, applyConnectionCoordinates, bindCoordinatesEvents };
}
