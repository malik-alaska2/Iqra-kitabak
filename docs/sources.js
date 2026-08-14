/* Источники книг для мини-приложения.
   Если Internet Archive заблокирует запрос из браузера (CORS), укажите адрес
   своего прокси в PROXY — код прокси лежит в proxy/worker.js. */
export const PROXY = '';

const wrap = (url) => (PROXY ? PROXY + encodeURIComponent(url) : url);

const IA_SEARCH = 'https://archive.org/advancedsearch.php';
const IA_META = 'https://archive.org/metadata/';
/* Скачивание — только через /cors/. Обычный /download/ не отдаёт заголовок
   Access-Control-Allow-Origin для PDF и EPUB, поэтому fetch из браузера падал
   с «Failed to fetch» и офлайн-библиотека не наполнялась ни одной книгой.
   Эндпоинт /cors/ отдаёт те же файлы с разрешающим заголовком. */
const IA_DL = 'https://archive.org/cors/';
const GUTENDEX = 'https://gutendex.com/books';
const GOOGLE_BOOKS = 'https://www.googleapis.com/books/v1/volumes';
const EXT_ORDER = { pdf: 0, epub: 1, djvu: 2, txt: 3 };

/* Как язык называется в индексе Internet Archive. Поле language там заполнено
   неровно («Russian», «rus», «ru»), поэтому для фильтра берём полное имя —
   поисковый индекс сам подтягивает варианты, — а для оценки совпадения
   сравниваем по нормализованному коду. */
const IA_LANG = { ar: 'Arabic', ru: 'Russian', uz: 'Uzbek', en: 'English' };
const LANG_CODES = {
  ar: ['ar', 'ara', 'arabic'],
  ru: ['ru', 'rus', 'russian'],
  uz: ['uz', 'uzb', 'uzbek'],
  en: ['en', 'eng', 'english'],
};

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

async function getJSON(url, timeout = 9000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const r = await fetch(wrap(url), { signal: ctrl.signal });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } finally { clearTimeout(timer); }
}

/* --------------------------------------------------- язык самого запроса */
/* Ищем на том языке, на котором человек пишет: арабская вязь → арабский,
   кириллица → русский, латиница → узбекский.
   Узбекский пишут и кириллицей тоже, поэтому отдельно смотрим на буквы
   ў, қ, ғ, ҳ — в русском алфавите их нет. */
const CYRILLIC = /[\u0400-\u04FF]/;
const UZBEK_CYRILLIC = /[\u045E\u040E\u049B\u049A\u0493\u0492\u04B3\u04B2]/;

export function detectQueryLang(query) {
  if (/[\u0600-\u06FF]/.test(query)) return 'ar';
  if (CYRILLIC.test(query)) return UZBEK_CYRILLIC.test(query) ? 'uz' : 'ru';
  if (/[A-Za-z]/.test(query)) return 'uz';
  return '';
}

/* Язык в запросе к Archive.org ровно один — тот, на котором пишет человек.
   Раньше для узбекского был второй заход (английский или русский), но отбор
   ниже строгий: находка с чужой меткой языка всё равно отбрасывается, то есть
   такой заход только тратил запрос. Книги без метки языка ловятся ступенями
   без фильтра — они в лестнице остались. */
function langHints(queryLang) {
  const one = IA_LANG[queryLang];
  return one ? [one] : [];
}

function sameLang(itemLang, code) {
  if (!itemLang || !code) return false;
  const names = LANG_CODES[code] || [];
  const list = Array.isArray(itemLang) ? itemLang : [itemLang];
  return list.some((l) => names.includes(String(l).trim().toLowerCase()));
}

