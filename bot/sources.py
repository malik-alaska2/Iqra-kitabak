"""Поиск книг в открытых легальных источниках.

Источники:
  1. catalog.json   — собственный каталог (ссылки, которые вы добавили сами)
  2. Internet Archive (archive.org) — миллионы оцифрованных книг, много арабских
  3. Project Gutenberg (gutendex.com) — книги в общественном достоянии

У каждой книги может быть несколько версий/форматов — пользователь выбирает сам.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import aiohttp

CATALOG_PATH = Path(__file__).resolve().parent.parent / "webapp" / "catalog.json"

IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_META = "https://archive.org/metadata/{ident}"
IA_DOWNLOAD = "https://archive.org/download/{ident}/{name}"
IA_COVER = "https://archive.org/services/img/{ident}"
GUTENDEX = "https://gutendex.com/books"

# Какие форматы отдаём пользователю и как их подписываем
FORMAT_LABELS = {
    "pdf": "PDF",
    "epub": "EPUB",
    "txt": "TXT",
    "djvu": "DjVu",
    "doc": "DOC",
}
IA_LANG_HINT = {"ar": "Arabic", "ru": "Russian", "uz": "Uzbek"}


def human_size(num: int | None) -> str:
    if not num:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}"
        num /= 1024
    return "—"


def _clean(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _ext(name: str) -> str:
    name = name.lower()
    for ext in ("pdf", "epub", "txt", "djvu", "doc"):
        if name.endswith("." + ext) or name.endswith("_" + ext):
            return ext
    return ""


# --------------------------------------------------------------------------- IA
async def _ia_metadata(session: aiohttp.ClientSession, ident: str, title: str,
                       author: str, year: str, lang: str) -> dict | None:
    """Собрать карточку книги с реальными файлами и их размерами."""
    try:
        async with session.get(IA_META.format(ident=ident), timeout=aiohttp.ClientTimeout(total=25)) as r:
            if r.status != 200:
                return None
            meta = await r.json(content_type=None)
    except Exception:
        return None

    files = []
    for f in meta.get("files", []):
        name = f.get("name", "")
        ext = _ext(name)
        if not ext or ext == "doc":
            continue
        if name.startswith("__") or "_meta" in name or name.endswith("_chocr.html.gz"):
            continue
        size = int(f.get("size") or 0)
        if size and size < 4096:          # мусорные заглушки
            continue
        quality = "scan" if "_bw" in name or "_text" in name else "orig"
        files.append({
            "fmt": ext,
            "label": FORMAT_LABELS.get(ext, ext.upper()),
            "url": IA_DOWNLOAD.format(ident=ident, name=name),
            "size": size,
            "quality": quality,
            "name": name,
        })

    if not files:
        return None

    # Лучшее качество вперёд: PDF-оригинал -> EPUB -> сжатый PDF -> TXT
    order = {"pdf": 0, "epub": 1, "djvu": 2, "txt": 3}
    files.sort(key=lambda f: (order.get(f["fmt"], 9), f["quality"] == "scan", -f["size"]))
    # не больше одного файла на формат+качество, максимум 6 вариантов
    seen, picked = set(), []
    for f in files:
        key = (f["fmt"], f["quality"])
        if key in seen:
            continue
        seen.add(key)
        picked.append(f)
        if len(picked) >= 6:
            break

    return {
        "src": "ia",
        "id": ident,
        "title": _clean(title) or ident,
        "author": _clean(author, 60),
        "year": str(year or "")[:4],
        "lang": lang,
        "cover": IA_COVER.format(ident=ident),
        "page": f"https://archive.org/details/{ident}",
        "files": picked,
    }


async def search_archive(session: aiohttp.ClientSession, query: str, lang: str, rows: int = 10) -> list[dict]:
    q = f'({query}) AND mediatype:texts'
    hint = IA_LANG_HINT.get(lang)
    if hint:
        q = f'{q} AND (language:({hint}) OR language:(*))'
    params = [
        ("q", q), ("rows", str(rows)), ("page", "1"), ("output", "json"),
        ("sort[]", "downloads desc"),
    ]
    for fl in ("identifier", "title", "creator", "year", "language", "downloads"):
        params.append(("fl[]", fl))

    try:
        async with session.get(IA_SEARCH, params=params, timeout=aiohttp.ClientTimeout(total=25)) as r:
            data = await r.json(content_type=None)
    except Exception:
        return []

    docs = (data.get("response") or {}).get("docs", [])
    sem = asyncio.Semaphore(6)

    async def one(d):
        async with sem:
            creator = d.get("creator")
            if isinstance(creator, list):
                creator = ", ".join(creator[:2])
            return await _ia_metadata(session, d.get("identifier", ""), d.get("title", ""),
                                      creator or "", d.get("year", ""), lang)

    results = await asyncio.gather(*[one(d) for d in docs], return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


# -------------------------------------------------------------------- Gutenberg
async def search_gutendex(session: aiohttp.ClientSession, query: str, limit: int = 5) -> list[dict]:
    try:
        async with session.get(GUTENDEX, params={"search": query},
                               timeout=aiohttp.ClientTimeout(total=20)) as r:
            data = await r.json(content_type=None)
    except Exception:
        return []

    out = []
    for b in data.get("results", [])[:limit]:
        files = []
        for mime, url in (b.get("formats") or {}).items():
            if url.endswith(".zip"):
                continue
            if "epub" in mime:
                files.append({"fmt": "epub", "label": "EPUB", "url": url, "size": 0, "quality": "orig"})
            elif mime.startswith("text/plain"):
                files.append({"fmt": "txt", "label": "TXT", "url": url, "size": 0, "quality": "orig"})
            elif "pdf" in mime:
                files.append({"fmt": "pdf", "label": "PDF", "url": url, "size": 0, "quality": "orig"})
        if not files:
            continue
        authors = ", ".join(a.get("name", "") for a in b.get("authors", [])[:2])
        out.append({
            "src": "pg",
            "id": str(b.get("id")),
            "title": _clean(b.get("title")),
            "author": _clean(authors, 60),
            "year": "",
            "lang": (b.get("languages") or [""])[0],
            "cover": (b.get("formats") or {}).get("image/jpeg", ""),
            "page": f"https://www.gutenberg.org/ebooks/{b.get('id')}",
            "files": files[:4],
        })
    return out


# ---------------------------------------------------------------- свой каталог
def load_catalog() -> list[dict]:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return data.get("books", [])
    except Exception:
        return []


def search_catalog(query: str, limit: int = 6) -> list[dict]:
    words = [w for w in re.split(r"\s+", query.lower()) if len(w) > 1]
    out = []
    for b in load_catalog():
        haystack = " ".join([
            str(b.get("title", "")), str(b.get("author", "")),
            " ".join(b.get("tags", []) or []),
        ]).lower()
        score = sum(1 for w in words if w in haystack)
        if score:
            item = dict(b)
            item["src"] = "cat"
            out.append((score, item))
    out.sort(key=lambda x: -x[0])
    return [i for _, i in out[:limit]]


# ------------------------------------------------------------------- агрегатор
async def search_all(query: str, lang: str, limit: int = 18) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    headers = {"User-Agent": "KitobBot/1.0 (Telegram book search)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        ia, pg = await asyncio.gather(
            search_archive(session, query, lang),
            search_gutendex(session, query),
            return_exceptions=True,
        )
    ia = ia if isinstance(ia, list) else []
    pg = pg if isinstance(pg, list) else []
    results = search_catalog(query) + ia + pg

    # убираем дубли по названию
    seen, unique = set(), []
    for b in results:
        key = (b.get("title", "").lower()[:60], b.get("src"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    return unique[:limit]
