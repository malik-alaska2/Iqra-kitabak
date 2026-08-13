import { T, TOPIC_QUERIES, LANGS, detectLang } from './i18n.js';
import { searchBooks, humanSize, bookKey, fileKey } from './sources.js';
import { favorites, files, downloadToLibrary } from './db.js';

const tg = window.Telegram?.WebApp;
const $ = (id) => document.getElementById(id);
const el = { q: $('q'), go: $('goBtn'), list: $('list'), state: $('state'), topics: $('topics'),
  sheet: $('sheet'), sheetBody: $('sheetBody'), toast: $('toast'), langBtn: $('langBtn'),
  langSheet: $('langSheet'), reader: $('reader'), readerPage: $('readerPage'), readerTitle: $('readerTitle') };

let lang = detectLang();
let tab = 'search';
let lastResults = [];
let offlineKeys = new Set();

/* ------------------------------------------------------------- Telegram */
if (tg) {
  tg.ready();
  tg.expand();
  if (tg.colorScheme === 'dark') document.documentElement.classList.add('dark');
  tg.onEvent?.('themeChanged', () => {
    document.documentElement.classList.toggle('dark', tg.colorScheme === 'dark');
  });
} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
  document.documentElement.classList.add('dark');
}
const haptic = (type = 'light') => tg?.HapticFeedback?.impactOccurred?.(type);

/* --------------------------------------------------------------- язык */
function applyLang() {
  const t = T[lang];
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  el.q.placeholder = t.search_ph;
  el.langBtn.textContent = lang.toUpperCase();
  document.querySelectorAll('[data-i18n]').forEach((n) => { n.textContent = t[n.dataset.i18n] || ''; });
  el.topics.innerHTML = Object.keys(TOPIC_QUERIES)
    .map((k) => `<button data-topic="${k}">${t.topics[k]}</button>`).join('');
  localStorage.setItem('kitob_lang', lang);
}

/* ------------------------------------------------------------ утилиты */
function toast(text) {
  el.toast.textContent = text;
  el.toast.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.toast.hidden = true; }, 2400);
}

function showState(title, text, spinner = false) {
  el.state.innerHTML = title || text
    ? `${spinner ? '<div class="spinner"></div>' : ''}<b>${title || ''}</b>${text || ''}` : '';
}

const escape = (s) => String(s || '').replace(/[&<>"]/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function bestFmt(book) {
  const order = ['pdf', 'epub', 'txt', 'djvu'];
  return order.find((f) => book.files?.some((x) => x.fmt === f)) || 'pdf';
}

/* ------------------------------------------------------- отрисовка списка */
async function renderBooks(books, { savedKeys } = {}) {
  const t = T[lang];
  const saved = savedKeys || new Set((await favorites.list()).map((x) => x.key));
  offlineKeys = await files.keys();
  el.list.innerHTML = books.map((b, i) => {
    const fmts = [...new Set((b.files || []).map((f) => f.fmt.toUpperCase()))].slice(0, 4);
    const isOffline = [...offlineKeys].some((k) => k.startsWith(`${b.src}:${b.id}:`));
    return `
      <article class="card" data-i="${i}" data-kind="${bestFmt(b)}">
        ${b.cover ? `<img class="card__cover" src="${escape(b.cover)}" alt="" loading="lazy" onerror="this.remove()">` : ''}
        <div class="card__body">
          <h3 class="card__title">${escape(b.title)}</h3>
          <p class="card__meta">${escape([b.author, b.year].filter(Boolean).join(' · '))}</p>
          <div class="card__tags">
            ${fmts.map((f) => `<span class="tag">${f}</span>`).join('')}
            ${saved.has(bookKey(b)) ? `<span class="tag tag--saved">★ ${t.saved}</span>` : ''}
            ${isOffline ? `<span class="tag tag--saved">${t.offline_tag}</span>` : ''}
          </div>
        </div>
      </article>`;
  }).join('');
  lastResults = books;
}

/* ------------------------------------------------------------- поиск */
async function runSearch(query) {
  if (!query.trim()) return;
  tab = 'search';
  setActiveTab('search');
  el.list.innerHTML = '';
  showState(T[lang].searching, '', true);
  try {
    const books = await searchBooks(query, lang);
    if (!books.length) return showState(T[lang].nothing_title, T[lang].nothing_text);
    showState('', '');
    await renderBooks(books);
  } catch (e) {
    showState(T[lang].error_title, T[lang].error_text);
  }
}

/* --------------------------------------------------------- вкладки */
function setActiveTab(name) {
  document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('is-active', b.dataset.tab === name));
}

