/* Источники книг для мини-приложения.
   Если Internet Archive заблокирует запрос из браузера (CORS), укажите адрес
   своего прокси в PROXY — код прокси лежит в proxy/worker.js. */
export const PROXY = '';

const wrap = (url) => (PROXY ? PROXY + encodeURIComponent(url) : url);

const IA_SEARCH = 'https://archive.org/advancedsearch.php';
const IA_META = 'https://archive.org/metadata/';
const IA_DL = 'https://archive.org/download/';
const GUTENDEX = 'https://gutendex.com/books';
const LANG_HINT = { ar: 'Arabic', ru: 'Russian', uz: 'Uzbek' };
const EXT_ORDER = { pdf: 0, epub: 1, djvu: 2, txt: 3 };

export function humanSize(bytes) {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0, n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i > 1 ? n.toFixed(1) : Math.round(n)} ${units[i]}`;
}

function extOf(name) {
  const m = name.toLowerCase().match(/\.(pdf|epub|txt|djvu)$/);
  return m ? m[1] : '';
}

async function getJSON(url, timeout = 20000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const r = await fetch(wrap(url), { signal: ctrl.signal });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } finally { clearTimeout(timer); }
}

/* ------------------------------------------------------- Internet Archive */
async function iaItem(ident, title, author, year) {
  let meta;
  try { meta = await getJSON(IA_META + encodeURIComponent(ident)); } catch { return null; }
  const files = [];
  for (const f of meta.files || []) {
    const ext = extOf(f.name || '');
    if (!ext) continue;
    if (f.name.startsWith('__') || f.name.includes('_meta')) continue;
    const size = Number(f.size || 0);
    if (size && size < 4096) continue;
    files.push({
      fmt: ext,
      url: `${IA_DL}${encodeURIComponent(ident)}/${encodeURIComponent(f.name)}`,
      size,
      scan: /_bw|_text/.test(f.name),
      name: f.name,
    });
  }
  if (!files.length) return null;
  files.sort((a, b) => (EXT_ORDER[a.fmt] ?? 9) - (EXT_ORDER[b.fmt] ?? 9) || a.scan - b.scan || b.size - a.size);
  const seen = new Set(), picked = [];
  for (const f of files) {
    const key = f.fmt + f.scan;
    if (seen.has(key)) continue;
    seen.add(key); picked.push(f);
    if (picked.length >= 6) break;
  }
  return {
    src: 'ia', id: ident, title: title || ident, author: author || '', year: String(year || '').slice(0, 4),
    cover: `https://archive.org/services/img/${encodeURIComponent(ident)}`,
    page: `https://archive.org/details/${encodeURIComponent(ident)}`,
    files: picked,
  };
}

async function searchArchive(query, lang, rows = 10) {
  const hint = LANG_HINT[lang];
  const q = `(${query}) AND mediatype:texts` + (hint ? ` AND (language:(${hint}) OR language:(*))` : '');
  const params = new URLSearchParams();
  params.set('q', q);
  params.set('rows', String(rows));
  params.set('page', '1');
  params.set('output', 'json');
  params.append('sort[]', 'downloads desc');
  ['identifier', 'title', 'creator', 'year'].forEach((f) => params.append('fl[]', f));

  const data = await getJSON(`${IA_SEARCH}?${params.toString()}`);
  const docs = data?.response?.docs || [];
  const items = await Promise.all(docs.map((d) => iaItem(
    d.identifier,
    d.title,
    Array.isArray(d.creator) ? d.creator.slice(0, 2).join(', ') : d.creator,
    d.year,
  ).catch(() => null)));
  return items.filter(Boolean);
}

/* ----------------------------------------------------------- Gutenberg */
async function searchGutendex(query) {
  const data = await getJSON(`${GUTENDEX}?search=${encodeURIComponent(query)}`);
  return (data.results || []).slice(0, 5).map((b) => {
    const files = [];
    for (const [mime, url] of Object.entries(b.formats || {})) {
      if (url.endsWith('.zip')) continue;
      if (mime.includes('epub')) files.push({ fmt: 'epub', url, size: 0 });
      else if (mime.startsWith('text/plain')) files.push({ fmt: 'txt', url, size: 0 });
      else if (mime.includes('pdf')) files.push({ fmt: 'pdf', url, size: 0 });
    }
    if (!files.length) return null;
    return {
      src: 'pg', id: String(b.id), title: b.title || '',
      author: (b.authors || []).slice(0, 2).map((a) => a.name).join(', '),
      year: '', cover: b.formats?.['image/jpeg'] || '',
      page: `https://www.gutenberg.org/ebooks/${b.id}`,
      files: files.slice(0, 4),
    };
  }).filter(Boolean);
}

/* -------------------------------------------------------- свой каталог */
let catalogCache = null;
async function loadCatalog() {
  if (catalogCache) return catalogCache;
  try {
    const r = await fetch('catalog.json');
    catalogCache = (await r.json()).books || [];
  } catch { catalogCache = []; }
  return catalogCache;
}

async function searchCatalog(query) {
  const books = await loadCatalog();
  const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 1);
  return books
    .map((b) => {
      const hay = `${b.title} ${b.author} ${(b.tags || []).join(' ')}`.toLowerCase();
      return { b: { ...b, src: 'cat' }, score: words.filter((w) => hay.includes(w)).length };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6)
    .map((x) => x.b);
}

/* ------------------------------------------------------------ агрегатор */
export async function searchBooks(query, lang) {
  const q = query.trim();
  if (!q) return [];
  const [cat, ia, pg] = await Promise.all([
    searchCatalog(q).catch(() => []),
    searchArchive(q, lang).catch(() => []),
    searchGutendex(q).catch(() => []),
  ]);
  if (!cat.length && !ia.length && !pg.length) {
    // если все внешние источники недоступны — это ошибка сети, а не пустой результат
    await fetch('https://archive.org/services/img/stream_only', { mode: 'no-cors' })
      .catch(() => { throw new Error('offline'); });
  }
  const seen = new Set(), out = [];
  for (const b of [...cat, ...ia, ...pg]) {
    const key = `${b.src}:${(b.title || '').toLowerCase().slice(0, 60)}`;
    if (seen.has(key)) continue;
    seen.add(key); out.push(b);
  }
  return out.slice(0, 18);
}

export function bookKey(b) { return `${b.src}:${b.id}`; }
export function fileKey(b, f) { return `${b.src}:${b.id}:${f.fmt}:${f.name || f.url.slice(-24)}`; }
