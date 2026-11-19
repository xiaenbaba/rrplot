export function serviceStatus(info) {
  if (!info?.ok) return { text: '服务未连接', warning: true,
    detail: '运行 start-web.cmd；可用 status-web.cmd 查询服务。' };
  const version = info.version ? `v${info.version}` : '未知版本';
  if (info.app !== 'rrplot' || !info.instanceId) return {
    text: `服务 ${version} · 旧版`, warning: true,
    detail: '请保存 JSON，在原服务窗口按 Ctrl+C，再运行 start-web.cmd。' };
  return { text: `服务 ${version}${info.codeChanged ? ' · 需要重启' : ''}`,
    warning: !!info.codeChanged,
    detail: `PID ${info.pid} · build ${info.build} · ${info.startedAt}`
      + (info.codeChanged ? '；请保存 JSON，运行 restart-web.cmd 后刷新页面。' : '') };
}

export function monitorService(element) {
  let busy = false;
  async function update() {
    if (busy) return;
    busy = true;
    let info = null;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch('/api/health', { signal: controller.signal });
      if (response.ok) info = await response.json();
    } catch { /* Health checks never discard the open document. */ }
    finally { clearTimeout(timeout); busy = false; }
    const state = serviceStatus(info);
    element.textContent = state.text; element.title = state.detail;
    element.classList.toggle('service-warning', state.warning);
  }
  element.addEventListener('click', update);
  window.addEventListener('focus', update);
  const timer = setInterval(() => { if (!document.hidden) void update(); }, 30000);
  window.addEventListener('pagehide', () => clearInterval(timer), { once: true });
  void update();
}