async function openSaved() {
  tab = 'saved'; setActiveTab('saved');
  const items = await favorites.list();
  el.list.innerHTML = '';
  if (!items.length) return showState(T[lang].saved_empty_title, T[lang].saved_empty_text);
  showState('', '');
  await renderBooks(items.map((x) => x.book), { savedKeys: new Set(items.map((x) => x.key)) });
}

async function openOffline() {
  tab = 'offline'; setActiveTab('offline');
  const items = await files.list();
  el.list.innerHTML = '';
  if (!items.length) return showState(T[lang].offline_empty_title, T[lang].offline_empty_text);
  showState('', '');
  el.list.innerHTML = items.map((f, i) => `
    <article class="card" data-file="${escape(f.key)}" data-kind="${f.fmt}">
      <div class="card__body">
        <h3 class="card__title">${escape(f.title)}</h3>
        <p class="card__meta">${escape(f.author || '')}</p>
        <div class="card__tags">
          <span class="tag">${f.fmt.toUpperCase()}</span>
          <span class="tag">${humanSize(f.size)}</span>
          <span class="tag tag--saved">${T[lang].offline_tag}</span>
        </div>
      </div>
    </article>`).join('');
}

/* -------------------------------------------------- карточка книги */
async function openBook(book) {
  const t = T[lang];
  const key = bookKey(book);
  const isFav = await favorites.has(key);
  const stored = await files.keys();

  el.sheetBody.innerHTML = `
    <h2 class="sheet__h">${escape(book.title)}</h2>
    <p class="sheet__sub">${escape([book.author, book.year].filter(Boolean).join(' · '))}</p>
    <p class="label">${t.versions}</p>
    ${(book.files || []).map((f, i) => {
      const has = stored.has(fileKey(book, f));
      return `<button class="file" data-file-i="${i}">
        <span class="file__fmt">${f.fmt.toUpperCase()}</span>
        <span class="file__note">${f.size ? humanSize(f.size) : t.size_unknown}${f.scan ? ' · scan' : ''}</span>
        <span class="file__go">${has ? '✓' : '↓'}</span>
      </button>`;
    }).join('')}
    <div class="actions">
      <button class="btn ${isFav ? 'btn--danger' : ''}" data-fav="${escape(key)}">${isFav ? t.unsave : t.save}</button>
      ${book.page ? `<button class="btn" data-web="${escape(book.page)}">${t.open_web}</button>` : ''}
    </div>`;

  el.sheetBody.dataset.book = JSON.stringify(book);
  el.sheet.hidden = false;
}

function closeSheet() { el.sheet.hidden = true; }

/* ------------------------------------------------- скачивание и открытие */
async function handleDownload(book, index) {
  const f = book.files[index];
  const key = fileKey(book, f);
  const existing = await files.get(key);
  if (existing) return openStored(existing);

  toast(T[lang].downloading);
  try {
    const rec = await downloadToLibrary(key, f.url, {
      title: book.title, author: book.author, fmt: f.fmt, src: book.src, bookId: book.id, page: book.page,
    });
    haptic('medium');
    toast(T[lang].downloaded);
    closeSheet();
    openStored(rec);
  } catch (e) {
    toast(T[lang].dl_failed);
    if (book.page) tg ? tg.openLink(book.page) : window.open(book.page, '_blank');
  }
}

const MIME = { pdf: 'application/pdf', epub: 'application/epub+zip', txt: 'text/plain', djvu: 'image/vnd.djvu' };

