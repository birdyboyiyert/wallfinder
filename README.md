# Wallpaper Finder

Search YouTube for **live-wallpaper loops**, rank them for wallpaper quality, let the community
vote on them, and copy the best URL straight into
[Lively Wallpaper](https://www.rocksdanister.com/lively/) - which plays YouTube URLs natively as
animated desktop wallpapers.

Lively already plays any YouTube URL. The value here is **curation**: a search tuned for good
wallpaper loops, a ranking engine that pushes seamless 4K loops to the top and buries the
tutorials / reactions / top-10 lists, and a community vote layer that lifts the genuinely great
ones.

## How it works

1. You search (e.g. `lofi rain wallpaper`).
2. `yt-dlp` runs a flat `ytsearch` against YouTube - **no videos are downloaded, only metadata**.
3. `app/ranking.py` scores each result (title keywords, resolution, aspect ratio, duration),
   hard-excludes "content" videos, and drops vertical Shorts.
4. Community votes are blended into the score, results are sorted best-first, and the payload is
   cached in SQLite.
5. You hit **COPY URL** on a card and paste into Lively -> *+ Add Wallpaper -> Enter URL*.

## Stack

Python 3.12 / FastAPI / uvicorn / yt-dlp / sqlite3 (stdlib) / vanilla HTML/CSS/JS.

## Project layout

```
app/
  main.py      FastAPI app, routes, CORS, serves the frontend + /api-docs
  search.py    yt-dlp YouTube search (flat, metadata only)
  ranking.py   wallpaper-quality scoring + filtering + vote blending (the core value)
  db.py        sqlite: search cache + community ratings
static/
  index.html   dark neo-brutalist search UI
  style.css
  app.js       search, result grid, copy button, preview modal, voting
  api-docs.html branded API reference page
requirements.txt
Procfile       Railway/Heroku-style process definition
```

## Run it (Windows / PowerShell)

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
# (If activation is blocked: Set-ExecutionPolicy -Scope Process Bypass -Force, then re-run)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000>. Browse the API at <http://127.0.0.1:8000/api-docs> or the
interactive Swagger UI at <http://127.0.0.1:8000/docs>.

### macOS / Linux

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API

CORS is open (`*`), so any web app can call this from the browser. There is no auth.

### `GET /` - the web UI
Serves the search frontend.

### `GET /api-docs` - branded API reference
Human-readable docs page with copy-paste curl + fetch examples and the live base URL.

### `GET /api/health`
```json
{ "status": "ok" }
```

### `GET /api/search`
Search, rank, filter, and (24h) cache wallpaper loops.

| Param     | Type   | Default | Description                                         |
|-----------|--------|---------|-----------------------------------------------------|
| `q`       | string | -       | **Required.** The search query.                     |
| `strict`  | bool   | `false` | Also require a wallpaper keyword in the title.      |
| `limit`   | int    | `25`    | Candidates to pull from YouTube before ranking (1-50). |
| `refresh` | bool   | `false` | Bypass the cache and re-search YouTube.             |

```powershell
curl "http://127.0.0.1:8000/api/search?q=lofi%20rain%20wallpaper&strict=false&limit=25"
```

Response is an **envelope**:

```jsonc
{
  "query": "lofi rain wallpaper",
  "strict": false,
  "cached": true,            // true when served from the SQLite cache (no YouTube call)
  "count": 9,
  "results": [
    {
      "title": "...",
      "channel": "...",
      "thumbnail": "https://i.ytimg.com/vi/<id>/hqdefault.jpg",
      "duration": 116,        // seconds, or null if unknown
      "resolution": "2160p",  // or null when yt-dlp doesn't report pixels in flat mode
      "url": "https://www.youtube.com/watch?v=<id>",
      "video_id": "<id>",
      "score": 106,           // includes any community vote bonus
      "votes": 0,             // net community votes (upvotes - downvotes)
      "breakdown": {          // exactly how the score was computed
        "base": 10,
        "title_keywords": ["live wallpaper", "4k"],
        "title_points": 88,
        "resolution_points": 0,
        "aspect_points": 0,
        "duration_points": 8,
        "vote_points": 0,
        "total": 106
      }
    }
  ]
}
```

- The cache is keyed by the normalized query **plus** `strict` and `limit`, so variants never
  collide. Repeat the same search and `"cached": true` comes back instantly.
- `refresh=true` bypasses the cache; `limit=50` pulls more candidates.

### `GET /api/top`
Highest community net-rated wallpapers overall, best-first.

| Param   | Type | Default | Description              |
|---------|------|---------|--------------------------|
| `limit` | int  | `20`    | How many to return (1-100). |

```jsonc
[ { "video_id": "hcVT8Th6JVM", "net_votes": 12, "url": "https://www.youtube.com/watch?v=hcVT8Th6JVM" } ]
```

### `POST /api/rate`
Cast a community vote. Body:

```jsonc
{ "video_id": "rneArlA6ouw", "vote": 1 }   // vote must be +1 or -1
```

```powershell
curl -X POST "http://127.0.0.1:8000/api/rate" `
  -H "Content-Type: application/json" `
  -d '{"video_id": "rneArlA6ouw", "vote": 1}'
```

Response:

```json
{ "video_id": "rneArlA6ouw", "net_votes": 1 }
```

- **One vote per video per person.** A voter is identified by a SHA-256 hash of their IP +
  user-agent - the raw IP is never stored. Re-voting updates your existing vote (so you can
  flip +1 -> -1 or change your mind); it never stacks.
- **Anti-abuse:** more than 20 votes/minute from one voter returns `429`. A non-`{1, -1}` vote
  returns `400`; a missing `video_id` returns `422`.
- Net votes feed back into search ranking as a clamped bonus (`+/-30`), so the community can nudge
  good loops up without letting votes fully override the quality score.

## Ranking signals (`app/ranking.py`)

Keyword lists and tuning knobs live at the top of the file.

| Signal        | Effect                                                                      |
|---------------|-----------------------------------------------------------------------------|
| Title keywords| **Boost:** live/moving/animated wallpaper, seamless, loop, screensaver, ambient, no copyright... |
| Title res.    | **Boost:** 4k, 8k, uhd, 2160p, 1440p, 1080p, 60fps                          |
| Hard-exclude  | **Drop entirely:** how to, tutorial, fix, guide, setup, install, review, reaction, top 10/20/50, vs, gameplay, walkthrough, trailer, lyrics, interview, podcast, vlog, unboxing |
| Shape         | **Boost** landscape ~16:9; **drop** vertical videos (Shorts)                |
| Resolution    | **Boost** real pixel height when yt-dlp reports it (1080p/1440p/4K+)         |
| Duration      | Mild: small bonus for ~30s-15min, small penalty for sub-8s clips (long ambient loops are fine) |
| Community     | Net votes add a clamped `+/-30` bonus                                          |

Anything below the minimum score is filtered out. Each result carries a `breakdown` field
showing exactly how its score was reached.

## Notes

- The SQLite file (`wallfinder.db`) is created automatically on startup and is git-ignored.
  It holds both the **search cache** (24h TTL) and the **community ratings** - both are live in
  this version.
- yt-dlp is used **only** for metadata; nothing is ever downloaded.

## Deploy (Railway)

The app binds `0.0.0.0` and reads the `$PORT` env var in production via the `Procfile`:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Live URL: **`<add your Railway URL here once deployed>`** - that public URL is where the API
lives, and `/api-docs` on it shows the real domain in every example.

> **Heads-up:** on Railway's free tier the SQLite file is **ephemeral** - it resets on every
> redeploy, so the search cache and community votes do not persist across deploys. That's fine
> for now; storage becomes permanent once this moves to the Raspberry Pi (the RaspAPI target).

> **Heads-up:** YouTube sometimes rate-limits / blocks `yt-dlp` requests coming from cloud IP
> ranges. If `/api/search` starts returning `502`s in production, that's the cause. The fix is
> to move to the official YouTube Data API (key-based) or run from the Raspberry Pi's
> residential IP - both planned for a later step.

### Railway steps

1. Push this repo to GitHub.
2. In Railway, click **New Project** -> **Deploy from GitHub repo** and select the repo.
3. Railway detects Python from `requirements.txt`, installs dependencies, and runs the `Procfile`.
4. Open the deployed service, go to **Settings** -> **Networking**, and generate/copy the public domain.
5. Test the live search endpoint:

```bash
curl "https://YOUR-RAILWAY-DOMAIN/api/search?q=lofi%20rain%20wallpaper&limit=10"
```

6. Test the required POST endpoint:

```bash
curl -X POST "https://YOUR-RAILWAY-DOMAIN/api/rate" \
  -H "Content-Type: application/json" \
  -d '{"video_id": "rneArlA6ouw", "vote": 1}'
```

7. Open `https://YOUR-RAILWAY-DOMAIN/api-docs` to verify the branded docs page shows the live
   base URL in its examples.
