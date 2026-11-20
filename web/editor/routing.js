import { routeDiagramEdges, validateRoutedMounts } from '../routing.js';

/** Explicit, cancellable routing transaction. Moving equipment never silently
 * replaces manual bends; results are ordinary vertices and one undo step. */
export function createRoutingController(state, commands) {
  async function autoRoute(scope = 'auto') {
    if (!state.doc || state.routingSession || state.documentLoad || commands.pipeActionsBusy() || document.querySelector('dialog[open]')) return;
    const selected = new Set(state.multiSelection.filter(ref => ref.kind === 'edge').map(ref => ref.id));
    const edges = state.doc.edges.filter(edge => scope === 'all' || (scope === 'auto' && !selected.size) || selected.has(edge.id));
    if (!edges.length) return commands.message('请先绘制或选择需要避障的管路。');
    const session = {}, original = state.doc, revision = state.revision, geometries = state.geometries;
    state.routingSession = session;
    const valid = () => state.routingSession === session && state.doc === original && state.revision === revision && state.geometries === geometries
      && !state.documentLoad && !commands.pipeActionsBusy() && !document.querySelector('dialog[open]');
    const changes = [], failures = [];
    try {
      const nodes = commands.currentNodes(true);
      for (let index = 0; index < edges.length; index++) {
        commands.status(`正在避障布线 ${index + 1}/${edges.length} · Esc 取消，编辑图纸也会取消`);
        // Yield before each search. Edits/undo/load during a large batch cancel
        // the stale transaction rather than overwriting the latest document.
        await new Promise(resolve => setTimeout(resolve, 0));
        if (!valid()) return commands.status('避障布线已取消 · 图纸已变化或正在进行其他操作');
        const result = routeDiagramEdges(original, nodes, new Set([edges[index].id]));
        changes.push(...result.changes); failures.push(...result.failures);
      }
      if (!valid()) return;
      // A batch is atomic: failed edges leave every original manual route intact.
      if (failures.length) return commands.message(`未应用避障布线：${failures.length} 条管路无法处理。${failures.slice(0, 3).map(f => `${f.id}：${f.message}`).join('；')} 请调整布局或仅选择可处理的管路。`);
      if (!changes.length) return commands.status('管路已满足当前避障走线 · 无需修改');
      validateRoutedMounts(original, nodes, changes);
      const byId = new Map(changes.map(change => [change.id, change.vertices]));
      commands.edit(() => { for (const edge of state.doc.edges) if (byId.has(edge.id)) edge.vertices = byId.get(edge.id); });
      commands.status(`已避障布线 · ${changes.length} 条管路 · Ctrl+Z 一次撤销`);
    } catch (error) { commands.message(error.message); }
    finally { if (state.routingSession === session) state.routingSession = null; }
  }

  return { autoRoute };
}
