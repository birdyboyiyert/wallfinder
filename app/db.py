"""
SQLite result cache.

Repeat searches for the same (normalized) query should be instant and shouldn't hammer
YouTube. We store the full ranked JSON payload keyed by a normalized query string, with a
timestamp so entries can expire.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "wallfinder.db"

# Cached searches are considered fresh for this long (seconds). 24h is plenty for v1.
CACHE_TTL_SECONDS = 24 * 60 * 60


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                query    TEXT PRIMARY KEY,
                results  TEXT NOT NULL,
                created  REAL NOT NULL
            )
            """
        )
        conn.commit()


def normalize_query(q: str) -> str:
    """Lowercase + collapse whitespace so 'Lofi  Rain ' and 'lofi rain' hit the same cache row."""
    return " ".join(q.lower().split())


def get_cached(query: str) -> list[dict[str, Any]] | None:
    """Return cached results for a query if present and not expired, else None."""
    key = normalize_query(query)
    with _connect() as conn:
        row = conn.execute(
            "SELECT results, created FROM search_cache WHERE query = ?", (key,)
        ).fetchone()

    if not row:
        return None
    if time.time() - row["created"] > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(row["results"])
    except json.JSONDecodeError:
        return None


def set_cached(query: str, results: list[dict[str, Any]]) -> None:
    key = normalize_query(query)
    payload = json.dumps(results)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO search_cache (query, results, created) VALUES (?, ?, ?)",
            (key, payload, time.time()),
        )
        conn.commit()
