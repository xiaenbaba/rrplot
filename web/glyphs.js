/* Bounded in-memory image interning. Legacy responses keep working. */
export function createGlyphCache(limit = 256) {
  const cache = new Map();
  return result => {
    const available = new Map(Object.entries(result.glyphs || {}));
    for (const [key, image] of available) {
      cache.delete(key); cache.set(key, image);
    }
    for (const node of result.nodes) {
      const g = node.geometry;
      if (g.glyphId) {
        const image = available.get(g.glyphId) || cache.get(g.glyphId);
        if (!image) throw new Error('图元图像缺失，请重新连接并更新。');
        g.image = image;
      }
    }
    while (cache.size > limit) cache.delete(cache.keys().next().value);
    return result;
  };
}
