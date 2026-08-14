/* Чтение книги прямо в приложении, без интернета.

   Раньше открывался только TXT, а PDF и EPUB уходили в системное «Поделиться»
   или в ссылку на скачивание. Внутри Telegram на Android это часто не срабатывает:
   встроенного просмотрщика PDF в WebView нет, и книга просто не открывалась.
   Поэтому оба формата разбираются здесь, локальными библиотеками из docs/vendor.  */

import { unzipSync, strFromU8 } from './vendor/fflate.mjs';

const PDFJS_URL = './vendor/pdf.min.mjs';
const PDFJS_WORKER = './vendor/pdf.worker.min.mjs';
const PDFJS_FONTS = './vendor/standard_fonts/';

export const READABLE = new Set(['txt', 'epub', 'pdf']);

/* --------------------------------------------------------------- общее */

const decoder = new TextDecoder();

function dirOf(path) {
  const i = path.lastIndexOf('/');
  return i < 0 ? '' : path.slice(0, i + 1);
}

/* Склеить относительный путь внутри EPUB: 'OEBPS/text/' + '../img/a.png'. */
function resolvePath(base, rel) {
  const parts = (base + rel).split('/');
  const out = [];
  for (const p of parts) {
    if (!p || p === '.') continue;
    if (p === '..') out.pop();
    else out.push(p);
  }
  return out.join('/');
}

/* ------------------------------------------------------------ TXT */

export async function renderText(blob, host) {
  host.textContent = await blob.text();
  return { destroy() { host.textContent = ''; } };
}

/* ----------------------------------------------------------- EPUB */

const MIME_BY_EXT = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif',
  svg: 'image/svg+xml', webp: 'image/webp',
};

/* Содержимое книги — чужой HTML, поэтому оставляем только разметку текста.
   Скрипты, стили, фреймы и обработчики событий вырезаются целиком. */
const DROP_TAGS = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'LINK', 'META', 'BASE', 'FORM', 'INPUT', 'BUTTON']);

function sanitize(root, resolveImage) {
  for (const node of [...root.querySelectorAll('*')]) {
    if (DROP_TAGS.has(node.tagName)) { node.remove(); continue; }
    for (const attr of [...node.attributes]) {
      const name = attr.name.toLowerCase();
      const value = attr.value || '';
      if (name.startsWith('on')) { node.removeAttribute(attr.name); continue; }
      if ((name === 'href' || name === 'src' || name === 'xlink:href')
          && /^\s*javascript:/i.test(value)) { node.removeAttribute(attr.name); continue; }
      // Вёрстка книги нам не нужна — она ломает единый вид читалки.
      if (name === 'style' || name === 'class' || name === 'width' || name === 'height') {
        node.removeAttribute(attr.name);
      }
    }
    if (node.tagName === 'A') {
      // Внутренние ссылки никуда не ведут: главы склеены в одну страницу.
      const href = node.getAttribute('href') || '';
      if (!/^https?:/i.test(href)) node.removeAttribute('href');
      else { node.setAttribute('target', '_blank'); node.setAttribute('rel', 'noopener noreferrer'); }
    }
    if (node.tagName === 'IMG') {
      const src = node.getAttribute('src');
      const url = src ? resolveImage(src) : '';
      if (url) { node.setAttribute('src', url); node.setAttribute('loading', 'lazy'); }
      else node.remove();
    }
  }
  return root;
}

export async function renderEpub(blob, host) {
  const zip = unzipSync(new Uint8Array(await blob.arrayBuffer()));
  const parser = new DOMParser();
  const urls = [];

  const text = (path) => (zip[path] ? strFromU8(zip[path]) : '');

  // 1. META-INF/container.xml указывает, где лежит OPF — оглавление книги.
  const container = parser.parseFromString(text('META-INF/container.xml'), 'application/xml');
  const opfPath = container.querySelector('rootfile')?.getAttribute('full-path');
  if (!opfPath || !zip[opfPath]) throw new Error('EPUB без OPF');

  const opfDir = dirOf(opfPath);
  const opf = parser.parseFromString(text(opfPath), 'application/xml');

  // 2. manifest — все файлы книги, spine — порядок чтения.
  const manifest = new Map();
  for (const item of opf.querySelectorAll('manifest > item')) {
    manifest.set(item.getAttribute('id'), {
      href: resolvePath(opfDir, item.getAttribute('href') || ''),
      type: item.getAttribute('media-type') || '',
    });
  }
  const spine = [...opf.querySelectorAll('spine > itemref')]
    .map((ref) => manifest.get(ref.getAttribute('idref')))
    .filter((it) => it && /xhtml|html/.test(it.type));
  if (!spine.length) throw new Error('EPUB без глав');

  // 3. Картинки достаём из архива и подменяем ссылки на blob.
  const imageCache = new Map();
  const imageFor = (chapterDir) => (src) => {
    const path = /^(https?:|data:)/i.test(src) ? src : resolvePath(chapterDir, src);
    if (/^(https?:|data:)/i.test(path)) return path;
    if (imageCache.has(path)) return imageCache.get(path);
    const bytes = zip[path];
    if (!bytes) return '';
    const ext = path.split('.').pop().toLowerCase();
    const url = URL.createObjectURL(new Blob([bytes], { type: MIME_BY_EXT[ext] || 'application/octet-stream' }));
    urls.push(url);
    imageCache.set(path, url);
    return url;
  };

  host.textContent = '';
  const frag = document.createDocumentFragment();
  for (const item of spine) {
    const raw = zip[item.href];
    if (!raw) continue;
    const doc = parser.parseFromString(decoder.decode(raw), 'application/xhtml+xml');
    const body = doc.querySelector('body') || doc.documentElement;
    if (!body) continue;
    const section = document.createElement('section');
    section.className = 'reader__chapter';
    // Направление письма берём из самой главы: арабская книга должна
    // читаться справа налево независимо от языка интерфейса.
    const root = doc.documentElement;
    const dir = body.getAttribute('dir') || root?.getAttribute('dir');
    const chapterLang = body.getAttribute('lang') || root?.getAttribute('lang')
      || root?.getAttributeNS?.('http://www.w3.org/XML/1998/namespace', 'lang');
    if (dir) section.setAttribute('dir', dir);
    else if (chapterLang && /^(ar|fa|ur|he)/i.test(chapterLang)) section.setAttribute('dir', 'rtl');
    if (chapterLang) section.setAttribute('lang', chapterLang);
    section.innerHTML = body.innerHTML;
    sanitize(section, imageFor(dirOf(item.href)));
    frag.append(section);
  }
  host.append(frag);

  return {
    destroy() {
      urls.forEach((u) => URL.revokeObjectURL(u));
      host.textContent = '';
    },
  };
}

