/* Explicit synthetic benchmark, only mounted by /?benchmark=1 in a test iframe. */
export function sampleDocument(count) {
  return { schemaVersion: 1, title: `性能测试 ${count}`, page: { width: 4000, height: 4000 },
    nodes: Array.from({ length: count }, (_, i) => ({ id: `n${i}`, type: 'heat_exchanger',
      x: 100 + i % 20 * 180, y: 100 + Math.floor(i / 20) * 100 })),
    edges: Array.from({ length: count - 1 }, (_, i) => ({ id: `e${i}`,
      source: { nodeId: `n${i}`, portId: 'right' }, target: { nodeId: `n${i + 1}`, portId: 'left' } })),
    labels: [], junctions: [] };
}
const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
export async function runBenchmark(editor, sizes = [50, 200, 500], repeat = 3) {
  const rows = [];
  for (const count of sizes) {
    // Remove the previous scene outside the timer. Each measured load must build
    // a fresh scene, rather than reusing the first N IDs from the smaller size.
    await editor.load(sampleDocument(0));
    await frame(); await frame();
    const start = performance.now();
    await editor.load(sampleDocument(count));
    const loadMs = performance.now() - start;
    const loadPhases = editor.loadMetrics?.();
    await frame(); await frame();
    const loadToFramesMs = performance.now() - start;
    const samples = { renderMs: [], selectMs: [], moveMs: [], undoMs: [], frameMs: [] };
    for (let i = 0; i < repeat; i++) {
      for (const [key, action] of [['renderMs', editor.render], ['selectMs', editor.select],
        ['moveMs', editor.move], ['undoMs', editor.undo]]) {
        const t = performance.now(); action(); samples[key].push(performance.now() - t);
      }
      const t = performance.now(); await frame(); await frame();
      samples.frameMs.push(performance.now() - t);
    }
    rows.push({ nodes: count, edges: count - 1, loadMs, loadPhases, loadToFramesMs,
      ...Object.fromEntries(Object.entries(samples).map(([k, v]) => [k, median(v)])),
      domElements: editor.elements(), repeat });
  }
  return { measuredAt: new Date().toISOString(), userAgent: navigator.userAgent,
    viewport: [innerWidth, innerHeight], visibility: document.visibilityState, rows };
}
