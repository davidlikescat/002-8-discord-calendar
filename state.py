"""SQLite 상태 저장소.

- meta: 키-값 (last_processed_message_id 등)
- bindings: 결과 임베드 ↔ 캘린더 이벤트 매핑
   * embed_message_id: 봇이 보낸 결과 임베드 메시지 ID
   * source_message_id: 사용자 원본 메시지 ID (수정·답장 추적)
   * event_id: 구글 캘린더 이벤트 ID
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from config import DB_PATH


_LOCK = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        conn = _conn()
        try:
            yield conn
        finally:
            conn.close()


def init() -> None:
    with _db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bindings (
                embed_message_id INTEGER PRIMARY KEY,
                source_message_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                title TEXT,
                start TEXT,
                html_link TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_bindings_source
                ON bindings(source_message_id);
            """
        )


# ---------- meta ----------

def get_meta(key: str) -> str | None:
    with _db() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_last_message_id() -> int | None:
    v = get_meta("last_processed_message_id")
    return int(v) if v else None


def set_last_message_id(msg_id: int) -> None:
    cur = get_last_message_id() or 0
    if msg_id > cur:
        set_meta("last_processed_message_id", str(msg_id))


# ---------- bindings ----------

def add_binding(
    *,
    embed_message_id: int,
    source_message_id: int,
    event_id: str,
    title: str | None,
    start: str | None,
    html_link: str | None,
) -> None:
    with _db() as c:
        c.execute(
            """
            INSERT OR REPLACE INTO bindings
                (embed_message_id, source_message_id, event_id, title, start, html_link)
            VALUES (?,?,?,?,?,?)
            """,
            (embed_message_id, source_message_id, event_id, title, start, html_link),
        )


def get_binding_by_embed(embed_message_id: int) -> dict | None:
    with _db() as c:
        row = c.execute(
            "SELECT * FROM bindings WHERE embed_message_id=?", (embed_message_id,)
        ).fetchone()
        return dict(row) if row else None


def get_bindings_by_source(source_message_id: int) -> list[dict]:
    with _db() as c:
        rows = c.execute(
            "SELECT * FROM bindings WHERE source_message_id=? ORDER BY created_at DESC",
            (source_message_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_binding(embed_message_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM bindings WHERE embed_message_id=?", (embed_message_id,))
