"""Kitob — Telegram-бот для поиска и чтения книг (uz / ru / ar).

Запуск:  python bot/main.py
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import os
import re
import tempfile

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

import keyboards as kb
import sources
import storage as db
from config import load_settings
from i18n import LANGS, TOPIC_QUERIES, menu_labels, t

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kitob")

settings = load_settings()
router = Router()
MENU = menu_labels()


# ----------------------------------------------------------------- утилиты
def book_key(book: dict, fmt: str = "") -> str:
    raw = f"{book.get('src')}:{book.get('id')}:{fmt}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


async def lang_of(user_id: int) -> str:
    return await db.get_lang(user_id) or "ru"


def esc(text: str) -> str:
    return html.escape(text or "")


def book_line(i: int, b: dict) -> str:
    parts = [f"<b>{i}.</b> {esc(b['title'])}"]
    meta = " · ".join(x for x in (esc(b.get("author", "")), b.get("year", "")) if x)
    if meta:
        parts.append(f"\n    <i>{meta}</i>")
    fmts = " ".join(sorted({f["label"] for f in b.get("files", [])}))
    if fmts:
        parts.append(f"\n    <code>{fmts}</code>")
    return "".join(parts)


def render_list(lang: str, books: list[dict], page: int) -> tuple[str, InlineKeyboardMarkup]:
    per = settings.results_per_page
    total_pages = max(1, (len(books) + per - 1) // per)
    page = max(0, min(page, total_pages - 1))
    start = page * per
    chunk = books[start:start + per]

    head = t(lang, "results", n=len(books))
    body = "\n\n".join(book_line(start + i + 1, b) for i, b in enumerate(chunk))
    foot = "\n\n" + t(lang, "page", cur=page + 1, total=total_pages) if total_pages > 1 else ""
    return f"{head}\n\n{body}{foot}", kb.results_kb(lang, 0, page, total_pages, start, len(chunk))


def render_card(lang: str, b: dict) -> str:
    lines = [f"📚 <b>{esc(b['title'])}</b>"]
    if b.get("author"):
        lines.append(f"{t(lang, 'author')}: {esc(b['author'])}")
    if b.get("year"):
        lines.append(f"{t(lang, 'year')}: {b['year']}")
    src_name = {"ia": "Internet Archive", "pg": "Project Gutenberg", "cat": "Kitob"}.get(b.get("src"), "")
    if src_name:
        lines.append(f"{t(lang, 'source')}: {src_name}")
    lines.append("")
    lines.append(t(lang, "formats"))
    return "\n".join(lines)


# ------------------------------------------------------------------ /start
@router.message(CommandStart())
async def cmd_start(msg: Message):
    lang = await db.get_lang(msg.from_user.id)
    if not lang:
        guess = (msg.from_user.language_code or "ru")[:2]
        lang = guess if guess in LANGS else "ru"
        await db.set_lang(msg.from_user.id, lang)
        await msg.answer(t(lang, "choose_lang"), reply_markup=kb.lang_kb())
    await msg.answer(t(lang, "start"), reply_markup=kb.main_menu(lang, settings.webapp_url))
    await msg.answer(t(lang, "presets"), reply_markup=kb.topics_kb(lang))


@router.message(Command("lang"))
async def cmd_lang(msg: Message):
    lang = await lang_of(msg.from_user.id)
    await msg.answer(t(lang, "choose_lang"), reply_markup=kb.lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(cq: CallbackQuery):
    code = cq.data.split(":", 1)[1]
    if code not in LANGS:
        return await cq.answer()
    await db.set_lang(cq.from_user.id, code)
    await cq.answer(t(code, "lang_saved"))
    await cq.message.answer(t(code, "start"), reply_markup=kb.main_menu(code, settings.webapp_url))


@router.message(Command("help"))
async def cmd_help(msg: Message):
    lang = await lang_of(msg.from_user.id)
    await msg.answer(t(lang, "help"))


@router.message(Command("search"))
async def cmd_search(msg: Message):
    lang = await lang_of(msg.from_user.id)
    query = msg.text.partition(" ")[2].strip()
    if query:
        return await do_search(msg, lang, query)
    await msg.answer(t(lang, "search_prompt"), reply_markup=kb.topics_kb(lang))


# ------------------------------------------------------------------- поиск
async def do_search(msg: Message, lang: str, query: str):
    wait = await msg.answer(t(lang, "searching"))
    try:
        books = await sources.search_all(query, lang)
    except Exception as e:
        log.exception("search failed: %s", e)
        books = []
    if not books:
        return await wait.edit_text(t(lang, "no_results"))

    sid = await db.save_search(msg.from_user.id, query, books)
    text, _ = render_list(lang, books, 0)
    per = settings.results_per_page
    total_pages = max(1, (len(books) + per - 1) // per)
    markup = kb.results_kb(lang, sid, 0, total_pages, 0, min(per, len(books)))
    await wait.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("t:"))
async def cb_topic(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    topic = cq.data.split(":", 1)[1]
    query = TOPIC_QUERIES.get(topic, {}).get(lang, topic)
    await cq.answer()
    await do_search(cq.message, lang, query)


@router.callback_query(F.data.startswith("p:"))
async def cb_page(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    _, sid, page = cq.data.split(":")
    data = await db.get_search(int(sid))
    if not data:
        return await cq.answer("⌛", show_alert=False)
    _, books = data
    page = int(page)
    per = settings.results_per_page
    total_pages = max(1, (len(books) + per - 1) // per)
    page = max(0, min(page, total_pages - 1))
    start = page * per
    text, _ = render_list(lang, books, page)
    markup = kb.results_kb(lang, int(sid), page, total_pages, start, len(books[start:start + per]))
    await cq.answer()
    try:
        await cq.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass


@router.callback_query(F.data.startswith("b:"))
async def cb_book(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    _, sid, idx = cq.data.split(":")
    data = await db.get_search(int(sid))
    if not data:
        return await cq.answer("⌛")
    _, books = data
    idx = int(idx)
    if idx >= len(books):
        return await cq.answer()
    book = books[idx]
    is_fav = await db.fav_has(cq.from_user.id, book_key(book))
    page = idx // settings.results_per_page
    await cq.answer()
    await cq.message.edit_text(render_card(lang, book),
                               reply_markup=kb.book_kb(lang, int(sid), idx, book, is_fav, page))


# --------------------------------------------------------------- избранное
@router.callback_query(F.data.startswith("f:"))
async def cb_fav_toggle(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    _, sid, idx = cq.data.split(":")
    data = await db.get_search(int(sid))
    if not data:
        return await cq.answer("⌛")
    _, books = data
    book = books[int(idx)]
    key = book_key(book)
    if await db.fav_has(cq.from_user.id, key):
        await db.fav_remove(cq.from_user.id, key)
        await cq.answer(t(lang, "fav_removed"))
        is_fav = False
    else:
        await db.fav_add(cq.from_user.id, key, book)
        await cq.answer(t(lang, "fav_added"))
        is_fav = True
    page = int(idx) // settings.results_per_page
    try:
        await cq.message.edit_reply_markup(
            reply_markup=kb.book_kb(lang, int(sid), int(idx), book, is_fav, page))
    except Exception:
        pass


@router.message(Command("favorites"))
async def cmd_favorites(msg: Message):
    lang = await lang_of(msg.from_user.id)
    await show_favorites(msg, lang)


async def show_favorites(msg: Message, lang: str):
    books = await db.fav_list(msg.chat.id)
    if not books:
        return await msg.answer(t(lang, "fav_empty"))
    items = [{"key": book_key(b), "title": b["title"]} for b in books]
    await msg.answer(t(lang, "fav_title"), reply_markup=kb.favorites_kb(lang, items))


@router.callback_query(F.data.startswith("fo:"))
async def cb_fav_open(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    key = cq.data.split(":", 1)[1]
    books = await db.fav_list(cq.from_user.id)
    book = next((b for b in books if book_key(b) == key), None)
    if not book:
        return await cq.answer()
    sid = await db.save_search(cq.from_user.id, "fav", [book])
    await cq.answer()
    await cq.message.answer(render_card(lang, book),
                            reply_markup=kb.book_kb(lang, sid, 0, book, True, 0))


@router.callback_query(F.data.startswith("fd:"))
async def cb_fav_delete(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    key = cq.data.split(":", 1)[1]
    await db.fav_remove(cq.from_user.id, key)
    await cq.answer(t(lang, "fav_removed"))
    books = await db.fav_list(cq.from_user.id)
    if not books:
        return await cq.message.edit_text(t(lang, "fav_empty"))
    items = [{"key": book_key(b), "title": b["title"]} for b in books]
    await cq.message.edit_reply_markup(reply_markup=kb.favorites_kb(lang, items))


# -------------------------------------------------------------- мои книги
@router.message(Command("library"))
async def cmd_library(msg: Message):
    lang = await lang_of(msg.from_user.id)
    await show_library(msg, lang)


async def show_library(msg: Message, lang: str):
    items = await db.lib_list(msg.chat.id)
    if not items:
        return await msg.answer(t(lang, "lib_empty"))
    await msg.answer(t(lang, "lib_title"), reply_markup=kb.library_kb(items))


@router.callback_query(F.data.startswith("lb:"))
async def cb_lib_resend(cq: CallbackQuery):
    key = cq.data.split(":", 1)[1]
    item = await db.lib_get(cq.from_user.id, key)
    if not item:
        return await cq.answer()
    await cq.answer()
    await cq.message.answer_document(item["file_id"], caption=f"📚 {esc(item['title'])}")


# ------------------------------------------------------------- скачивание
def safe_filename(title: str, fmt: str) -> str:
    name = re.sub(r"[^\w\s\-\.\u0400-\u04FF\u0600-\u06FF]", "", title, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)[:60] or "book"
    return f"{name}.{fmt}"


async def download_to_temp(url: str, max_bytes: int) -> tuple[str | None, int]:
    """Скачать файл во временный каталог. Возвращает (путь|None, размер)."""
    headers = {"User-Agent": "KitobBot/1.0"}
    timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as r:
            r.raise_for_status()
            declared = int(r.headers.get("Content-Length") or 0)
            if declared and declared > max_bytes:
                return None, declared
            fd, path = tempfile.mkstemp(prefix="kitob_")
            size = 0
            with os.fdopen(fd, "wb") as fh:
                async for chunk in r.content.iter_chunked(1 << 16):
                    size += len(chunk)
                    if size > max_bytes:
                        fh.close()
                        os.unlink(path)
                        return None, size
                    fh.write(chunk)
            return path, size


@router.callback_query(F.data.startswith("d:"))
async def cb_download(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    _, sid, idx, fi = cq.data.split(":")
    data = await db.get_search(int(sid))
    if not data:
        return await cq.answer("⌛")
    _, books = data
    book = books[int(idx)]
    file = book["files"][int(fi)]
    url, fmt = file["url"], file["fmt"]
    caption = f"📚 <b>{esc(book['title'])}</b>" + (f"\n<i>{esc(book.get('author',''))}</i>" if book.get("author") else "")

    await cq.answer()

    # 1) файл уже загружался кем-то — отправляем мгновенно по file_id
    cached = await db.file_cached(url)
    if cached:
        sent = await cq.message.answer_document(cached, caption=caption)
        await db.lib_add(cq.from_user.id, book_key(book, fmt), book["title"], fmt, cached)
        return

    wait = await cq.message.answer(t(lang, "downloading"))
    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        path, size = await download_to_temp(url, max_bytes)
    except Exception as e:
        log.warning("download error %s: %s", url, e)
        return await wait.edit_text(
            t(lang, "dl_error"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "open_link"), url=url)]]),
        )

    if not path:
        return await wait.edit_text(
            t(lang, "too_big", size=sources.human_size(size)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "open_link"), url=url)]]),
        )

    try:
        doc = FSInputFile(path, filename=safe_filename(book["title"], fmt))
        sent = await cq.message.answer_document(doc, caption=caption)
        file_id = sent.document.file_id
        await db.file_cache_put(url, file_id, size)
        await db.lib_add(cq.from_user.id, book_key(book, fmt), book["title"], fmt, file_id)
        await wait.edit_text(t(lang, "sent"))
    except Exception as e:
        log.warning("send error: %s", e)
        await wait.edit_text(
            t(lang, "dl_error"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "open_link"), url=url)]]),
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# --------------------------------------------------- текст: меню или запрос
@router.message(F.text)
async def on_text(msg: Message):
    lang = await lang_of(msg.from_user.id)
    action = MENU.get(msg.text.strip())

    if action == "search":
        return await msg.answer(t(lang, "search_prompt"), reply_markup=kb.topics_kb(lang))
    if action == "fav":
        return await show_favorites(msg, lang)
    if action == "lib":
        return await show_library(msg, lang)
    if action == "lang":
        return await msg.answer(t(lang, "choose_lang"), reply_markup=kb.lang_kb())
    if action == "help":
        return await msg.answer(t(lang, "help"))
    if action == "app":
        return await msg.answer(t(lang, "start"), reply_markup=kb.main_menu(lang, settings.webapp_url))

    if len(msg.text.strip()) < 2:
        return await msg.answer(t(lang, "search_prompt"))
    await do_search(msg, lang, msg.text.strip())


# ------------------------------------------------------------------- запуск
async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Start / Boshlash / بدء"),
        BotCommand(command="search", description="Search / Qidiruv / بحث"),
        BotCommand(command="favorites", description="Favorites / Saralangan / المفضلة"),
        BotCommand(command="library", description="My books / Kitoblarim / كتبي"),
        BotCommand(command="lang", description="Language / Til / اللغة"),
        BotCommand(command="help", description="Help / Yordam / مساعدة"),
    ])


async def main() -> None:
    await db.init(settings.db_path)
    bot = Bot(settings.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await set_commands(bot)
    log.info("Kitob bot started. WebApp: %s", settings.webapp_url or "—")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
