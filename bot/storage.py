"""SQLite-хранилище: язык пользователя, избранное, скачанные книги, кэш file_id."""
from __future__ import annotations

import json
import time

import aiosqlite

_DB_PATH = ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    lang TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    query TEXT,
    payload TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER,
    key TEXT,
    payload TEXT,
    created_at INTEGER,
    PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS library (
    user_id INTEGER,
    key TEXT,
    title TEXT,
    fmt TEXT,
    file_id TEXT,
    created_at INTEGER,
    PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS files (
    url TEXT PRIMARY KEY,
    file_id TEXT,
    size INTEGER,
    created_at INTEGER
);
"""


async def init(db_path: str) -> None:
    global _DB_PATH
    _DB_PATH = db_path
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


# ------------------------------------------------------------------ пользователь
async def get_lang(user_id: int) -> str | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
    return row[0] if row and row[0] else None


async def set_lang(user_id: int, lang: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT INTO users(user_id, lang, created_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang",
            (user_id, lang, int(time.time())),
        )
        await db.commit()


async def users_count() -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            return (await cur.fetchone())[0]


# ---------------------------------------------------------------------- поиск
async def save_search(user_id: int, query: str, books: list[dict]) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO searches(user_id, query, payload, created_at) VALUES(?,?,?,?)",
            (user_id, query, json.dumps(books, ensure_ascii=False), int(time.time())),
        )
        await db.commit()
        sid = cur.lastrowid
        # чистим старое, чтобы база не росла
        await db.execute("DELETE FROM searches WHERE created_at < ?", (int(time.time()) - 86400 * 3,))
        await db.commit()
    return sid


async def get_search(sid: int) -> tuple[str, list[dict]] | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT query, payload FROM searches WHERE id=?", (sid,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return row[0], json.loads(row[1])


# ------------------------------------------------------------------- избранное
async def fav_add(user_id: int, key: str, book: dict) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO favorites(user_id, key, payload, created_at) VALUES(?,?,?,?)",
            (user_id, key, json.dumps(book, ensure_ascii=False), int(time.time())),
        )
        await db.commit()


async def fav_remove(user_id: int, key: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("DELETE FROM favorites WHERE user_id=? AND key=?", (user_id, key))
        await db.commit()


async def fav_has(user_id: int, key: str) -> bool:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT 1 FROM favorites WHERE user_id=? AND key=?", (user_id, key)) as cur:
            return await cur.fetchone() is not None


async def fav_list(user_id: int) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT payload FROM favorites WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [json.loads(r[0]) for r in rows]


# ------------------------------------------------------------ мои книги / файлы
async def lib_add(user_id: int, key: str, title: str, fmt: str, file_id: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO library(user_id, key, title, fmt, file_id, created_at) VALUES(?,?,?,?,?,?)",
            (user_id, key, title, fmt, file_id, int(time.time())),
        )
        await db.commit()


async def lib_list(user_id: int) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT key, title, fmt, file_id FROM library WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"key": r[0], "title": r[1], "fmt": r[2], "file_id": r[3]} for r in rows]


async def lib_get(user_id: int, key: str) -> dict | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT key, title, fmt, file_id FROM library WHERE user_id=? AND key=?", (user_id, key)
        ) as cur:
            row = await cur.fetchone()
    return {"key": row[0], "title": row[1], "fmt": row[2], "file_id": row[3]} if row else None


async def file_cached(url: str) -> str | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT file_id FROM files WHERE url=?", (url,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def file_cache_put(url: str, file_id: str, size: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO files(url, file_id, size, created_at) VALUES(?,?,?,?)",
            (url, file_id, size, int(time.time())),
        )
        await db.commit()
