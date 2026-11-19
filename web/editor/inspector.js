import { canMount, detachNode, along, mountNode, projectOnRoute, MOUNT_TYPES } from '../geometry.js';
import { propertySection, glyphImage } from '../inspector.js';
import { uid } from './config.js';

/** Property fields, sections, ports and device style controls.
 * State belongs to the editor instance. Commands are late-bound controller ports;
 * factories are side-effect free, and event binding happens after composition.
 */
export function createInspectorController(state, commands) {
  function renderMountFields(root, item) {
    const supported = state.pipeMountsSupported && canMount(state.doc, item);
    commands.field(root, '挂接管路', item.mount?.edgeId || '', value => {
      if (!value) { detachNode(item, commands.currentNodes().find(n => n.id === item.id)); return; }
      const pose = commands.currentNodes().find(n => n.id === item.id);
      const points = commands.edgePoints(state.doc.edges.find(e => e.id === value));
      if (along(points, .5).length < 1) return commands.message('管路长度为零，无法挂接。');
      mountNode(state.doc, item.id, value, projectOnRoute(points, [pose.x, pose.y]).at, item.mount?.reverse);
      state.ports = [];
    }, { options: [{ value: '', label: '未挂接' }, ...state.doc.edges.map(e => ({ value: e.id,
      label: commands.refName(e.source) + ' → ' + commands.refName(e.target) }))], disabled: !supported });
    if (item.mount) {
      commands.field(root, '挂接位置（%）', item.mount.at * 100, v => { item.mount.at = v / 100; }, { min: 0, max: 100 });
      commands.field(root, '挂接反向', item.mount.reverse, v => { item.mount.reverse = v; }, { type: 'checkbox' });
      commands.inspectorButton(root, '解除挂接', () => commands.edit(() => detachNode(item, commands.currentNodes().find(n => n.id === item.id))));
    }
    root.append(commands.html('p', !state.pipeMountsSupported ? '阀件挂接需要重启服务并刷新页面。'
      : !canMount(state.doc, item) ? '该阀件已作为管路端点；调整其相连管路后才能挂接。'
        : '拖到管路附近松开即可挂接，拖离可解除；父管路保持完整，移动和改线时自动跟随。', 'muted'));
  }

  function field(parent, caption, value, setter, options = {}) {
    const wrap = commands.html('label', undefined, 'field'); wrap.append(commands.html('span', caption));
    const input = commands.html(options.multiline ? 'textarea' : options.options ? 'select' : 'input');
    input.setAttribute('aria-label', caption);
    if (options.options) options.options.forEach(v => {
      const o = commands.html('option', typeof v === 'object' ? v.label : options.optionLabels?.[v] || String(v)); o.value = typeof v === 'object' ? v.value : v; input.append(o);
    });
    else if (!options.multiline) input.type = options.type || (typeof value === 'number' ? 'number' : 'text');
    if (options.min !== undefined) input.min = options.min;
    if (options.max !== undefined) input.max = options.max;
    if (options.required) input.required = true;
    input.disabled = !!options.disabled;
    if (input.type === 'number') input.step = options.step || 'any';
    if (input.type === 'checkbox') input.checked = value; else input.value = value;
    let committed = value;
    function commit() {
      if (options.deferValidation) return;
      if (!input.checkValidity()) { input.reportValidity(); return; }
      const next = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
      if (next === committed) return;
      committed = next;
      if (options.transient) setter(next); else commands.edit(() => setter(next));
    }
    input.addEventListener('change', commit);
    input.addEventListener('blur', commit);
    wrap.append(input); parent.append(wrap); return input;
  }

  function inspectorButton(parent, caption, action) {
    const b = commands.html('button', caption); b.addEventListener('click', action); parent.append(b); return b;
  }

  function inspectorSection(parent, caption) {
    return propertySection(parent, caption, state.inspectorGroups.get(caption) !== false,
      open => state.inspectorGroups.set(caption, open));
  }

  function renderInspector() {
    commands.renderHint();
    commands.renderObjectList();
    const root = commands.$('inspector'); root.replaceChildren();
    if (state.mode === 'reconnect' && state.reconnect) {
      commands.$('selection-kind').textContent = 'RECONNECT';
      root.append(commands.html('h2', state.reconnect.side === 'source' ? '重新连接起点' : '重新连接终点', 'object-heading'));
      const edge = state.doc.edges.find(e => e.id === state.reconnect.edgeId);
      root.append(commands.html('p', '当前端点：' + commands.refName(edge[state.reconnect.side]), 'muted'));
      root.append(commands.html('p', '点击新的设备端口或三通，也可 Shift+点击其他管路插入三通并重接。靠近时预览走线，折点、样式和状态点保留。', 'muted'));
      commands.inspectorButton(root, '取消重接（Esc）', commands.cancelReconnect);
      return;
    }
    if (state.mode === 'move-all') {
      commands.$('selection-kind').textContent = 'ALL';
      root.append(commands.html('h2', '整体移动', 'object-heading'));
      root.append(commands.html('p', '在画布中按住左键拖动，整体移动全部设备、三通、管路折点和文字。页面位置保持不变，附着标签随设备移动。', 'muted'));
      root.append(commands.html('p', '每次拖动可用 Ctrl+Z 撤销；拖动中按 Esc 取消本次移动，松开后按 Esc 退出。', 'muted'));
      commands.inspectorButton(root, '精确平移全部', () => commands.showMoveDialog('all'));
      return;
    }
    if (state.multiSelection.length > 1) {
      commands.$('selection-kind').textContent = 'MULTI';
      root.append(commands.html('h2', `已选择 ${state.multiSelection.length} 项`, 'object-heading'));
      commands.connectedSelectionButton(root);
      const movable = commands.layoutRefs().length, pipes = state.multiSelection.filter(ref => ref.kind === 'edge').length;
      root.append(commands.html('p', `设备、三通和文字 ${movable} 项 · 管路 ${pipes} 条。按住 Shift 点击可添加或取消选择，Shift+拖动空白可追加框选。`, 'muted'));
      root.append(commands.html('p', '可批量修改样式或删除。拖动已选设备、三通或文字可一起移动；管路随端点移动，单选管路后可编辑走线。', 'muted'));
      root.append(commands.html('p', movable ? 'Ctrl+C 复制设备、三通和文字，Ctrl+D 生成副本，均包含设备标签和组内管路。单独选中的管路不复制，请同时选择其两端设备或三通。'
        : '复制管路时，请同时选择两端设备或三通，再使用 Ctrl+C 或 Ctrl+D。', 'muted'));
      const layout = commands.html('div', undefined, 'layout-grid');
      for (const [action, caption] of [
        ['align-left', '左对齐'], ['align-center-x', '水平居中'], ['align-right', '右对齐'],
        ['align-top', '上对齐'], ['align-center-y', '垂直居中'], ['align-bottom', '下对齐'],
        ['distribute-x', '水平等距'], ['distribute-y', '垂直等距'],
      ]) {
        const button = commands.inspectorButton(layout, caption, () => commands.batchLayout(action));
        button.disabled = movable < (action.startsWith('distribute') ? 3 : 2);
      }
      if (movable) root.append(commands.html('div', '批量布局（设备、三通和文字）', 'section-label'), layout);
      if (pipes) commands.renderPipeActions(root, pipes);
      if (movable) commands.inspectorButton(root, '精确平移所选', () => commands.showMoveDialog('selection'));
      commands.inspectorButton(root, '批量样式', commands.showBatchStyles);
      commands.inspectorButton(root, '清除多选', () => { commands.clearSelection(); commands.render(); });
      return;
    }
    const item = commands.findSelected();
    commands.$('selection-kind').textContent = state.selection?.kind?.toUpperCase() || 'PAGE';
    if (!item) {
      root.append(commands.html('h2', '页面设置', 'object-heading'));
      commands.field(root, '图纸名称', state.doc.title, v => { state.doc.title = v; });
      const pair = commands.html('div', undefined, 'field-pair'); root.append(pair);
      commands.field(pair, '页面宽度', state.doc.page.width, v => { state.doc.page.width = v; }, { min: 100, max: 4000 });
      commands.field(pair, '页面高度', state.doc.page.height, v => { state.doc.page.height = v; }, { min: 100, max: 4000 });
      root.append(commands.html('div', '页面排版', 'section-label'));
      commands.inspectorButton(root, '精确平移全部', () => commands.showMoveDialog('all'));
      const margin = commands.field(root, '适配留白（单位）', state.pageMargin, v => { state.pageMargin = v; },
        { min: 10, max: 500, required: true, transient: true, disabled: state.pageLayoutBusy });
      margin.id = 'page-margin';
      const layout = commands.html('div', undefined, 'button-row'); root.append(layout);
      const empty = !['nodes', 'edges', 'junctions', 'labels'].some(name => state.doc[name].length);
      for (const [action, title] of [['center', '内容居中'], ['fit', '页面适配内容']]) {
        const button = commands.inspectorButton(layout, title, () => commands.applyPageLayout(action));
        button.dataset.pageLayout = action; button.disabled = empty || state.pageLayoutBusy;
      }
      root.append(commands.html('p', '作用于整张图纸，包含文字和管路。保持图元大小与连接；适配会调整纸张尺寸，每次排版可一次撤销。“适应页面”只调整视图。', 'muted'));
      root.append(commands.html('p', state.mode === 'box-select' ? '拖出矩形，完整框住设备、管路、三通或文字。松开后可批量修改样式或删除，拖动设备、三通和文字可移动；按住 Shift 可追加选择。'
        : '选择设备、标签或管路查看属性；使用“框选”或 Shift+拖动空白可多选。坐标单位与 rrplot 画布一致。', 'muted')); return;
    }
    const kind = state.selection.kind;
    root.append(commands.html('h2', kind === 'node' ? item.title : { edge: '管路', label: '文字标签', junction: '分流三通' }[kind], 'object-heading'));
    if (kind !== 'label' || item.nodeId || item.edgeId) commands.connectedSelectionButton(root);
    if (kind === 'node') {
      const position = commands.inspectorSection(root, '名称与位置');
      commands.field(position, '设备名称', item.title, v => {
        const l = state.doc.labels.find(l => l.nodeId === item.id && l.text === item.title);
        if (l) l.text = v; item.title = v;
      });
      if (!item.mount) {
        commands.coordinateFields(position, item);
        commands.field(position, '旋转角度', item.rotation, v => { item.rotation = Number(v); }, { options: [0, 90, 180, 270] });
      }
      if (MOUNT_TYPES.includes(item.type)) commands.renderMountFields(commands.inspectorSection(root, '管路挂接'), item);
      const parameters = commands.inspectorSection(root, '图元参数');
      const preview = commands.html('figure', undefined, 'glyph-preview');
      preview.append(glyphImage(item.type, item.params, item.title));
      preview.append(commands.html('figcaption', '当前样式 · 连接端口按画布旋转')); parameters.append(preview);
      if (item.type === 'solenoid_valve') root.append(commands.html('p', '阀体样式可选圆圈 X＋横杆或对顶三角＋横杆＋Σ 折线。切换保持端口与挂接；对顶三角样式的执行机构保持水平朝上、竖直朝右，不随反向挂接翻转。', 'muted'));
      if (item.type === 'expansion_valve') root.append(commands.html('p', '阀体样式可选圆圈 X 或对顶三角＋半圆穹顶，切换保持端口与挂接。穹顶按画布连接方向自动保持水平朝上、竖直朝右，不随管路反向翻到另一侧。', 'muted'));
      const entry = state.catalog.find(c => c.type === item.type);
      for (const [key, f] of Object.entries(entry.fields)) commands.field(parameters, f.label, item.params[key], v => { item.params[key] = v; }, f);
      if (item.type === 'four_way_valve') root.append(commands.html('p', 'D / exhaust：排气；S / suction：回气；C / condenser、E / evaporator：两侧换热器。端口随旋转移动，图元只表示接管关系。', 'muted'));
      if (item.type === 'check_valve') root.append(commands.html('p', '阀体样式可选黑色实心或空心黑框，切换样式保持端口与挂接。三角尖端指向 out；改变流通方向会交换 in/out 的位置，已有管路继续按端口 ID 跟随。', 'muted'));
      commands.inspectorButton(root, '添加设备标签', () => commands.edit(() => {
        const id = uid('label'); state.doc.labels.push({ id, nodeId: item.id, x: 0, y: 70, text: item.title, size: 15, ha: 'center', boxed: true, color: '#111111' }); commands.setSelection('label', id);
      }));
    } else if (kind === 'label') {
      commands.field(root, '标签内容', item.text, v => { item.text = v; }, { multiline: true });
      if (!item.nodeId) {
        commands.field(root, '附着管路', item.edgeId || '', v => commands.attachLabelToEdge(item, v), {
          options: [{ value: '', label: '独立文字' }, ...state.doc.edges.map(e => ({ value: e.id,
            label: commands.refName(e.source) + ' → ' + commands.refName(e.target) }))], disabled: !state.edgeLabelsSupported });
        if (!state.edgeLabelsSupported) root.append(commands.html('p', '使用管路状态点前，请重启 start-web.cmd 并刷新页面。', 'muted'));
      }
      if (item.edgeId) commands.field(root, '沿管路位置（%）', item.at * 100, v => { item.at = v / 100; }, { min: 0, max: 100 });
      commands.coordinateFields(root, item, item.nodeId || item.edgeId ? '相对偏移' : '');
      commands.field(root, '字号（pt）', item.size, v => { item.size = v; }, { min: 6, max: 72 });
      commands.field(root, '文字对齐', item.ha, v => { item.ha = v; }, { options: ['left', 'center', 'right'] });
      commands.field(root, '文字颜色', item.color, v => { item.color = v; }, { type: 'color' });
      commands.field(root, '白色背景', item.boxed, v => { item.boxed = v; }, { type: 'checkbox' });
      if (item.nodeId) commands.inspectorButton(root, '解除设备附着', () => commands.edit(() => {
        const p = commands.labelPosition(item); delete item.nodeId; [item.x, item.y] = p;
      }));
    } else if (kind === 'junction') {
      commands.coordinateFields(root, item);
      commands.inspectorButton(root, '从此三通接出支路', () => commands.beginBranch(item.id)).disabled = commands.branchBusy();
      commands.inspectorButton(root, '删除三通并恢复管路', () => commands.removeSelected());
    }
    else if (kind === 'edge') {
      root.append(commands.html('p', commands.refName(item.source) + ' → ' + commands.refName(item.target), 'muted'));
      commands.field(root, '线宽（pt）', item.width, v => { item.width = v; }, { min: .2, max: 8 });
      commands.field(root, '管路颜色', item.color, v => { item.color = v; }, { type: 'color' });
      commands.field(root, '线型', item.linestyle, v => { item.linestyle = v; }, { options: ['solid', 'dashed'] });
      commands.field(root, '显示流向箭头', item.head, v => { item.head = v; }, { type: 'checkbox' });
      root.append(commands.html('p', `${item.vertices.length} 个手动顶点。拖动线段中间的长条手柄调整走线；双击管线添加折点，Alt+点击方形折点删除。`, 'muted'));
      commands.inspectorButton(root, '编辑折点坐标', () => commands.showEdgeCoordinates(item.id)).disabled = !!commands.pipeActionsBusy();
      commands.renderPipeActions(root, 1);
      commands.inspectorButton(root, '在管路中间插入三通', () => commands.splitEdge(item));
      commands.inspectorButton(root, '插入三通并接出支路', () => commands.splitEdge(item, .5, true)).disabled = commands.branchBusy();
      commands.inspectorButton(root, '添加状态点', () => commands.addStateLabel(item));
      const endpoints = commands.html('div', undefined, 'button-row reconnect-buttons'); root.append(endpoints);
      commands.inspectorButton(endpoints, '重接起点', () => commands.beginReconnect(item, 'source'));
      commands.inspectorButton(endpoints, '重接终点', () => commands.beginReconnect(item, 'target'));
    }
    if (['node', 'junction', 'label'].includes(kind))
      commands.inspectorButton(root, '精确平移所选', () => commands.showMoveDialog('selection'));
  }

  return { renderMountFields, field, inspectorButton, inspectorSection, renderInspector };
}
