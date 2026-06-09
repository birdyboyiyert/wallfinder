"""
YouTube search via yt-dlp's Python API.

We never download anything - yt-dlp is used purely as a metadata source. We bias the query
toward wallpaper loops, run a flat-ish search for speed, and normalize the fields the ranker
needs: id, title, channel, thumbnail, duration, view_count, width, height, url.
"""

from __future__ import annotations

from typing import Any

from yt_dlp import YoutubeDL

# Flat extraction keeps the search to a single cheap round-trip. It returns title/duration/
# view_count/channel for each hit; width/height/thumbnail may be sparse, which the ranker
# tolerates (it falls back to title keywords for resolution and constructs a thumbnail URL).
_YDL_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "noplaylist": True,
    "default_search": "ytsearch",
    "socket_timeout": 20,
}

YOUTUBE_WATCH = "https://www.youtube.com/watch?v="


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """Pull just the fields we care about into a stable shape."""
    vid = entry.get("id") or ""

    thumbnail = entry.get("thumbnail")
    if not thumbnail and entry.get("thumbnails"):
        thumbnail = entry["thumbnails"][-1].get("url")

    url = entry.get("url") or entry.get("webpage_url") or ""
    if not url or ("watch?v=" not in url and "youtu.be" not in url):
        url = YOUTUBE_WATCH + vid if vid else url

    dur = entry.get("duration")

    return {
        "id": vid,
        "title": entry.get("title"),
        "channel": entry.get("channel") or entry.get("uploader"),
        "thumbnail": thumbnail,
        "thumbnails": entry.get("thumbnails"),
        "duration": int(dur) if dur else None,
        "view_count": entry.get("view_count"),
        "width": entry.get("width"),
        "height": entry.get("height"),
        "url": url,
    }


def search_youtube(query: str, n: int = 25) -> list[dict[str, Any]]:
    """
    Search YouTube for `query` (we append wallpaper phrasing) and return up to `n` normalized
    entries. Raises whatever yt-dlp raises on network failure - the caller maps it to 502.
    """
    term = f'ytsearch{int(n)}:{query} live wallpaper loop'

    with YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(term, download=False)

    entries = (info or {}).get("entries") or []
    return [_normalize(e) for e in entries if e]
