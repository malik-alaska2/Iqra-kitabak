# Kitob — Telegram-бот и мини-приложение для книг

Поиск книг в открытых источниках, выбор версии и формата, избранное и офлайн-доступ.
Три языка интерфейса: **o‘zbekcha / русский / العربية** (арабский — с RTL-версткой).
Два способа использования: **обычный бот** и **Mini App** — данные и логика общие.

---

## Что умеет

| | Бот | Мини-приложение |
|---|---|---|
| Поиск по названию/автору | ✅ | ✅ |
| Разделы: Коран и тафсир, хадис, фикх, акыда, сира | ✅ | ✅ |
| Несколько версий одной книги (PDF / EPUB / TXT, оригинал и скан, размер файла) | ✅ | ✅ |
| Избранное | ✅ (в базе бота) | ✅ (IndexedDB) |
| Офлайн после скачивания | ✅ файл остаётся в чате Telegram | ✅ blob в IndexedDB + читалка TXT |
| Мгновенная повторная отправка | ✅ кэш `file_id` | ✅ из памяти устройства |
| Переключение языка | ✅ | ✅ |

Источники: **свой каталог `catalog.json`** → **Internet Archive** → **Project Gutenberg**.
Все три отдают книги легально; собственный каталог показывается первым — туда добавляйте
издания, на распространение которых у вас есть право (вакфы, общественное достояние, ваши файлы).

---

> **Быстрый старт:** токен уже вписан в `.env`. Windows — запустите `start.bat`,
> macOS/Linux — `./start.sh`. Пошаговая инструкция с деплоем — в файле [START.md](START.md).

---

## Структура

```
bot/            бот на aiogram 3 (Python)
  main.py       хендлеры, поиск, отправка файлов
  sources.py    поиск в источниках, разбор форматов
  storage.py    SQLite: язык, избранное, «мои книги», кэш file_id
  i18n.py       переводы uz/ru/ar
  keyboards.py  клавиатуры
webapp/         мини-приложение (статика для GitHub Pages)
  index.html app.js styles.css i18n.js sources.js db.js sw.js catalog.json
proxy/          необязательный CORS-прокси на Cloudflare Workers
.github/workflows/pages.yml   автодеплой мини-приложения
.github/workflows/bot.yml     запасной запуск бота внутри Actions
```

---

## 1. Запуск бота

```bash
git clone <ваш-репозиторий> kitob && cd kitob
cp .env.example .env          # впишите BOT_TOKEN от @BotFather
pip install -r bot/requirements.txt
python bot/main.py
```

Через Docker:

```bash
docker build -t kitob -f bot/Dockerfile .
docker run -d --name kitob --env-file .env -v kitob-data:/data kitob
```

## 2. Мини-приложение на GitHub Pages

1. Залейте репозиторий на GitHub, ветка `main`.
2. **Settings → Pages → Source: GitHub Actions**. Workflow `pages.yml` опубликует папку `webapp`.
3. Получите адрес вида `https://USERNAME.github.io/kitob/`.
4. Впишите его в `.env` → `WEBAPP_URL=` и перезапустите бота — появится кнопка «📱 Приложение».
5. В @BotFather: `/mybots → Bot Settings → Menu Button → Edit menu button URL` — тот же адрес.
   Тогда приложение открывается кнопкой рядом с полем ввода.

## 3. Где держать бота бесплатно

GitHub Pages отдаёт только статику, поэтому бот там жить не может. Рабочие бесплатные варианты:

- **Koyeb / Render / Fly.io** — деплой из репозитория по `bot/Dockerfile`, контейнер работает постоянно. Рекомендую.
- **`.github/workflows/bot.yml`** — запасной вариант, бот крутится в Actions и перезапускается каждые ~5 часов.
  Добавьте секрет `BOT_TOKEN` (Settings → Secrets → Actions) и переменную `WEBAPP_URL`.
  Минус: короткие перерывы при перезапуске и хранение базы в артефакте.
- **Свой мини-сервер / VPS** — `docker run` из примера выше.

## 4. Если поиск не работает в мини-приложении

Браузер может заблокировать запросы к archive.org из-за CORS. Тогда:

```bash
cd proxy && npx wrangler deploy      # бесплатный Cloudflare Workers
```

Полученный адрес впишите в `webapp/sources.js`:

```js
export const PROXY = 'https://kitob-proxy.ВАШ-АККАУНТ.workers.dev/?u=';
```

Бот работает без прокси в любом случае — он ходит в источники со своего сервера.

## 5. Свой каталог книг

`webapp/catalog.json` — общий для бота и приложения. Формат одной книги лежит там же в поле `_template`:

```json
{
  "id": "riyad-us-salihin-uz",
  "title": "Riyoz us-solihiyn",
  "author": "Imom Nawawiy",
  "year": "2019",
  "tags": ["hadis", "хадисы", "الحديث"],
  "page": "https://example.org/riyad",
  "files": [
    { "fmt": "pdf", "label": "PDF", "url": "https://example.org/riyad.pdf", "size": 8400000, "quality": "orig" }
  ]
}
```

Книги из каталога всегда идут первыми в результатах — так вы контролируете, какие издания
пользователи видят в первую очередь.

---

## Ограничения, о которых стоит знать

- Telegram не даёт боту отправить файл больше **50 МБ** — такие книги бот присылает ссылкой.
- Мини-приложение хранит книги в памяти браузера Telegram; при очистке данных приложения они удалятся.
  Поэтому важные книги полезно скачать и через бота — в чате файл лежит постоянно.
- Поиск идёт по открытым каталогам; качество метаданных у Internet Archive неровное,
  поэтому в карточке всегда показываются размер файла и пометка `scan` для сканов.
