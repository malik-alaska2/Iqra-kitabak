/* Ссылка на книгу для передачи боту.

   Формат один на две стороны: base64url от строки «источник|id|номер файла».
   Его читает bot/sources.py → decode_book_ref, поэтому менять формат можно
   только в обоих местах сразу — на это есть тест tests/booklink.test.mjs.

   Ограничение в 64 символа не наше: столько Telegram разрешает
   в ссылке-приглашении t.me/бот?start=… */

export const REF_LIMIT = 64;

/* Прислать в чат можно только то, что бот сумеет найти сам: книгу своего
   каталога или элемент Archive.org. У Gutenberg такой ветки нет. */
const SENDABLE = new Set(['cat', 'ia']);

export function bookRef(book, index) {
  if (!book || !SENDABLE.has(book.src) || !book.id) return '';
  if (!Number.isInteger(index) || index < 0 || index >= 12) return '';

  const bytes = new TextEncoder().encode(`${book.src}|${book.id}|${index}`);
  const b64 = btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  // Идентификаторы Archive.org иногда длинные — тогда ссылку не строим,
  // и приложение просто не показывает кнопку.
  return b64.length <= REF_LIMIT ? b64 : '';
}
