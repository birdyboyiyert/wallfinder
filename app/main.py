"""
Wallpaper Finder - FastAPI app.

Endpoints:
  GET  /             -> serves the static frontend (static/index.html)
  GET  /api-docs     -> branded, human-readable API reference
  GET  /api/health   -> {"status": "ok"}
  GET  /api/search   -> ranked + filtered wallpaper loops (envelope response, sqlite-cached)
  GET  /api/top      -> highest community net-rated wallpapers overall
  POST /api/rate     -> cast a +1/-1 community vote on a wallpaper
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, ranking, search

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Wallpaper Finder",
    version="1.0.0",
    description="Searches YouTube and curates good live-wallpaper loops for Lively Wallpaper.",
)

# CORS: this is a public, "usable by anyone" API - allow any web app to call it from the
# browser. (No cookies/credentials are used, so allow_origins="*" is safe here.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Make sure the sqlite tables (search cache + ratings) exist before any request.
    db.init_db()


# --- Response models -----------------------------------------------------------------

class SearchResult(BaseModel):
    title: str
    channel: str
    thumbnail: str | None = None
    duration: int | None = Field(None, description="Length in seconds")
    resolution: str | None = Field(None, description="e.g. 2160p, 1080p")
    url: str
    video_id: str = Field("", description="YouTube video id (used for previews + voting)")
    score: int
    votes: int = Field(0, description="Net community votes (upvotes - downvotes)")
    breakdown: dict = Field(default_factory=dict, description="How the score was computed")


class SearchResponse(BaseModel):
    query: str
    strict: bool
    cached: bool
    count: int
    results: list[SearchResult]


class Health(BaseModel):
    status: str


class RateRequest(BaseModel):
    video_id: str = Field(..., min_length=1, description="YouTube video id to vote on")
    vote: int = Field(..., description="Must be +1 (up) or -1 (down)")


class RateResponse(BaseModel):
    video_id: str
    net_votes: int


class TopItem(BaseModel):
    video_id: str
    net_votes: int
    url: str


# --- Endpoints -----------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api-docs", include_in_schema=False)
def api_docs(request: Request) -> HTMLResponse:
    # Show the REAL base url (works locally and behind Railway's proxy).
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base_url = f"{proto}://{host}"
    html = (STATIC_DIR / "api-docs.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__BASE_URL__", base_url))


@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")


@app.get("/api/search", response_model=SearchResponse)
def api_search(
    q: str = Query(..., min_length=1, description="Search query"),
    strict: bool = Query(False, description="Also require at least one wallpaper keyword"),
    limit: int = Query(25, ge=1, le=50, description="Candidates to pull from YouTube before ranking"),
    refresh: bool = Query(False, description="Bypass the cache and re-search YouTube"),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # Cache key includes the params that change the result set, so a strict/limit variant
    # never serves another variant's cached payload.
    cache_key = f"{db.normalize_query(query)}|strict={strict}|limit={limit}"

    cached_results = None if refresh else db.get_cached(cache_key)
    if cached_results is not None:
        results = cached_results
        cached = True
    else:
        try:
            raw = search.search_youtube(query, n=limit)
        except Exception as exc:  # noqa: BLE001 - surface a clean 502 to the client
            raise HTTPException(status_code=502, detail=f"YouTube search failed: {exc}") from exc
        results = ranking.rank_and_filter(raw, strict=strict)
        # Cache the BASE ranking (no vote blending) so votes always reflect live counts.
        db.set_cached(cache_key, results)
        cached = False

    _blend_votes(results)

    return SearchResponse(
        query=query,
        strict=strict,
        cached=cached,
        count=len(results),
        results=[SearchResult(**r) for r in results],
    )


def _blend_votes(results: list[dict]) -> None:
    """
    Mutate results in place: add the live community vote count + a clamped score bonus, then
    re-sort best-first. Runs on every request (cached or fresh) so ratings stay live.
    """
    vote_map = db.votes_for([r.get("video_id", "") for r in results])
    for r in results:
        net = vote_map.get(r.get("video_id", ""), 0)
        bonus = ranking.vote_bonus(net)
        r["votes"] = net
        r["score"] = r["score"] + bonus
        if isinstance(r.get("breakdown"), dict):
            r["breakdown"]["vote_points"] = bonus
            r["breakdown"]["total"] = r["score"]
    results.sort(key=lambda r: r["score"], reverse=True)


@app.post("/api/rate", response_model=RateResponse)
def api_rate(payload: RateRequest, request: Request) -> RateResponse:
    if payload.vote not in (1, -1):
        raise HTTPException(status_code=400, detail="vote must be +1 or -1.")

    # Identify the voter WITHOUT storing their raw IP: hash ip + user-agent.
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    voter_hash = hashlib.sha256(f"{client_ip}|{user_agent}".encode()).hexdigest()

    # Rate-limit: too many votes in the window -> 429. (Same-video spam is already deduped
    # by the unique index, so this catches rapid voting across many different videos.)
    if db.recent_vote_count(voter_hash, db.RATE_LIMIT_WINDOW) >= db.RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many votes. Slow down.")

    db.add_rating(payload.video_id, payload.vote, voter_hash)
    return RateResponse(video_id=payload.video_id, net_votes=db.net_votes(payload.video_id))


@app.get("/api/top", response_model=list[TopItem])
def api_top(limit: int = Query(20, ge=1, le=100, description="How many to return")) -> list[TopItem]:
    return [
        TopItem(
            video_id=row["video_id"],
            net_votes=row["net"],
            url=ranking.YOUTUBE_WATCH + row["video_id"],
        )
        for row in db.top_rated(limit)
    ]


# Static assets (index.html, style.css, app.js). Mounted last so it can't shadow routes.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
