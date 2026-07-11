"""Thin SQLite persistence layer.

SQLite is sufficient for a single-user personal deployment (spec Section 0).
Rows store rich objects as JSON text; a few first-class columns support
indexing and filtering. A module-level connection is guarded by a lock so it
is safe to call from FastAPI's threadpool-backed sync endpoints.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Iterable

from .config import get_settings

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    skill_id   TEXT NOT NULL,
    version    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL,
    is_latest  INTEGER NOT NULL DEFAULT 0,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id    TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    status     TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    data       TEXT
);

CREATE TABLE IF NOT EXISTS timeline (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    step       INTEGER,
    action     TEXT,
    status     TEXT,
    message    TEXT,
    data       TEXT
);

-- Append-only audit trail. No UPDATE/DELETE is ever issued against this table.
CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    agent_id   TEXT,
    task_id    TEXT,
    skill_id   TEXT,
    data       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets (
    ref        TEXT PRIMARY KEY,
    ciphertext TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            settings = get_settings()
            _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL;")
            _conn.execute("PRAGMA foreign_keys=ON;")
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    with _lock:
        conn = get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _lock:
        conn = get_conn()
        return list(conn.execute(sql, tuple(params)).fetchall())


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


def loads(text: str | None) -> Any:
    return json.loads(text) if text else None


# --- Simple key/value settings store ---------------------------------------

def kv_get(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM kv WHERE key=?", (key,))
    return loads(row["value"]) if row else default


def kv_set(key: str, value: Any) -> None:
    execute(
        "INSERT INTO kv(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, dumps(value)),
    )


def reset_for_tests() -> None:
    """Drop the cached connection (used by the test fixtures)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
