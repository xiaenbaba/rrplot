export const NS = 'http://www.w3.org/2000/svg';
export const clone = value => structuredClone(value);
export const uid = prefix => prefix + '-' + crypto.randomUUID().slice(0, 8);
export const DRAFT = 'rrplot-web-v1-draft';
export const BENCHMARK = (globalThis.location?.search || '').slice(1).split('&').includes('benchmark=1');
export const DRAFT_HISTORY = 'rrplot-web-v1-draft-history';
export const SHORTCUTS = 'rrplot-web-v1-single-key-shortcuts';
export const CANVAS_PREFERENCES = { grid: 'rrplot-web-v1-grid', snap: 'rrplot-web-v1-snap' };
