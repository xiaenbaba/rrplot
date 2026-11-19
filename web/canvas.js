/* Keyed top-level SVG groups. Unchanged children retain browser image/layout caches. */
export function createCanvasRenderer(root) {
  const cache = new Map();
  let previous = null, used = null;
  function place(element) {
    const next = previous ? previous.nextSibling : root.firstChild;
    if (element !== next) root.insertBefore(element, next);
    used.add(element);
    previous = element;
  }
  return {
    begin() {
      // Remove old overlays first, so unchanged groups never shuffle past them.
      const retained = new Set([...cache.values()].map(entry => entry.element));
      for (const element of [...root.childNodes]) if (!retained.has(element)) element.remove();
      previous = null; used = new Set();
    },
    place,
    group(key, tag, attrs, signature) {
      let entry = cache.get(key);
      if (!entry) {
        entry = { element: root.ownerDocument.createElementNS(root.namespaceURI, tag) };
        cache.set(key, entry);
      }
      const { element } = entry;
      for (const [name, value] of Object.entries(attrs)) {
        if (value !== undefined && element.getAttribute(name) !== String(value)) element.setAttribute(name, value);
      }
      place(element);
      const changed = signature !== entry.signature;
      if (changed) { element.replaceChildren(); entry.signature = signature; }
      return { element, changed };
    },
    end() {
      for (const element of [...root.childNodes]) if (!used.has(element)) element.remove();
      for (const [key, entry] of cache) if (!used.has(entry.element)) cache.delete(key);
      used = null; previous = null;
    }
  };
}
