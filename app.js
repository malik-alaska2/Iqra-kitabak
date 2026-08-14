import { T, TOPIC_QUERIES, LANGS, detectLang } from './i18n.js';
import { searchBooks, humanSize, bookKey, fileKey, fetchBookFile, webSearchUrl,
  detectQueryLang } from './sources.js';
import { favorites, files, saveToLibrary } from './db.js';
import { open as openInReader, READABLE } from './reader.js';
import { bookRef } from './booklink.js';

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

function showState(title, text, spinner = false, extra = '') {
  el.state.innerHTML = title || text || extra
    ? `${spinner ? '<div class="spinner"></div>' : ''}<b>${title || ''}</b>${text || ''}${extra}` : '';
}

/* Когда ни один источник ничего не дал, предлагаем обычный поиск Google —
   лучше так, чем упереться в «ничего не нашлось». */
function webSearchButton(query) {
  const url = webSearchUrl(query, detectQueryLang(query) || lang);
  return `<button class="btn state__btn" data-web="${escape(url)}">${T[lang].search_web}</button>`;
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
    if (!books.length) {
      return showState(T[lang].nothing_title, T[lang].nothing_text, false, webSearchButton(query));
    }
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
    <p class="label">${(book.files || []).length ? t.versions : t.web_only}</p>
    ${(book.files || []).map((f, i) => {
      const has = stored.has(fileKey(book, f));
      const sendable = canSendToChat() && bookRef(book, i);
      return `<div class="file-row">
        <button class="file" data-file-i="${i}">
          <span class="file__fmt">${f.fmt.toUpperCase()}</span>
          <span class="file__note">${f.size ? humanSize(f.size) : t.size_unknown}${f.scan ? ' · scan' : ''}</span>
          <span class="file__go">${has ? '✓' : '↓'}</span>
        </button>
        ${sendable ? `<button class="file-send" data-send-i="${i}" title="${t.send_to_chat}" aria-label="${t.send_to_chat}">📩</button>` : ''}
      </div>`;
    }).join('')}
    <div class="actions">
      <button class="btn ${isFav ? 'btn--danger' : ''}" data-fav="${escape(key)}">${isFav ? t.unsave : t.save}</button>
      ${book.page ? `<button class="btn" data-web="${escape(book.page)}">${t.open_web}</button>` : ''}
    </div>`;

  el.sheetBody.dataset.book = JSON.stringify(book);
  el.sheet.hidden = false;
  syncBackButton();
}

function closeSheet() { el.sheet.hidden = true; syncBackButton(); }

/* Кнопка «назад» в шапке Telegram видна, только когда есть что закрывать. */
function syncBackButton() {
  const open = !el.reader.hidden || !el.sheet.hidden;
  if (open) tg?.BackButton?.show?.(); else tg?.BackButton?.hide?.();
}

/* ------------------------------------------- отправка книги в чат Telegram */
/* Книгу можно не только сохранить в приложении, но и попросить бота прислать
   её в чат — тогда файл лежит в переписке и не зависит от памяти браузера.
   Путей два, и какой доступен, решает способ запуска приложения:
   из кнопки клавиатуры доступен sendData, из кнопки меню — только ссылка
   вида t.me/бот?start=…, для которой нужно имя бота. Имя бот подставляет
   в адрес сам, а мы запоминаем его на будущие запуски. */
const botUsername = (() => {
  const fromHash = /(?:^|[#&])bot=([A-Za-z0-9_]{3,64})/.exec(location.hash || '');
  if (fromHash) {
    localStorage.setItem('kitob_bot', fromHash[1]);
    return fromHash[1];
  }
  return localStorage.getItem('kitob_bot') || '';
})();

const canSendData = () => Boolean(tg?.initDataUnsafe?.query_id);
const canSendToChat = () => Boolean(tg) && (canSendData() || Boolean(botUsername));

function sendToChat(book, index) {
  const ref = bookRef(book, index);
  if (!ref) { toast(T[lang].send_unavailable); return false; }
  if (canSendData()) {
    tg.sendData(JSON.stringify({ action: 'send', ref }));   // приложение закроется
    return true;
  }
  if (botUsername) {
    tg.openTelegramLink(`https://t.me/${botUsername}?start=${ref}`);
    return true;
  }
  toast(T[lang].send_unavailable);
  return false;
}

