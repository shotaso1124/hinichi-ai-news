"""SQLite-backed TTL cache for fetcher responses.

Schema
------
``cache``:
    - ``source``      TEXT   — fetcher identifier (e.g. ``"hn"``)
    - ``cache_key``   TEXT   — sub-key inside the source (e.g. date)
    - ``data_json``   TEXT   — JSON-serialized payload
    - ``expires_at``  TEXT   — ISO 8601 UTC timestamp of expiry
    - PRIMARY KEY (``source``, ``cache_key``)

``set()`` performs an UPSERT, ``get()`` returns ``None`` when the row is
missing or has expired (expired rows are also lazily deleted).
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "news_cache.db"


def _db_path() -> Path:
    """Return the active DB path, honoring the ``AI_NEWS_CACHE_DB`` env var.

    Tests override the location by setting ``AI_NEWS_CACHE_DB`` before
    importing this module's helpers.
    """
    override = os.environ.get("AI_NEWS_CACHE_DB")
    if override:
        return Path(override)
    return _DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            source TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            data_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (source, cache_key)
        )
        """
    )
    return conn


def get(source: str, key: str) -> list | None:
    """Return cached payload for ``(source, key)`` or ``None`` if missing/expired."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT data_json, expires_at FROM cache WHERE source = ? AND cache_key = ?",
            (source, key),
        ).fetchone()
        if row is None:
            return None

        data_json, expires_at = row
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            # Corrupt timestamp — treat as expired and purge.
            conn.execute(
                "DELETE FROM cache WHERE source = ? AND cache_key = ?",
                (source, key),
            )
            conn.commit()
            return None

        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        if expiry <= datetime.now(timezone.utc):
            conn.execute(
                "DELETE FROM cache WHERE source = ? AND cache_key = ?",
                (source, key),
            )
            conn.commit()
            return None

        return json.loads(data_json)


def set(source: str, key: str, data: Any, ttl_minutes: int = 30) -> None:
    """UPSERT the payload with a TTL of ``ttl_minutes`` (default 30)."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO cache (source, cache_key, data_json, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, cache_key) DO UPDATE SET
                data_json = excluded.data_json,
                expires_at = excluded.expires_at
            """,
            (source, key, json.dumps(data, ensure_ascii=False), expires_at.isoformat()),
        )
        conn.commit()


def clear(source: str | None = None, key: str | None = None) -> None:
    """Delete cache entries.

    - ``clear()`` removes everything.
    - ``clear(source=...)`` removes a single source.
    - ``clear(source=..., key=...)`` removes a single row.
    """
    with closing(_connect()) as conn:
        if source is None:
            conn.execute("DELETE FROM cache")
        elif key is None:
            conn.execute("DELETE FROM cache WHERE source = ?", (source,))
        else:
            conn.execute(
                "DELETE FROM cache WHERE source = ? AND cache_key = ?",
                (source, key),
            )
        conn.commit()


__all__ = ["get", "set", "clear"]