/* ------------------------------------------------------------ PDF */

let pdfjsPromise = null;
function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(PDFJS_URL).then((lib) => {
      lib.GlobalWorkerOptions.workerSrc = new URL(PDFJS_WORKER, import.meta.url).href;
      return lib;
    });
  }
  return pdfjsPromise;
}

/* Страницы рисуются по мере прокрутки: у книги может быть шестьсот страниц,
   и рисовать их все сразу — верный способ уронить вкладку по памяти. */
export async function renderPdf(blob, host, { onPage } = {}) {
  const lib = await loadPdfjs();
  const data = new Uint8Array(await blob.arrayBuffer());
  const doc = await lib.getDocument({
    data,
    standardFontDataUrl: new URL(PDFJS_FONTS, import.meta.url).href,
    isEvalSupported: false,
  }).promise;

  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let zoom = 1;
  const pages = [];
  host.textContent = '';

  for (let n = 1; n <= doc.numPages; n += 1) {
    const wrap = document.createElement('div');
    wrap.className = 'reader__pdf-page';
    wrap.dataset.page = String(n);
    host.append(wrap);
    pages.push({ n, wrap, canvas: null, task: null, rendered: false });
  }

  async function draw(entry) {
    if (entry.rendered) return;
    entry.rendered = true;
    const page = await doc.getPage(entry.n);
    const base = page.getViewport({ scale: 1 });
    // Вписываем страницу в ширину экрана, дальше масштаб меняют кнопками.
    // Ширина может быть нулевой, если читалку ещё не показали, — тогда берём
    // запасное значение, иначе холст выйдет нулевого размера и останется пустым.
    const width = host.clientWidth || window.innerWidth || 800;
    const fit = width / base.width;
    const viewport = page.getViewport({ scale: fit * zoom * dpr });
    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = '100%';
    entry.canvas = canvas;
    entry.wrap.textContent = '';
    entry.wrap.append(canvas);
    entry.task = page.render({ canvasContext: canvas.getContext('2d'), viewport });
    try { await entry.task.promise; } catch (e) { entry.rendered = false; }
  }

  // Держим отрисованными только видимые страницы и соседние.
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const entry = pages[Number(e.target.dataset.page) - 1];
      if (!entry) continue;
      if (e.isIntersecting) {
        draw(entry);
        onPage?.(entry.n, doc.numPages);
      }
    }
  }, { root: host, rootMargin: '200% 0px' });
  pages.forEach((p) => io.observe(p.wrap));

  // Резервируем высоту, чтобы полоса прокрутки не прыгала до отрисовки.
  const first = await doc.getPage(1);
  const v = first.getViewport({ scale: 1 });
  pages.forEach((p) => { p.wrap.style.aspectRatio = `${v.width} / ${v.height}`; });

  // Первую страницу рисуем всегда, не дожидаясь наблюдателя: если контейнер
  // ещё без размеров, IntersectionObserver не сработает и экран останется пустым.
  await draw(pages[0]);
  onPage?.(1, doc.numPages);

  return {
    zoom(delta) {
      zoom = Math.min(3, Math.max(0.6, zoom + delta));
      pages.forEach((p) => {
        p.task?.cancel?.();
        p.rendered = false;
        p.canvas = null;
        p.wrap.textContent = '';
      });
      pages.filter((p) => p.wrap.getBoundingClientRect().top < window.innerHeight * 2).forEach(draw);
    },
    destroy() {
      io.disconnect();
      pages.forEach((p) => p.task?.cancel?.());
      doc.destroy();
      host.textContent = '';
    },
  };
}

/* --------------------------------------------------------- диспетчер */

export async function open(record, host, opts) {
  if (record.fmt === 'txt') return renderText(record.blob, host);
  if (record.fmt === 'epub') return renderEpub(record.blob, host);
  if (record.fmt === 'pdf') return renderPdf(record.blob, host, opts);
  throw new Error('формат без читалки: ' + record.fmt);
}
