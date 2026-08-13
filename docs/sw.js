/* Кэш оболочки приложения: интерфейс открывается без интернета.
   Сами книги хранятся в IndexedDB (см. db.js). */
const CACHE = 'kitob-shell-v2';
const SHELL = [
  './', './index.html', './styles.css', './app.js', './i18n.js',
  './sources.js', './db.js', './catalog.json', './manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;

  // Запросы к источникам книг не кэшируем — только сеть.
  if (url.origin !== self.location.origin && !url.host.includes('fonts.')) return;

  // network-first: сначала сеть, кэш — только запасной вариант офлайн.
  // При cache-first браузер навсегда отдавал бы первую загруженную версию
  // и обновления сайта не доходили бы до пользователей.
  e.respondWith(
    fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(e.request).then((hit) => hit || caches.match('./index.html')))
  );
});
