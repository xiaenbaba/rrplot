/* Keyed top-level SVG groups. Unchanged children retain browser image/layout caches. */
export function createCanvasRenderer(root) {
  const cache = new Map();
  let ordered = null, used = null;
  function place(element) {
    if (used.has(element)) return;
    ordered.push(element);
    used.add(element);
  }
  return {
    begin() {
      // Remove old overlays first, so unchanged groups never shuffle past them.
      const retained = new Set([...cache.values()].map(entry => entry.element));
      for (const element of [...root.childNodes]) if (!retained.has(element)) element.remove();
      ordered = []; used = new Set();
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
      // Build new groups while detached, then attach consecutive new elements in
      // one fragment. Existing groups keep their DOM/image identity and position.
      let next = root.firstChild;
      let fragment = root.ownerDocument.createDocumentFragment?.();
      const flush = () => {
        if (fragment?.firstChild) root.insertBefore(fragment, next);
      };
      for (const element of ordered) {
        if (element === next) { flush(); next = next.nextSibling; }
        else if (fragment && element.parentNode !== root) fragment.append(element);
        else { flush(); root.insertBefore(element, next); }
      }
      flush();
      for (const element of [...root.childNodes]) if (!used.has(element)) element.remove();
      for (const [key, entry] of cache) if (!used.has(entry.element)) cache.delete(key);
      used = null; ordered = null;
    }
  };
}
