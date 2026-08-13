"""Клавиатуры бота."""
from __future__ import annotations

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup, WebAppInfo)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from i18n import LANGS, t, topic_title
from sources import human_size


def lang_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, title in LANGS.items():
        kb.button(text=title, callback_data=f"lang:{code}")
    kb.adjust(1)
    return kb.as_markup()


def main_menu(lang: str, webapp_url: str = "") -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(lang, "menu_search")), KeyboardButton(text=t(lang, "menu_fav"))],
        [KeyboardButton(text=t(lang, "menu_lib"))],
        [KeyboardButton(text=t(lang, "menu_lang")), KeyboardButton(text=t(lang, "menu_help"))],
    ]
    if webapp_url:
        rows[1].append(KeyboardButton(text=t(lang, "menu_app"), web_app=WebAppInfo(url=webapp_url)))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def topics_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in ("quran", "hadith", "fiqh", "aqidah", "seerah"):
        kb.button(text=topic_title(lang, key), callback_data=f"t:{key}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def results_kb(lang: str, sid: int, page: int, total_pages: int,
               start: int, count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(count):
        kb.button(text=str(start + i + 1), callback_data=f"b:{sid}:{start + i}")
    kb.adjust(*([3] * ((count + 2) // 3)))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=t(lang, "prev"), callback_data=f"p:{sid}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text=t(lang, "next"), callback_data=f"p:{sid}:{page + 1}"))
    if nav:
        kb.row(*nav)
    return kb.as_markup()


def book_kb(lang: str, sid: int, idx: int, book: dict, is_fav: bool, page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for fi, f in enumerate(book.get("files", [])[:6]):
        size = human_size(f.get("size"))
        mark = "📕" if f["fmt"] == "pdf" else "📗" if f["fmt"] == "epub" else "📄"
        label = f"{mark} {f['label']}" + (f" · {size}" if size != "—" else "")
        kb.button(text=label, callback_data=f"d:{sid}:{idx}:{fi}")
    kb.adjust(2)

    row = [InlineKeyboardButton(
        text=t(lang, "fav_del_btn") if is_fav else t(lang, "fav_add_btn"),
        callback_data=f"f:{sid}:{idx}",
    )]
    if book.get("page"):
        row.append(InlineKeyboardButton(text=t(lang, "open_link"), url=book["page"]))
    kb.row(*row)
    kb.row(InlineKeyboardButton(text=t(lang, "back_to_list"), callback_data=f"p:{sid}:{page}"))
    return kb.as_markup()


def favorites_kb(lang: str, items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for it in items:
        kb.row(
            InlineKeyboardButton(text=f"📖 {it['title'][:38]}", callback_data=f"fo:{it['key']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fd:{it['key']}"),
        )
    return kb.as_markup()


def library_kb(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for it in items:
        kb.button(text=f"{it['fmt'].upper()} · {it['title'][:38]}", callback_data=f"lb:{it['key']}")
    kb.adjust(1)
    return kb.as_markup()