async function openStored(rec) {
  const record = rec.blob ? rec : await files.get(rec.key);
  if (!record) return;
  if (record.fmt === 'txt') return openReader(record);

  const name = `${record.title.slice(0, 60).replace(/[^\w\s\u0400-\u04FF\u0600-\u06FF-]/g, '').trim() || 'book'}.${record.fmt}`;
  const type = record.type || MIME[record.fmt] || 'application/octet-stream';

  // На телефоне системное меню «Поделиться» надёжнее: книгу можно открыть
  // в читалке или сохранить в файлы — всё это работает без интернета.
  try {
    const file = new File([record.blob], name, { type });
    if (navigator.canShare?.({ files: [file] })) {
      await navigator.share({ files: [file], title: record.title });
      return;
    }
  } catch (e) {
    if (e.name === 'AbortError') return;
  }

  const url = URL.createObjectURL(record.blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.target = '_blank';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

/* --------------------------------------------------------------- читалка */
let readSize = Number(localStorage.getItem('kitob_read_size') || 17);

async function openReader(record) {
  const text = await record.blob.text();
  el.readerTitle.textContent = record.title;
  el.readerPage.textContent = text;
  el.readerPage.style.setProperty('--read-size', `${readSize}px`);
  el.reader.hidden = false;
  el.readerPage.scrollTop = 0;
}

function setReadSize(delta) {
  readSize = Math.min(28, Math.max(13, readSize + delta));
  localStorage.setItem('kitob_read_size', String(readSize));
  el.readerPage.style.setProperty('--read-size', `${readSize}px`);
}

/* -------------------------------------------------------------- события */
el.go.addEventListener('click', () => runSearch(el.q.value));
el.q.addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(el.q.value); });

el.topics.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-topic]');
  if (!btn) return;
  const q = TOPIC_QUERIES[btn.dataset.topic][lang];
  el.q.value = q;
  haptic();
  runSearch(q);
});

el.list.addEventListener('click', async (e) => {
  const card = e.target.closest('.card');
  if (!card) return;
  haptic();
  if (card.dataset.file) {
    const rec = await files.get(card.dataset.file);
    if (rec) openStored(rec);
    return;
  }
  openBook(lastResults[Number(card.dataset.i)]);
});

el.sheet.addEventListener('click', async (e) => {
  if (e.target === el.sheet || e.target.id === 'sheetClose') return closeSheet();
  const book = el.sheetBody.dataset.book ? JSON.parse(el.sheetBody.dataset.book) : null;
  if (!book) return;

  const fileBtn = e.target.closest('[data-file-i]');
  if (fileBtn) return handleDownload(book, Number(fileBtn.dataset.fileI));

  const favBtn = e.target.closest('[data-fav]');
  if (favBtn) {
    const key = favBtn.dataset.fav;
    if (await favorites.has(key)) {
      await favorites.remove(key);
      favBtn.textContent = T[lang].save;
      favBtn.classList.remove('btn--danger');
      toast(T[lang].removed);
    } else {
      await favorites.add(key, book);
      favBtn.textContent = T[lang].unsave;
      favBtn.classList.add('btn--danger');
      toast(T[lang].saved);
    }
    if (tab === 'saved') openSaved();
    return;
  }

  const webBtn = e.target.closest('[data-web]');
  if (webBtn) {
    const url = webBtn.dataset.web;
    tg ? tg.openLink(url) : window.open(url, '_blank');
  }
});

document.querySelectorAll('.tab').forEach((b) => b.addEventListener('click', () => {
  haptic();
  if (b.dataset.tab === 'search') { tab = 'search'; setActiveTab('search'); el.list.innerHTML = '';
    showState(T[lang].empty_title, T[lang].empty_text); }
  if (b.dataset.tab === 'saved') openSaved();
  if (b.dataset.tab === 'offline') openOffline();
}));

el.langBtn.addEventListener('click', () => { el.langSheet.hidden = false; });
el.langSheet.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-lang]');
  if (btn && LANGS.includes(btn.dataset.lang)) {
    lang = btn.dataset.lang;
    applyLang();
    if (tab === 'saved') openSaved(); else if (tab === 'offline') openOffline();
    else showState(T[lang].empty_title, T[lang].empty_text);
  }
  el.langSheet.hidden = true;
});

$('readerClose').addEventListener('click', () => { el.reader.hidden = true; });
$('fontPlus').addEventListener('click', () => setReadSize(1));
$('fontMinus').addEventListener('click', () => setReadSize(-1));

/* ---------------------------------------------------------------- старт */
applyLang();
showState(T[lang].empty_title, T[lang].empty_text);
files.keys().then((k) => { offlineKeys = k; });

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
