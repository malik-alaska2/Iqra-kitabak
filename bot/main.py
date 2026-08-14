"""Kitob — Telegram-бот для поиска и чтения книг (uz / ru / ar).

Запуск:  python bot/main.py
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import tempfile

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo)

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


BOT_USERNAME = ""


# ----------------------------------------------------------------- утилиты
def webapp_url_for(username: str | None) -> str:
    """Адрес мини-приложения с именем бота в хэше.

    Хэш не уходит на сервер, но доступен странице: по нему приложение строит
    ссылку t.me/бот?start=..., когда книгу нужно прислать в чат, а отправить
    данные напрямую нельзя (так бывает при запуске из кнопки меню).
    """
    url = settings.webapp_url
    if not url or not username:
        return url
    return f"{url}#bot={username}"


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
async def cmd_start(msg: Message, command: CommandObject | None = None):
    lang = await db.get_lang(msg.from_user.id)
    if not lang:
        guess = (msg.from_user.language_code or "ru")[:2]
        lang = guess if guess in LANGS else "ru"
        await db.set_lang(msg.from_user.id, lang)
        await msg.answer(t(lang, "choose_lang"), reply_markup=kb.lang_kb())

    # Ссылка вида t.me/бот?start=... — мини-приложение просит прислать книгу.
    ref = (command.args or "").strip() if command else ""
    if ref:
        return await deliver_by_ref(msg, msg.from_user.id, lang, ref)

    await msg.answer(t(lang, "start"), reply_markup=kb.main_menu(lang, webapp_url_for(BOT_USERNAME)))
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


async def download_to_temp(url: str, max_bytes: int, via: str = "") -> tuple[str | None, int]:
    """Скачать файл во временный каталог. Возвращает (путь|None, размер)."""
    headers = {"User-Agent": "KitobBot/1.0"}
    timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        if via == "wikisource":
            # Викитека отдаёт текст внутри JSON, а не файлом.
            async with session.get(url) as r:
                r.raise_for_status()
                data = await r.json(content_type=None)
            page = next(iter((data.get("query") or {}).get("pages", {}).values()), {})
            text = (page.get("extract") or "").strip()
            if not text:
                return None, 0
            body = text.encode("utf-8")
            if len(body) > max_bytes:
                return None, len(body)
            fd, path = tempfile.mkstemp(prefix="kitob_")
            with os.fdopen(fd, "wb") as fh:
                fh.write(body)
            return path, len(body)

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


async def deliver_book(target: Message, user_id: int, lang: str, book: dict, file: dict) -> None:
    """Скачать файл и отправить его в чат.

    Общий путь для трёх входов: кнопки в самом боте, кнопки «отправить в чат»
    в мини-приложении и ссылки-приглашения вида t.me/бот?start=...
    """
    url, fmt = file["url"], file["fmt"]
    if not sources.is_allowed_file_url(url):
        # Адрес приходит от клиента, поэтому доверять ему нельзя.
        log.warning("отклонён адрес не из списка источников: %s", url)
        return await target.answer(t(lang, "dl_error"))

    caption = f"📚 <b>{esc(book['title'])}</b>" + (f"\n<i>{esc(book.get('author',''))}</i>" if book.get("author") else "")

    # 1) файл уже загружался кем-то — отправляем мгновенно по file_id
    cached = await db.file_cached(url)
    if cached:
        await target.answer_document(cached, caption=caption)
        await db.lib_add(user_id, book_key(book, fmt), book["title"], fmt, cached)
        return

    wait = await target.answer(t(lang, "downloading"))
    link_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "open_link"), url=url)]])
    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        path, size = await download_to_temp(url, max_bytes, file.get("via", ""))
    except Exception as e:
        log.warning("download error %s: %s", url, e)
        return await wait.edit_text(t(lang, "dl_error"), reply_markup=link_kb)

    if not path:
        return await wait.edit_text(
            t(lang, "too_big", size=sources.human_size(size)), reply_markup=link_kb)

    try:
        doc = FSInputFile(path, filename=safe_filename(book["title"], fmt))
        sent = await target.answer_document(doc, caption=caption)
        file_id = sent.document.file_id
        await db.file_cache_put(url, file_id, size)
        await db.lib_add(user_id, book_key(book, fmt), book["title"], fmt, file_id)
        await wait.edit_text(t(lang, "sent"))
    except Exception as e:
        log.warning("send error: %s", e)
        await wait.edit_text(t(lang, "dl_error"), reply_markup=link_kb)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@router.callback_query(F.data.startswith("d:"))
async def cb_download(cq: CallbackQuery):
    lang = await lang_of(cq.from_user.id)
    _, sid, idx, fi = cq.data.split(":")
    data = await db.get_search(int(sid))
    if not data:
        return await cq.answer("⌛")
    _, books = data
    book = books[int(idx)]
    await cq.answer()
    await deliver_book(cq.message, cq.from_user.id, lang, book, book["files"][int(fi)])


# ------------------------------------------- книга, заказанная из мини-приложения
async def deliver_by_ref(target: Message, user_id: int, lang: str, ref: str) -> None:
    parsed = sources.decode_book_ref(ref)
    if not parsed:
        return await target.answer(t(lang, "book_gone"))
    src, ident, index = parsed
    book = await sources.fetch_book(src, ident)
    if not book or index >= len(book.get("files") or []):
        return await target.answer(t(lang, "book_gone"))
    await deliver_book(target, user_id, lang, book, book["files"][index])


@router.message(F.web_app_data)
async def on_web_app_data(msg: Message):
    """Мини-приложение, открытое кнопкой меню, просит прислать книгу в чат."""
    lang = await lang_of(msg.from_user.id)
    try:
        payload = json.loads(msg.web_app_data.data)
    except Exception:
        return await msg.answer(t(lang, "book_gone"))
    if payload.get("action") != "send" or not isinstance(payload.get("ref"), str):
        return await msg.answer(t(lang, "book_gone"))
    await deliver_by_ref(msg, msg.from_user.id, lang, payload["ref"])


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
        return await msg.answer(t(lang, "start"), reply_markup=kb.main_menu(lang, webapp_url_for(BOT_USERNAME)))

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


async def setup_menu_button(bot: Bot) -> None:
    """Повесить мини-приложение на кнопку рядом с полем ввода.

    Раньше это делалось руками в @BotFather. Делаем сами по двум причинам:
    настройка не теряется при переносе бота, и в адрес попадает имя бота —
    приложению оно нужно, чтобы построить ссылку «прислать книгу в чат».
    """
    if not settings.webapp_url:
        return
    try:
        me = await bot.get_me()
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Kitob", web_app=WebAppInfo(url=webapp_url_for(me.username))))
        log.info("кнопка меню настроена на %s", webapp_url_for(me.username))
    except Exception as e:
        log.warning("не удалось настроить кнопку меню: %s", e)


async def main() -> None:
    await db.init(settings.db_path)
    bot = Bot(settings.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await set_commands(bot)
    await setup_menu_button(bot)
    me = await bot.get_me()
    globals()["BOT_USERNAME"] = me.username or ""
    log.info("Kitob bot started as @%s. WebApp: %s", me.username, settings.webapp_url or "—")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
