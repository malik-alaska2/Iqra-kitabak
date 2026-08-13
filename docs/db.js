/* Офлайн-хранилище: избранное (метаданные) и файлы книг (blob) в IndexedDB. */
const DB_NAME = 'kitob';
const DB_VERSION = 1;
let dbPromise = null;

function open() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('favorites')) db.createObjectStore('favorites', { keyPath: 'key' });
      if (!db.objectStoreNames.contains('files')) db.createObjectStore('files', { keyPath: 'key' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

async function tx(store, mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const req = fn(t.objectStore(store));
    t.oncomplete = () => resolve(req?.result);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  });
}

export const favorites = {
  add: (key, book) => tx('favorites', 'readwrite', (s) => s.put({ key, book, at: Date.now() })),
  remove: (key) => tx('favorites', 'readwrite', (s) => s.delete(key)),
  get: (key) => tx('favorites', 'readonly', (s) => s.get(key)),
  async has(key) { return Boolean(await this.get(key)); },
  async list() {
    const all = await tx('favorites', 'readonly', (s) => s.getAll());
    return (all || []).sort((a, b) => b.at - a.at);
  },
};

export const files = {
  put: (key, meta, blob) => tx('files', 'readwrite', (s) => s.put({ key, ...meta, blob, at: Date.now() })),
  get: (key) => tx('files', 'readonly', (s) => s.get(key)),
  remove: (key) => tx('files', 'readwrite', (s) => s.delete(key)),
  async has(key) { return Boolean(await this.get(key)); },
  async list() {
    const all = await tx('files', 'readonly', (s) => s.getAll());
    return (all || []).sort((a, b) => b.at - a.at);
  },
  async keys() {
    const all = await tx('files', 'readonly', (s) => s.getAllKeys());
    return new Set(all || []);
  },
};

/** Скачать файл в хранилище. Возвращает запись или бросает ошибку. */
export async function downloadToLibrary(key, url, meta) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  await files.put(key, { ...meta, url, size: blob.size, type: blob.type }, blob);
  return { key, ...meta, url, size: blob.size, blob };
}
