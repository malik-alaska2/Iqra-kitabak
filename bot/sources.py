"""Поиск книг в открытых легальных источниках.

Источники:
  1. catalog.json   — собственный каталог (ссылки, которые вы добавили сами)
  2. Internet Archive (archive.org) — миллионы оцифрованных книг, много арабских
  3. Project Gutenberg (gutendex.com) — книги в общественном достоянии

У каждой книги может быть несколько версий/форматов — пользователь выбирает сам.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from urllib.parse import quote, urlparse

import aiohttp

# Каталог общий с мини-приложением. Папка называется docs/ — именно её отдаёт
# GitHub Pages. Раньше здесь стояло webapp/, из-за чего свой каталог у бота
# никогда не загружался.
CATALOG_PATH = Path(__file__).resolve().parent.parent / "docs" / "catalog.json"

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
IA_LANG_HINT = {"ar": "Arabic", "ru": "Russian", "uz": "Uzbek", "en": "English"}
# Поле language в Archive.org заполнено неровно: «Russian», «rus», «ru».
# Для фильтра берём полное название (индекс сам подтягивает варианты),
# а для оценки совпадения сравниваем по всем известным написаниям.
LANG_CODES = {
    "ar": {"ar", "ara", "arabic"},
    "ru": {"ru", "rus", "russian"},
    "uz": {"uz", "uzb", "uzbek"},
    "en": {"en", "eng", "english"},
}


CYRILLIC = re.compile(r"[\u0400-\u04FF]")
# Узбекский пишут и кириллицей тоже: ў, қ, ғ, ҳ — в русском алфавите их нет.
UZBEK_CYRILLIC = re.compile(r"[\u045E\u040E\u049B\u049A\u0493\u0492\u04B3\u04B2]")


def detect_query_lang(query: str) -> str:
    """Язык самого запроса: ищем на том языке, на котором человек пишет."""
    if re.search(r"[\u0600-\u06FF]", query):
        return "ar"
    if CYRILLIC.search(query):
        return "uz" if UZBEK_CYRILLIC.search(query) else "ru"
    if re.search(r"[A-Za-z]", query):
        return "uz"
    return ""


def _lang_hints(query_lang: str) -> list[str]:
    """Язык в запросе к Archive.org ровно один — тот, на котором пишет человек.

    Раньше для узбекского был второй заход (английский или русский), но отбор
    строгий: находка с чужой меткой языка всё равно отбрасывается, то есть
    такой заход только тратил запрос. Книги без метки языка ловятся ступенями
    без фильтра — они в лестнице остались.
    """
    hint = IA_LANG_HINT.get(query_lang)
    return [hint] if hint else []


def _same_lang(item_lang, code: str) -> bool:
    if not item_lang or not code:
        return False
    values = item_lang if isinstance(item_lang, list) else [item_lang]
    names = LANG_CODES.get(code, set())
    return any(str(v).strip().lower() in names for v in values)


def _words(query: str) -> list[str]:
    # Двоеточия и скобки ломают синтаксис запроса Solr — вырезаем их.
    raw = re.split(r"\s+", query)
    cleaned = [re.sub(r"[\"\\:()\[\]{}^~*?]", " ", w).strip() for w in raw]
    return [w for w in cleaned if len(w) > 1]


def _query_ladder(query: str, query_lang: str) -> list[str]:
    """Лестница запросов — от самого точного к самому широкому.

    Раньше запрос из двух слов склеивался через AND по всему тексту и почти
    всегда давал ноль («hadis toplami» — 0 результатов), а фильтр языка вида
    `language:(Uzbek) OR language:(*)` не фильтровал вообще ничего.
    Теперь идём по ступеням и останавливаемся, как только набрали кандидатов.
    """
    ws = _words(query)
    fallback = re.sub(r"[\"\\:()\[\]{}^~*?]", " ", query).strip()
    and_q = " AND ".join(ws) if ws else fallback
    or_q = " OR ".join(ws) if ws else fallback
    hints = _lang_hints(query_lang)

    steps: list[str] = []
    for h in hints:
        steps.append(f"title:({and_q}) AND mediatype:texts AND language:({h})")
    for h in hints:
        steps.append(f"({and_q}) AND mediatype:texts AND language:({h})")
    steps.append(f"title:({and_q}) AND mediatype:texts")
    steps.append(f"({and_q}) AND mediatype:texts")
    if len(ws) > 1:
        for h in hints:
            steps.append(f"({or_q}) AND mediatype:texts AND language:({h})")
        steps.append(f"title:({or_q}) AND mediatype:texts")
    return steps


def _score_doc(doc: dict, ws: list[str], query_lang: str, rank: int) -> float:
    """Название важнее автора, книга на языке запроса — выше.

    rank — место в исходной выдаче (по скачиваниям), уходит в тай-брейк.
    """
    title = str(doc.get("title") or "").lower()
    creator = doc.get("creator")
    if isinstance(creator, list):
        creator = " ".join(creator)
    creator = str(creator or "").lower()

    score = 0.0
    hits = 0
    for w in ws:
        n = w.lower()
        if n in title:
            score += 4
            hits += 1
        elif n in creator:
            score += 2
            hits += 1
    if ws and hits == len(ws):
        score += 6
    if _same_lang(doc.get("language"), query_lang):
        score += 5
    return score - rank * 0.01


# --------------------------------------------------- строгий отбор по языку
# Запрос на арабском должен приводить к арабским книгам, на русском — к русским.
# Одного поля language мало: в Archive.org оно и пустое бывает, и неверное —
# метка Uzbek нередко стоит на изданиях на урду. Поэтому смотрим на два
# признака сразу: объявленный язык и письмо самого названия.
SCRIPTS = {
    "arabic": re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF]"),
    "cyrillic": re.compile(r"[\u0400-\u04FF]"),
    "latin": re.compile(r"[A-Za-z]"),
    # деванагари, бенгальский, иврит, тайский, японский, китайский, корейский
    "foreign": re.compile(
        r"[\u0900-\u097F\u0980-\u09FF\u0590-\u05FF\u0E00-\u0E7F"
        r"\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]"),
}
NATIVE_SCRIPT = {"ar": "arabic", "ru": "cyrillic", "uz": "latin"}
EXTRA_SCRIPT = {"uz": "cyrillic"}


def script_of(text: str) -> str:
    counts = {name: len(rx.findall(str(text or ""))) for name, rx in SCRIPTS.items()}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else ""


def _lang_codes(book: dict) -> set[str]:
    raw = book.get("lang") if book.get("lang") is not None else book.get("language")
    values = raw if isinstance(raw, list) else [raw]
    codes: set[str] = set()
    for value in values:
        name = str(value or "").strip().lower()
        if not name:
            continue
        matched = False
        for code, names in LANG_CODES.items():
            if name in names:
                codes.add(code)
                matched = True
        if not matched:
            codes.add(name)
    return codes


def matches_lang(book: dict, lang: str) -> bool:
    """Строгая проверка: книга не на языке запроса не показывается вообще."""
    if not lang:
        return True
    script = script_of(book.get("title"))
    if script == "foreign":          # деванагари, CJK и прочее — точно мимо
        return False

    declared = _lang_codes(book)
    if declared:
        if lang not in declared:
            return False
        # Язык совпал, но письмо противоречит: так выглядят ошибки метаданных
        # вроде арабской книги с меткой Uzbek.
        return lang == "ar" or script != "arabic"
    return script in {NATIVE_SCRIPT.get(lang), EXTRA_SCRIPT.get(lang)}


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


def _ia_creator(meta_info: dict) -> str:
    creator = meta_info.get("creator")
    if isinstance(creator, list):
        return ", ".join(str(c) for c in creator[:2])
    return str(creator or "")


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

    meta_info = meta.get("metadata") or {}
    return {
        "src": "ia",
        "id": ident,
        # Название приходит из поисковой выдачи; при запросе по одному
        # идентификатору её нет — тогда берём из метаданных самого элемента.
        "title": _clean(title) or _clean(meta_info.get("title")) or ident,
        "author": _clean(author or _ia_creator(meta_info), 60),
        "year": str(year or "")[:4],
        "lang": lang,
        "cover": IA_COVER.format(ident=ident),
        "page": f"https://archive.org/details/{ident}",
        "files": picked,
    }


async def _ia_query(session: aiohttp.ClientSession, q: str, rows: int = 20) -> list[dict]:
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
    return (data.get("response") or {}).get("docs", [])


async def search_archive(session: aiohttp.ClientSession, query: str, lang: str, rows: int = 10) -> list[dict]:
    query_lang = detect_query_lang(query) or lang
    ws = _words(query)

    found: dict[str, tuple[dict, float]] = {}
    for q in _query_ladder(query, query_lang):
        docs = await _ia_query(session, q)
        for i, d in enumerate(docs):
            ident = d.get("identifier")
            if not ident or ident in found:
                continue
            found[ident] = (d, _score_doc(d, ws, query_lang, i))
        if len(found) >= 12:
            break

    if not found:
        return []

    best = sorted(found.values(), key=lambda x: -x[1])[: rows + 4]
    sem = asyncio.Semaphore(6)

    async def one(d: dict):
        async with sem:
            creator = d.get("creator")
            if isinstance(creator, list):
                creator = ", ".join(creator[:2])
            return await _ia_metadata(session, d.get("identifier", ""), d.get("title", ""),
                                      creator or "", d.get("year", ""), query_lang)

    results = await asyncio.gather(*[one(d) for d, _ in best], return_exceptions=True)
    return [r for r in results if isinstance(r, dict)][:rows]


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


# ------------------------------------------------------------- Google Books
# «Ищи в гугле» — вот это оно: у Google Books открытый поиск с полем
# langRestrict, то есть язык ограничивает сам Google. Файлы оттуда не забрать,
# поэтому такие находки идут ссылкой на страницу источника — зато находятся
# книги, которых нет в Archive.org. Без ключа у API дневной лимит на адрес:
# на 429 просто молча пропускаем источник.
GOOGLE_BOOKS = "https://www.googleapis.com/books/v1/volumes"


async def search_google_books(session: aiohttp.ClientSession, query: str,
                              lang: str, limit: int = 8) -> list[dict]:
    params = {"q": query, "maxResults": str(limit), "printType": "books"}
    if lang:
        params["langRestrict"] = lang
    try:
        async with session.get(GOOGLE_BOOKS, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            data = await r.json(content_type=None)
    except Exception:
        return []

    out = []
    for v in data.get("items", []):
        info = v.get("volumeInfo") or {}
        access = v.get("accessInfo") or {}
        if access.get("viewability") == "NO_PAGES" and not access.get("publicDomain"):
            continue
        page = info.get("canonicalVolumeLink") or info.get("infoLink") or ""
        if not info.get("title") or not page:
            continue
        out.append({
            "src": "gb",
            "id": str(v.get("id")),
            "title": _clean(info.get("title")),
            "author": _clean(", ".join(info.get("authors") or [])[:60], 60),
            "year": str(info.get("publishedDate") or "")[:4],
            "language": info.get("language") or "",
            "cover": (info.get("imageLinks") or {}).get("thumbnail", "").replace("http://", "https://"),
            "page": page,
            "files": [],          # скачивание доступно только на стороне Google
        })
    return out


# ----------------------------------------------------------------- Викитека
# Разделы Викитеки живут на отдельном домене для каждого языка, поэтому язык
# результата гарантирован самим адресом. Тексты полные — «Сахих аль-Бухари»
# лежит там целиком.
WIKISOURCE_HOSTS = {"ar": "ar", "ru": "ru"}      # узбекского раздела нет


async def search_wikisource(session: aiohttp.ClientSession, query: str,
                            lang: str, limit: int = 5) -> list[dict]:
    host = WIKISOURCE_HOSTS.get(lang)
    if not host:
        return []
    api = f"https://{host}.wikisource.org/w/api.php"
    params = {"action": "query", "list": "search", "srsearch": query,
              "srlimit": str(limit), "srnamespace": "0", "format": "json"}
    try:
        async with session.get(api, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            data = await r.json(content_type=None)
    except Exception:
        return []

    out = []
    for hit in (data.get("query") or {}).get("search", []):
        title = hit.get("title") or ""
        if not title:
            continue
        out.append({
            "src": "ws",
            "id": f"{host}:{title}",
            "title": _clean(title),
            "author": "",
            "year": "",
            "language": lang,
            "cover": "",
            "page": f"https://{host}.wikisource.org/wiki/{quote(title)}",
            "files": [{
                "fmt": "txt", "label": "TXT", "size": 0, "quality": "orig",
                "via": "wikisource",
                "url": f"{api}?action=query&prop=extracts&explaintext=1&exlimit=1"
                       f"&format=json&titles={quote(title)}",
            }],
        })
    return out


# ---------------------------------------------------------------- свой каталог
def load_catalog() -> list[dict]:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return data.get("books", [])
    except Exception:
        return []


def catalog_by_id(book_id: str) -> dict | None:
    for b in load_catalog():
        if b.get("id") == book_id:
            item = dict(b)
            item["src"] = "cat"
            return item
    return None


# Куда боту вообще разрешено ходить за файлом. Ссылку на скачивание присылает
# мини-приложение, а его открывает пользователь — значит содержимое запроса
# полностью в его руках. Без этого списка бот стал бы открытым загрузчиком
# любого адреса в интернете.
ALLOWED_FILE_HOSTS = {
    "archive.org", "www.archive.org", "web.archive.org",
    "gutendex.com", "gutenberg.org", "www.gutenberg.org",
}
# У Викитеки свой домен на каждый язык, поэтому разрешаем по суффиксу.
ALLOWED_HOST_SUFFIXES = (".wikisource.org",)


def is_allowed_file_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = parsed.hostname or ""
    return host in ALLOWED_FILE_HOSTS or host.endswith(ALLOWED_HOST_SUFFIXES)


# Ссылка на книгу, которая помещается в deep link Telegram: /start принимает
# не больше 64 символов и только A-Z a-z 0-9 _ - , поэтому «источник|id|номер
# файла» кодируется в base64url. Идентификаторы Archive.org иногда длиннее —
# тогда ссылку не строим, и мини-приложение показывает другой путь.
BOOK_REF_LIMIT = 64


def encode_book_ref(src: str, ident: str, file_index: int) -> str | None:
    raw = f"{src}|{ident}|{int(file_index)}".encode()
    ref = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return ref if len(ref) <= BOOK_REF_LIMIT else None


def decode_book_ref(ref: str) -> tuple[str, str, int] | None:
    if not ref or len(ref) > BOOK_REF_LIMIT or not re.fullmatch(r"[A-Za-z0-9_-]+", ref):
        return None
    try:
        raw = base64.urlsafe_b64decode(ref + "=" * (-len(ref) % 4)).decode()
        src, ident, index = raw.split("|")
        idx = int(index)
    except Exception:
        return None
    if src not in {"cat", "ia"} or not ident or not 0 <= idx < 12:
        return None
    return src, ident, idx


async def fetch_book(src: str, ident: str) -> dict | None:
    """Собрать карточку книги по источнику и идентификатору.

    Нужна, когда мини-приложение просит бота прислать книгу: в ссылке
    помещается только пара «источник + идентификатор», а список файлов
    и размеры бот добирает сам.
    """
    if src == "cat":
        return catalog_by_id(ident)
    if src == "ia":
        headers = {"User-Agent": "KitobBot/1.0 (Telegram book search)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            return await _ia_metadata(session, ident, "", "", "", "")
    return None


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
    query_lang = detect_query_lang(query) or lang
    headers = {"User-Agent": "KitobBot/1.0 (Telegram book search)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            search_archive(session, query, lang),
            search_wikisource(session, query, query_lang),
            search_google_books(session, query, query_lang),
        ]
        # Gutenberg — библиотека в основном англоязычной классики. Для арабских
        # и русских запросов она почти всегда пуста, поэтому не ждём её зря.
        if query_lang == "uz":
            tasks.append(search_gutendex(session, query))
        done = await asyncio.gather(*tasks, return_exceptions=True)

    parts = [d if isinstance(d, list) else [] for d in done]
    # Свой каталог и то, что можно скачать, — впереди; находки Google Books,
    # которые читаются только на сайте источника, — последними.
    ia, ws, gb = parts[0], parts[1], parts[2]
    pg = parts[3] if len(parts) > 3 else []
    results = search_catalog(query) + ia + ws + pg + gb

    # Строгий отбор по языку и снятие дублей по названию.
    seen, unique = set(), []
    for b in results:
        if not matches_lang(b, query_lang):
            continue
        key = (b.get("title", "").lower()[:60], b.get("src"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    return unique[:limit]
