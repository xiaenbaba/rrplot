const fs = require('node:fs');
const path = require('node:path');

/** Load the actual controller factories into existing focused VM scenarios.
 * Pure geometry/DOM adapters are supplied by each scenario, as before. Only this
 * test adapter exposes legacy variable names; production uses state/commands.
 */
function loadEditorSource(entry) {
  const visited = new Set(), chunks = [];
  const editorRoot = path.join(path.dirname(entry), 'editor') + path.sep;
  function visit(file) {
    if (visited.has(file)) return;
    visited.add(file);
    const source = fs.readFileSync(file, 'utf8');
    for (const match of source.matchAll(/^import .* from '([^']+)';\r?$/gm)) {
      const dependency = path.resolve(path.dirname(file), match[1]);
      if (dependency.startsWith(editorRoot)) visit(dependency);
    }
    chunks.push(source.replace(/^import .*;\r?$/gm, '')
      .replace(/^export /gm, '').replace('void editor.commands.init();', ''));
  }
  visit(entry);
  chunks.push(`
    for (const [owner, keys] of [[editor.state, Object.keys(editor.state)],
      [editor.commands, Object.keys(editor.commands)]]) {
      for (const key of keys) Object.defineProperty(globalThis, key, {
        configurable: true, get: () => owner[key], set: value => { owner[key] = value; }
      });
    }
  `);
  return chunks.join('\n');
}

module.exports = { loadEditorSource };
