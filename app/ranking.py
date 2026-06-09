"""
Wallpaper-quality ranking + filtering.

This is the whole point of the app. Lively can already play any YouTube URL as a wallpaper,
so the value is curation: given a pile of YouTube results, keep only the ones that are
actually good *desktop wallpaper loops* and order them best-first.

The pipeline per result is:
  1. HARD-EXCLUDE  - title contains "content" words (tutorial/reaction/top 10/...) -> dropped.
  2. SHAPE FILTER  - vertical videos (Shorts) are dropped; landscape ~16:9 is rewarded.
  3. SCORE         - title keywords + resolution + aspect + mild duration handling.
  4. THRESHOLD     - anything below MIN_SCORE is dropped.
  5. STRICT (opt)  - if strict=True, also require at least one wallpaper keyword.

All keyword lists live here (top of file) so they're trivial to tweak.
"""

from __future__ import annotations

from typing import Any

# =====================================================================================
# KEYWORD LISTS — single source of truth, edit here.
# =====================================================================================

# Positive title signals -> the uploader is framing this as wallpaper material.
# Weights are deliberately chunky so a few strong hits dominate generic noise.
BOOST_KEYWORDS: dict[str, int] = {
    "live wallpaper": 30,
    "moving wallpaper": 26,
    "animated wallpaper": 26,
    "wallpaper engine": 22,
    "desktop background": 20,
    "wallpaper": 16,
    "screensaver": 16,
    "seamless": 16,
    "looping": 12,
    "loop": 10,
    "ambient": 10,
    "no copyright": 8,
    "free to use": 8,
}

# Resolution / quality signals found in the title (used as a fallback when yt-dlp doesn't
# report real pixel dimensions in flat mode).
RESOLUTION_KEYWORDS: dict[str, int] = {
    "8k": 16,
    "4k": 18,
    "uhd": 14,
    "2160p": 16,
    "1440p": 10,
    "1080p": 8,
    "60fps": 8,
    "full hd": 6,
}

# The set used for the strict-mode "must contain a wallpaper keyword" gate.
WALLPAPER_KEYWORDS: frozenset[str] = frozenset(BOOST_KEYWORDS) | frozenset(RESOLUTION_KEYWORDS)

# Hard-exclude: if the title contains any of these, the result is dropped entirely.
EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "how to",
    "tutorial",
    "fix",
    "guide",
    "setup",
    "install",
    "review",
    "reaction",
    "top 10",
    "top 20",
    "top 50",
    " vs ",
    "gameplay",
    "walkthrough",
    "trailer",
    "lyrics",
    "interview",
    "podcast",
    "vlog",
    "unboxing",
)

# Tuning knobs.
BASE_SCORE = 10
MIN_SCORE = 12  # results scoring below this are filtered out

YOUTUBE_WATCH = "https://www.youtube.com/watch?v="


# =====================================================================================
# Scoring helpers
# =====================================================================================

def _is_excluded(title_lc: str) -> bool:
    return any(kw in title_lc for kw in EXCLUDE_KEYWORDS)


def _boost_score(title_lc: str) -> tuple[int, list[str]]:
    total, hits = 0, []
    for kw, pts in BOOST_KEYWORDS.items():
        if kw in title_lc:
            total += pts
            hits.append(kw)
    return total, hits


def _title_resolution_score(title_lc: str) -> int:
    return sum(pts for kw, pts in RESOLUTION_KEYWORDS.items() if kw in title_lc)


def _has_wallpaper_keyword(title_lc: str) -> bool:
    return any(kw in title_lc for kw in WALLPAPER_KEYWORDS)


def _resolution_label(height: int | None, width: int | None) -> str | None:
    if not height and width:
        height = int(width * 9 / 16)
    if not height:
        return None
    if height >= 2160:
        return "2160p"
    if height >= 1440:
        return "1440p"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    return f"{height}p"


def _resolution_meta_score(height: int | None) -> int:
    """Score from real pixel height when yt-dlp provides it."""
    if not height:
        return 0
    if height >= 2160:
        return 24  # 4K+ gets extra
    if height >= 1440:
        return 14
    if height >= 1080:
        return 10
    if height >= 720:
        return 2
    return -8


def _aspect_score(width: int | None, height: int | None) -> int:
    """Reward landscape ~16:9. Vertical is handled separately (dropped)."""
    if not width or not height:
        return 0
    ratio = width / height
    if 1.6 <= ratio <= 1.85:  # ~16:9
        return 10
    if 1.3 <= ratio < 1.6:  # 4:3-ish, still horizontal
        return 4
    return 0


def _duration_score(seconds: int | None) -> int:
    """
    Mild handling only — long ambient loops are legitimate wallpapers, so we don't punish
    length. We only nudge: a small bonus for the comfortable 30s-15min range, and a small
    penalty for blink-and-miss clips under ~8s.
    """
    if not seconds or seconds <= 0:
        return 0
    if seconds < 8:
        return -10
    if 30 <= seconds <= 900:
        return 8
    return 0


def _is_vertical(width: int | None, height: int | None) -> bool:
    return bool(width and height and height > width)


# =====================================================================================
# Public API
# =====================================================================================

def score_result(entry: dict[str, Any]) -> dict[str, Any] | None:
    """
    Score a single yt-dlp entry. Returns a normalized result dict, or None if the entry is
    hard-excluded or vertical (i.e. it should not appear in results at all).
    """
    title = (entry.get("title") or "").strip()
    if not title:
        return None

    title_lc = title.lower()
    if _is_excluded(title_lc):
        return None

    width = entry.get("width")
    height = entry.get("height")
    if _is_vertical(width, height):
        return None  # it's a Short

    boost, _hits = _boost_score(title_lc)
    title_res = _title_resolution_score(title_lc)
    meta_res = _resolution_meta_score(height)
    aspect = _aspect_score(width, height)

    dur = entry.get("duration")
    dur_i = int(dur) if dur else None
    duration_pts = _duration_score(dur_i)

    score = BASE_SCORE + boost + title_res + meta_res + aspect + duration_pts

    video_id = entry.get("id") or ""
    url = entry.get("url") or entry.get("webpage_url") or (YOUTUBE_WATCH + video_id)
    if video_id and "watch?v=" not in url and "youtu.be" not in url:
        url = YOUTUBE_WATCH + video_id

    thumbnail = entry.get("thumbnail")
    if not thumbnail and entry.get("thumbnails"):
        thumbnail = entry["thumbnails"][-1].get("url")
    if not thumbnail and video_id:
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    return {
        "title": title,
        "channel": entry.get("channel") or entry.get("uploader") or "Unknown",
        "thumbnail": thumbnail,
        "duration": dur_i,
        "resolution": _resolution_label(height, width),
        "url": url,
        "score": score,
        # internal, not part of the response model:
        "_id": video_id,
        "_title_lc": title_lc,
    }


def rank_and_filter(
    entries: list[dict[str, Any]],
    strict: bool = False,
) -> list[dict[str, Any]]:
    """
    Score, filter (hard-exclude, vertical, threshold, optional strict), de-dupe, and sort
    descending by score. Returns clean result dicts ready for the response model.
    """
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    for entry in entries:
        if not entry:
            continue
        scored = score_result(entry)
        if scored is None:
            continue
        if scored["score"] < MIN_SCORE:
            continue
        if strict and not _has_wallpaper_keyword(scored["_title_lc"]):
            continue

        vid = scored["_id"]
        if vid and vid in seen:
            continue
        if vid:
            seen.add(vid)

        # strip internal fields
        scored.pop("_id", None)
        scored.pop("_title_lc", None)
        results.append(scored)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
