"""
Wallpaper Finder — FastAPI app (Part 2: search + ranking/filter + endpoints).

Endpoints:
  GET /             -> JSON welcome + link to /docs (frontend lands in Part 3)
  GET /api/search   -> ranked + filtered wallpaper loops for a query (?strict= optional)
  GET /api/health   -> {"status": "ok"}
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import ranking, search

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Wallpaper Finder",
    version="0.3.0",
    description="Searches YouTube and curates good live-wallpaper loops for Lively Wallpaper.",
)


# --- Response models -----------------------------------------------------------------

class SearchResult(BaseModel):
    title: str
    channel: str
    thumbnail: str | None = None
    duration: int | None = Field(None, description="Length in seconds")
    resolution: str | None = Field(None, description="e.g. 2160p, 1080p")
    url: str
    score: int


class Health(BaseModel):
    status: str


# --- Endpoints -----------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")


@app.get("/api/search", response_model=list[SearchResult])
def api_search(
    q: str = Query(..., min_length=1, description="Search query"),
    strict: bool = Query(False, description="Also require at least one wallpaper keyword"),
    n: int = Query(25, ge=1, le=50, description="Candidates to pull from YouTube before ranking"),
) -> list[SearchResult]:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        raw = search.search_youtube(query, n=n)
    except Exception as exc:  # noqa: BLE001 - surface a clean 502 to the client
        raise HTTPException(status_code=502, detail=f"YouTube search failed: {exc}") from exc

    ranked = ranking.rank_and_filter(raw, strict=strict)
    return [SearchResult(**r) for r in ranked]


# Static assets (index.html, style.css, app.js). Mounted last so it can't shadow routes.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
