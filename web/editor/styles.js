import { styleTargets, applyStyles } from '../styles.js';
import { clone } from './config.js';

/** Batch style dialog and its revision-guarded application.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createStylesController(state, commands) {
  function updateStyleButton() {
    commands.$('batch-styles').disabled = state.mode !== 'select' || !!(state.placement || state.pendingPort || state.reconnect || state.drag || state.pageLayoutBusy)
      || !(state.doc.edges.length || state.doc.labels.length);
  }

  function showBatchStyles() {
    if (!state.doc || state.mode !== 'select' || state.placement || state.pendingPort || state.reconnect || state.drag || state.pageLayoutBusy)
      return commands.message('请先完成当前操作或按 Esc，再设置批量样式。');
    state.styleSession = { revision: state.revision, selection: clone(state.multiSelection), controls: [] };
    commands.$('style-scope').value = state.multiSelection.length ? 'selection' : 'all';
    commands.renderStyleFields();
    commands.$('styles-dialog').showModal();
  }

  function renderStyleFields() {
    const scope = commands.$('style-scope').value;
    const targets = styleTargets(state.doc, state.styleSession.selection, scope);
    commands.$('style-summary').textContent = `将处理 ${targets.edges.length} 条管路、${targets.labels.length} 个标签。`
      + (scope === 'selection' ? ' 包含所选设备的标签、两端均在组内的管路及其状态点。' : ' 包含独立文字、设备标签和管路状态点。');
    commands.$('style-error').textContent = '';
    const root = commands.$('style-fields'); root.replaceChildren(); state.styleSession.controls = [];
    for (const [group, title, specs] of [
      ['edges', '管路', [
        ['color', '管路颜色', '#111111', { type: 'color' }],
        ['width', '线宽（pt）', 1.8, { min: .2, max: 8, required: true }],
        ['linestyle', '线型', 'solid', { options: [{ value: 'solid', label: '实线' }, { value: 'dashed', label: '虚线' }] }],
        ['head', '流向箭头', true, { options: [{ value: 'true', label: '显示' }, { value: 'false', label: '隐藏' }] }]
      ]],
      ['labels', '标签', [
        ['color', '文字颜色', '#111111', { type: 'color' }],
        ['size', '字号（pt）', 15, { min: 6, max: 72, required: true }],
        ['ha', '文字对齐', 'center', { options: [{ value: 'left', label: '左对齐' }, { value: 'center', label: '居中' }, { value: 'right', label: '右对齐' }] }],
        ['boxed', '白色背景', false, { options: [{ value: 'true', label: '显示' }, { value: 'false', label: '隐藏' }] }]
      ]]
    ]) {
      const section = commands.html('section', undefined, 'style-section');
      section.append(commands.html('h3', `${title} · ${targets[group].length} 项`)); root.append(section);
      const ids = new Set(targets[group]), items = state.doc[group].filter(item => ids.has(item.id));
      for (const [key, caption, fallback, options] of specs) {
        const row = commands.html('div', undefined, 'style-row'); section.append(row);
        const label = commands.html('label', undefined, 'style-enable'), enable = commands.html('input');
        enable.type = 'checkbox'; enable.disabled = !items.length;
        enable.setAttribute('aria-label', '修改' + caption); label.append(enable, commands.html('span', caption)); row.append(label);
        const common = items.length && items.every(item => item[key] === items[0][key]);
        const initial = common ? items[0][key] : fallback;
        const namedColor = options.type === 'color' && !/^#[0-9a-f]{6}$/i.test(initial);
        const input = commands.field(row, '批量' + caption, namedColor ? fallback : initial, () => {}, { ...options, disabled: true, transient: true });
        if (!common && items.length) row.append(commands.html('small', '当前值不一致', 'muted'));
        else if (namedColor) row.append(commands.html('small', '请重新选择颜色', 'muted'));
        enable.addEventListener('change', () => { input.disabled = !enable.checked; commands.updateStyleApply(); });
        state.styleSession.controls.push({ group, key, enable, input });
      }
    }
    commands.updateStyleApply();
  }

  function updateStyleApply() {
    commands.$('style-apply').disabled = !state.styleSession.controls.some(control => control.enable.checked);
  }

  function bindStylesEvents() {
    commands.$('style-scope').addEventListener('change', commands.renderStyleFields);
    commands.$('styles-dialog').addEventListener('close', () => { state.styleSession = null; });
    commands.$('style-form').addEventListener('submit', event => {
      event.preventDefault();
      if (!state.styleSession || state.revision !== state.styleSession.revision) {
        commands.$('style-error').textContent = '图纸已变化，请关闭后重新打开批量样式。'; return;
      }
      const patch = {};
      for (const { group, key, enable, input } of state.styleSession.controls) {
        if (!enable.checked) continue;
        (patch[group] ||= {})[key] = input.type === 'number' ? Number(input.value)
          : ['head', 'boxed'].includes(key) ? input.value === 'true' : input.value;
      }
      if (!Object.keys(patch).length) return;
      try {
        const next = applyStyles(state.doc, state.styleSession.selection, commands.$('style-scope').value, patch);
        const changed = JSON.stringify(next) !== JSON.stringify(state.doc);
        if (changed) commands.edit(() => { state.doc = next; });
        commands.$('styles-dialog').close();
        commands.status(changed ? '批量样式已应用 · Ctrl+Z 可一次撤销' : '样式已一致，无需修改');
      } catch (error) { commands.$('style-error').textContent = error.message; }
    });
  }

  return { updateStyleButton, showBatchStyles, renderStyleFields, updateStyleApply, bindStylesEvents };
}
