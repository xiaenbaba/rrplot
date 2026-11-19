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