/* Двоеточия и скобки ломают синтаксис запроса Solr — вырезаем их. */
const cleanWord = (w) => w.replace(/["\\:()[\]{}^~*?]/g, ' ').trim();

function words(query) {
  return query.split(/\s+/).map(cleanWord).filter((w) => w.length > 1);
}

/* ------------------------------------------------------- Internet Archive */
/* Лестница запросов: от самого точного к самому широкому. Раньше запрос из
   двух слов склеивался через AND по всему тексту и почти всегда давал ноль
   («hadis toplami» — 0 результатов), а фильтр языка вида
   `language:(Uzbek) OR language:(*)` не фильтровал вообще ничего.
   Теперь идём по ступеням и останавливаемся, как только набрали кандидатов. */
function queryLadder(query, queryLang) {
  const ws = words(query);
  const AND = ws.length ? ws.join(' AND ') : cleanWord(query);
  const OR = ws.length ? ws.join(' OR ') : cleanWord(query);
  const hints = langHints(queryLang);
  const steps = [];

  for (const h of hints) steps.push(`title:(${AND}) AND mediatype:texts AND language:(${h})`);
  for (const h of hints) steps.push(`(${AND}) AND mediatype:texts AND language:(${h})`);
  steps.push(`title:(${AND}) AND mediatype:texts`);
  steps.push(`(${AND}) AND mediatype:texts`);
  if (ws.length > 1) {
    for (const h of hints) steps.push(`(${OR}) AND mediatype:texts AND language:(${h})`);
    steps.push(`title:(${OR}) AND mediatype:texts`);
  }
  return steps;
}

async function iaQuery(q, rows) {
  const params = new URLSearchParams();
  params.set('q', q);
  params.set('rows', String(rows));
  params.set('page', '1');
  params.set('output', 'json');
  params.append('sort[]', 'downloads desc');
  ['identifier', 'title', 'creator', 'year', 'language'].forEach((f) => params.append('fl[]', f));
  const data = await getJSON(`${IA_SEARCH}?${params.toString()}`);
  return data?.response?.docs || [];
}

const norm = (s) => String(s || '').toLowerCase().replace(/[’'`]/g, "'");

/* Оценка попадания: название важнее автора, книга на языке запроса — выше.
   `rank` — место в исходной выдаче (по скачиваниям), уходит в тай-брейк. */
function scoreDoc(doc, ws, queryLang, rank) {
  const title = norm(doc.title);
  const creator = norm(Array.isArray(doc.creator) ? doc.creator.join(' ') : doc.creator);
  let score = 0;
  let hits = 0;
  for (const w of ws) {
    const n = norm(w);
    if (title.includes(n)) { score += 4; hits += 1; }
    else if (creator.includes(n)) { score += 2; hits += 1; }
  }
  if (ws.length && hits === ws.length) score += 6;
  if (sameLang(doc.language, queryLang)) score += 5;
  return score - rank * 0.01;
}

async function iaItem(doc) {
  const ident = doc.identifier;
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
  const creator = Array.isArray(doc.creator) ? doc.creator.slice(0, 2).join(', ') : doc.creator;
  return {
    src: 'ia', id: ident, title: doc.title || ident, author: creator || '',
    year: String(doc.year || '').slice(0, 4),
    cover: `https://archive.org/services/img/${encodeURIComponent(ident)}`,
    page: `https://archive.org/details/${encodeURIComponent(ident)}`,
    files: picked,
  };
}

async function searchArchive(query, queryLang, want = 10) {
  const ws = words(query);
  const found = new Map();

  for (const q of queryLadder(query, queryLang)) {
    let docs = [];
    try { docs = await iaQuery(q, 20); } catch { docs = []; }
    docs.forEach((d, i) => {
      if (!d.identifier || found.has(d.identifier)) return;
      found.set(d.identifier, { doc: d, score: scoreDoc(d, ws, queryLang, i) });
    });
    if (found.size >= 12) break;
  }
  if (!found.size) return [];

  const best = [...found.values()].sort((a, b) => b.score - a.score).slice(0, want + 4);
  const items = await Promise.all(best.map((x) => iaItem(x.doc).catch(() => null)));
  return items.filter(Boolean).slice(0, want);
}

/* --------------------------------------------- строгий отбор по языку */
/* Запрос на арабском должен приводить к арабским книгам, на русском —
   к русским. Одного поля language мало: в Archive.org оно и пустое бывает,
   и неверное — метка Uzbek нередко стоит на изданиях на урду. Поэтому
   смотрим на два признака сразу: объявленный язык и письмо самого названия. */
const SCRIPTS = {
  arabic: /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF]/g,
  cyrillic: /[\u0400-\u04FF]/g,
  latin: /[A-Za-z]/g,
  // деванагари, бенгальский, иврит, тайский, китайский, японский, корейский
  foreign: /[\u0900-\u097F\u0980-\u09FF\u0590-\u05FF\u0E00-\u0E7F\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]/g,
};

export function scriptOf(text) {
  const counts = Object.entries(SCRIPTS)
    .map(([name, re]) => [name, (String(text || '').match(re) || []).length]);
  const [best, n] = counts.sort((a, b) => b[1] - a[1])[0] || ['latin', 0];
  return n ? best : '';
}

/* Коды языков книги — из своего каталога (поле lang) или из метаданных. */
function langCodes(book) {
  const raw = book.lang != null ? book.lang : book.language;
  const list = Array.isArray(raw) ? raw : [raw];
  const codes = new Set();
  for (const value of list) {
    const name = String(value || '').trim().toLowerCase();
    if (!name) continue;
    for (const [code, names] of Object.entries(LANG_CODES)) {
      if (names.includes(name)) codes.add(code);
    }
    if (!Object.values(LANG_CODES).some((names) => names.includes(name))) codes.add(name);
  }
  return [...codes];
}

const NATIVE_SCRIPT = { ar: 'arabic', ru: 'cyrillic', uz: 'latin' };
const EXTRA_SCRIPT = { uz: 'cyrillic' };

export function matchesLang(book, lang) {
  if (!lang) return true;
  const script = scriptOf(book.title);
  if (script === 'foreign') return false;      // деванагари, CJK и прочее — точно мимо

  const declared = langCodes(book);
  if (declared.length) {
    if (!declared.includes(lang)) return false;
    // Язык совпал, но письмо противоречит: так выглядят ошибки метаданных
    // вроде арабской книги с меткой Uzbek.
    return lang === 'ar' || script !== 'arabic';
  }
  // Языка нет — судим по письму названия.
  return script === NATIVE_SCRIPT[lang] || script === EXTRA_SCRIPT[lang];
}

/* --------------------------------------------------------- Google Books */
/* «Ищи в гугле» — вот это оно и есть: у Google Books открытый поиск с полем
   langRestrict, то есть язык ограничивается на стороне самого Google.
   Файлы оттуда браузером не забрать (Google не отдаёт их другому сайту),
   поэтому такие находки открываются на странице источника — зато находятся
   книги, которых нет в Archive.org.
   Без ключа у API есть дневной лимит на адрес; когда он исчерпан, приходит
   429 — тогда просто молча пропускаем источник. */
async function searchGoogleBooks(query, queryLang) {
  const params = new URLSearchParams({ q: query, maxResults: '10', printType: 'books' });
  if (queryLang) params.set('langRestrict', queryLang);
  const data = await getJSON(`${GOOGLE_BOOKS}?${params.toString()}`, 7000);
  return (data.items || []).map((v) => {
    const info = v.volumeInfo || {};
    const access = v.accessInfo || {};
    if (access.viewability === 'NO_PAGES' && !access.publicDomain) return null;
    const cover = (info.imageLinks?.thumbnail || '').replace(/^http:/, 'https:');
    return {
      src: 'gb', id: String(v.id), title: info.title || '',
      author: (info.authors || []).slice(0, 2).join(', '),
      year: String(info.publishedDate || '').slice(0, 4),
      language: info.language || '',
      cover,
      page: info.canonicalVolumeLink || info.infoLink || '',
      files: [],                       // скачивать можно только на стороне Google
    };
  }).filter((b) => b && b.title && b.page);
}

/* ------------------------------------------------------------ Викитека */
/* Разделы Викитеки живут на отдельном домене для каждого языка, поэтому
   язык результата гарантирован самим адресом. Тексты полные — «Сахих
   аль-Бухари» там лежит целиком — и отдаются как TXT в офлайн-библиотеку. */
const WIKISOURCE_HOSTS = { ar: 'ar', ru: 'ru' };   // узбекского раздела нет

function wikisourceApi(host, params) {
  return `https://${host}.wikisource.org/w/api.php?${new URLSearchParams(
    { format: 'json', origin: '*', ...params }).toString()}`;
}

async function searchWikisource(query, queryLang) {
  const host = WIKISOURCE_HOSTS[queryLang];
  if (!host) return [];
  const data = await getJSON(wikisourceApi(host, {
    action: 'query', list: 'search', srsearch: query, srlimit: '5', srnamespace: '0',
  }), 7000);
  return (data?.query?.search || []).map((hit) => ({
    src: 'ws', id: `${host}:${hit.title}`, title: hit.title,
    author: '', year: '', language: queryLang, cover: '',
    page: `https://${host}.wikisource.org/wiki/${encodeURIComponent(hit.title)}`,
    files: [{
      fmt: 'txt', label: 'TXT', size: 0,
      via: 'wikisource',
      url: wikisourceApi(host, {
        action: 'query', prop: 'extracts', explaintext: '1', exlimit: '1', titles: hit.title,
      }),
    }],
  }));
}

/* Викитека отдаёт текст внутри JSON, поэтому просто скачать адрес мало. */
export async function fetchBookFile(file) {
  const res = await fetch(wrap(file.url));
  if (!res.ok) throw new Error(res.status);
  if (file.via !== 'wikisource') return res.blob();
  const data = await res.json();
  const page = Object.values(data?.query?.pages || {})[0] || {};
  const text = page.extract || '';
  if (!text.trim()) throw new Error('пустая страница');
  return new Blob([text], { type: 'text/plain' });
}

/* Запасной выход: обычный поиск Google в браузере. Нужен, когда ни один
   источник ничего не нашёл — пусть человек хотя бы не упирается в стену. */
export function webSearchUrl(query, lang) {
  const hint = { ar: 'كتاب pdf', ru: 'книга pdf', uz: 'kitob pdf' }[lang] || 'pdf';
  const params = new URLSearchParams({ q: `${query} ${hint}` });
  if (lang) params.set('lr', `lang_${lang}`);
  return `https://www.google.com/search?${params.toString()}`;
}

/* ----------------------------------------------------------- Gutenberg */
/* Gutenberg — библиотека в основном англоязычной классики. Для арабских и
   русских запросов она почти всегда пуста, поэтому не тратим на неё время. */
async function searchGutendex(query) {
  const data = await getJSON(`${GUTENDEX}?search=${encodeURIComponent(query)}`, 5000);
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

async function searchCatalog(query, queryLang) {
  const books = await loadCatalog();
  const ws = words(query).map(norm);
  if (!ws.length) return [];
  return books
    .map((b) => {
      const hay = norm(`${b.title} ${b.author} ${(b.tags || []).join(' ')}`);
      let score = ws.filter((w) => hay.includes(w)).length;
      if (score && queryLang && b.lang === queryLang) score += 1;
      return { b: { ...b, src: 'cat' }, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6)
    .map((x) => x.b);
}

/* ------------------------------------------------------------ агрегатор */
/* Порядок важен: сначала свой каталог, потом то, что можно скачать
   (Archive.org, Викитека, Gutenberg), и только затем находки Google Books —
   их читают на стороне источника. */
export async function searchBooks(query, uiLang) {
  const q = query.trim();
  if (!q) return [];
  const queryLang = detectQueryLang(q) || uiLang || 'ru';

  const results = await Promise.all([
    searchCatalog(q, queryLang).catch(() => []),
    searchArchive(q, queryLang).catch(() => []),
    searchWikisource(q, queryLang).catch(() => []),
    queryLang === 'uz' ? searchGutendex(q).catch(() => []) : Promise.resolve([]),
    searchGoogleBooks(q, queryLang).catch(() => []),
  ]);
  const all = results.flat();

  if (!all.length) {
    // если все внешние источники недоступны — это ошибка сети, а не пустой результат
    await fetch('https://archive.org/services/img/stream_only', { mode: 'no-cors' })
      .catch(() => { throw new Error('offline'); });
  }

  // Строгий отбор: книга на другом языке не показывается вообще.
  const seen = new Set(), out = [];
  for (const b of all) {
    if (!matchesLang(b, queryLang)) continue;
    const key = `${b.src}:${norm(b.title).slice(0, 60)}`;
    if (seen.has(key)) continue;
    seen.add(key); out.push(b);
  }
  return out.slice(0, 24);
}

export function bookKey(b) { return `${b.src}:${b.id}`; }
export function fileKey(b, f) { return `${b.src}:${b.id}:${f.fmt}:${f.name || f.url.slice(-24)}`; }