/* ------------------------------------------------- скачивание и открытие */
async function handleDownload(book, index) {
  const f = book.files[index];
  const key = fileKey(book, f);
  const existing = await files.get(key);
  if (existing) return openStored(existing);

  toast(T[lang].downloading);
  try {
    const blob = await fetchBookFile(f);
    const rec = await saveToLibrary(key, blob, {
      title: book.title, author: book.author, fmt: f.fmt, url: f.url,
      src: book.src, bookId: book.id, page: book.page,
    });
    haptic('medium');
    toast(T[lang].downloaded);
    closeSheet();
    openStored(rec);
  } catch (e) {
    // Скачать в приложение не вышло — обычно это блокировка сети.
    // Просим бота прислать книгу в чат и только в крайнем случае
    // отправляем человека на страницу источника.
    if (canSendToChat() && sendToChat(book, index)) {
      toast(T[lang].sent_to_chat);
      return;
    }
    toast(T[lang].dl_failed);
    if (book.page) tg ? tg.openLink(book.page) : window.open(book.page, '_blank');
  }
}

const MIME = { pdf: 'application/pdf', epub: 'application/epub+zip', txt: 'text/plain', djvu: 'image/vnd.djvu' };

async function openStored(rec) {
  const record = rec.blob ? rec : await files.get(rec.key);
  if (!record) return;
  // PDF, EPUB \u0438 TXT \u0447\u0438\u0442\u0430\u044E\u0442\u0441\u044F \u0432\u043D\u0443\u0442\u0440\u0438 \u043F\u0440\u0438\u043B\u043E\u0436\u0435\u043D\u0438\u044F; \u043E\u0441\u0442\u0430\u043B\u044C\u043D\u043E\u0435 \u043E\u0442\u0434\u0430\u0451\u043C \u0441\u0438\u0441\u0442\u0435\u043C\u0435.
  if (READABLE.has(record.fmt)) return openReader(record);
  return shareStored(record);
}

async function shareStored(record) {
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
let reading = null;          // текущий контроллер читалки
let readingRecord = null;

async function openReader(record) {
  closeReader();
  readingRecord = record;
  el.readerTitle.textContent = record.title;
  el.readerPage.dataset.fmt = record.fmt;
  el.readerPage.style.setProperty('--read-size', `${readSize}px`);
  el.reader.hidden = false;
  el.readerPage.scrollTop = 0;
  el.readerPage.textContent = '';
  syncBackButton();
  setReaderNote(T[lang].opening);

  try {
    reading = await openInReader(record, el.readerPage, {
      onPage: (n, total) => setReaderNote(`${n} / ${total}`),
    });
    if (record.fmt !== 'pdf') setReaderNote('');
  } catch (e) {
    // Битый или нестандартный файл — не оставляем пустой экран.
    closeReader();
    toast(T[lang].read_failed);
    shareStored(record);
  }
}

function closeReader() {
  reading?.destroy?.();
  reading = null;
  readingRecord = null;
  el.reader.hidden = true;
  el.readerPage.removeAttribute('data-fmt');
  setReaderNote('');
  syncBackButton();
}

function setReaderNote(text) {
  const note = $('readerNote');
  if (note) note.textContent = text;
}

/* У текста меняется кегль, у PDF — масштаб страницы. Кнопки те же. */
function zoomReader(delta) {
  if (readingRecord?.fmt === 'pdf') return reading?.zoom?.(delta * 0.25);
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

el.state.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-web]');
  if (!btn) return;
  haptic();
  const url = btn.dataset.web;
  tg ? tg.openLink(url) : window.open(url, '_blank');
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

  const sendBtn = e.target.closest('[data-send-i]');
  if (sendBtn) { haptic('medium'); return sendToChat(book, Number(sendBtn.dataset.sendI)); }

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

$('readerClose').addEventListener('click', closeReader);
$('fontPlus').addEventListener('click', () => zoomReader(1));
$('fontMinus').addEventListener('click', () => zoomReader(-1));
$('readerShare').addEventListener('click', () => { if (readingRecord) shareStored(readingRecord); });

// Кнопка «назад» в Telegram должна закрывать читалку или карточку,
// а не выбрасывать из приложения.
tg?.BackButton?.onClick?.(() => {
  if (!el.reader.hidden) closeReader();
  else if (!el.sheet.hidden) closeSheet();
});

/* ---------------------------------------------------------------- старт */
applyLang();
showState(T[lang].empty_title, T[lang].empty_text);
files.keys().then((k) => { offlineKeys = k; });

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
