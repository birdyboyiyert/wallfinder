"""
SQLite storage: search cache + community ratings.

- search_cache: repeat searches for the same (normalized) key are instant and don't hammer
  YouTube. We store the full ranked JSON payload with a timestamp so entries can expire.
- ratings: one +1/-1 vote per (video, voter) so the community can push the best loops up.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "wallfinder.db"

# --- Tuning knobs (edit here) --------------------------------------------------------
CACHE_TTL_SECONDS = 24 * 60 * 60   # cached searches are fresh for 24h
RATE_LIMIT_WINDOW = 60             # seconds
RATE_LIMIT_MAX = 20                # max votes (across distinct videos) per window per voter


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id    TEXT NOT NULL,
                vote        INTEGER NOT NULL,
                voter_hash  TEXT NOT NULL,
                created     REAL NOT NULL
            )
            """
        )
        # One person = one (latest) vote per video.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_ratings_video_voter "
            "ON ratings (video_id, voter_hash)"
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


# =====================================================================================
# Community ratings
# =====================================================================================

def add_rating(video_id: str, vote: int, voter_hash: str) -> None:
    """
    Record a vote. The UNIQUE (video_id, voter_hash) index means a repeat vote by the same
    voter REPLACES their previous one (so flipping +1 -> -1 works, and you can't stack votes).
    """
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ratings (video_id, vote, voter_hash, created) "
            "VALUES (?, ?, ?, ?)",
            (video_id, vote, voter_hash, time.time()),
        )
        conn.commit()


def net_votes(video_id: str) -> int:
    """Net score (sum of +1/-1 votes) for a single video."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(vote), 0) AS net FROM ratings WHERE video_id = ?",
            (video_id,),
        ).fetchone()
    return int(row["net"]) if row else 0


def votes_for(video_ids: list[str]) -> dict[str, int]:
    """Batch net-vote lookup for a list of video ids (for blending into search results)."""
    ids = [v for v in video_ids if v]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT video_id, SUM(vote) AS net FROM ratings "
            f"WHERE video_id IN ({placeholders}) GROUP BY video_id",
            ids,
        ).fetchall()
    return {row["video_id"]: int(row["net"]) for row in rows}


def top_rated(limit: int = 20) -> list[dict[str, Any]]:
    """Highest net-rated videos overall, best-first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT video_id, SUM(vote) AS net FROM ratings "
            "GROUP BY video_id HAVING net != 0 ORDER BY net DESC, MAX(created) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"video_id": row["video_id"], "net": int(row["net"])} for row in rows]


def recent_vote_count(voter_hash: str, since_seconds: float) -> int:
    """How many distinct votes this voter has recorded within the window (for rate-limiting)."""
    cutoff = time.time() - since_seconds
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM ratings WHERE voter_hash = ? AND created >= ?",
            (voter_hash, cutoff),
        ).fetchone()
    return int(row["c"]) if row else 0
