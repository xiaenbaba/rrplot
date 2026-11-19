/* Include response-body consumption in the deadline; release even a stalled fetch. */
export async function requestResource(url, options = {}, { timeoutMs = 20000, fetchImpl = globalThis.fetch } = {}) {
  const controller = new AbortController();
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new Error('本机服务响应超时，请检查服务后重试；当前图纸已保留。');
      error.code = 'TIMEOUT'; reject(error); controller.abort();
    }, timeoutMs);
  });
  const operation = (async () => {
    const response = await fetchImpl(url, { ...options, signal: controller.signal });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const error = new Error(detail.error || `请求失败 (${response.status})`);
      error.code = 'HTTP'; error.status = response.status; throw error;
    }
    return response.headers.get('content-type')?.includes('application/json')
      ? response.json() : response.blob();
  })();
  try { return await Promise.race([operation, timeout]); }
  catch (error) {
    if (error.code === 'TIMEOUT' || error.code === 'HTTP') throw error;
    const failure = new Error('无法连接本机服务，请运行 status-web.cmd 检查后重试；当前图纸已保留。');
    failure.code = 'NETWORK'; failure.cause = error; throw failure;
  } finally { clearTimeout(timer); }
}

/* At most one request runs; intermediate pending snapshots are discarded. */
export function createLatestQueue(send) {
  let active = false, pending = null;
  async function drain() {
    if (active || !pending) return;
    active = true;
    const job = pending; pending = null;
    try { job.resolve(await send(job.value)); }
    catch (error) { job.reject(error); }
    finally { active = false; void drain(); }
  }
  return value => new Promise((resolve, reject) => {
    if (pending) pending.resolve(null);
    pending = { value, resolve, reject };
    // Start promptly and retain only the newest snapshot while a request runs.
    void drain();
  });
}
