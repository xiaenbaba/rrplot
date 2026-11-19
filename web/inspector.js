/* Small DOM helpers shared by the property inspector and the symbol palette. */
export function propertySection(parent, caption, open, onToggle) {
  const group = document.createElement('details');
  group.className = 'property-section'; group.open = open;
  const title = document.createElement('summary'); title.textContent = caption;
  group.append(title); group.addEventListener('toggle', () => onToggle(group.open));
  const content = document.createElement('div'); content.className = 'property-section-body';
  group.append(content); parent.append(group); return content;
}

export function glyphUrl(type, params = {}) {
  return '/api/glyph/' + encodeURIComponent(type) + '?params=' + encodeURIComponent(JSON.stringify(params));
}

export function glyphImage(type, params = {}, caption = '') {
  const image = document.createElement('img');
  image.className = 'glyph-thumbnail'; image.src = glyphUrl(type, params);
  image.alt = caption; image.loading = 'lazy'; image.draggable = false;
  image.addEventListener('error', () => { image.hidden = true; });
  return image;
}
