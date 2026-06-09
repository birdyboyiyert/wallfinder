# Wallpaper Finder

Search YouTube for **live-wallpaper loops**, rank them for wallpaper quality, and copy the
best URL straight into [Lively Wallpaper](https://www.rocksdanister.com/lively/) — which plays
YouTube URLs natively as animated desktop wallpapers.

Lively already plays any YouTube URL. The value here is **curation**: a search tuned for good
wallpaper loops, plus a ranking engine that pushes the seamless 4K loops to the top and buries
the tutorials, reactions, and top-10 lists.

## How it works

1. You search (e.g. `lofi rain wallpaper`).
2. `yt-dlp` runs a `ytsearch` against YouTube — no videos are downloaded, only metadata.
3. `app/ranking.py` scores every result on title signals, duration, resolution, and views.
4. Results are sorted best-first, cached in SQLite, and returned as JSON.
5. You hit **Copy URL for Lively** and paste into Lively → *+ Add Wallpaper → Enter URL*.

## Stack

Python 3.12 · FastAPI · uvicorn · yt-dlp · sqlite3 (stdlib) · vanilla HTML/CSS/JS.

## Project layout

```
app/
  main.py      FastAPI app, routes, serves the frontend
  search.py    yt-dlp YouTube search
  ranking.py   wallpaper-quality scoring (the core value)
  db.py        sqlite cache (keyed by normalized query)
static/
  index.html   dark search UI
  style.css
  app.js       search, result grid, copy button, preview modal
requirements.txt
```

## Run it (Windows / PowerShell)

```powershell
# 1. Create a Python 3.12 virtual environment
py -3.12 -m venv venv

# 2. Activate it
.\venv\Scripts\Activate.ps1
# (If activation is blocked: Set-ExecutionPolicy -Scope Process Bypass -Force, then re-run)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
uvicorn app.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000>.

### macOS / Linux

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Test it

- In the browser, search **`lofi rain wallpaper`** — top results should be seamless / 4K / loop
  videos, not tutorials.
- Or hit the API directly:

  ```powershell
  curl "http://127.0.0.1:8000/api/search?q=lofi%20rain%20wallpaper"
  ```

- Repeat the same search — the response will include `"cached": true` and return instantly.
- Add `&refresh=true` to bypass the cache, or `&limit=40` to pull more candidates.

## Ranking signals (app/ranking.py)

| Signal       | Boosts                                            | Penalizes                                  |
|--------------|---------------------------------------------------|--------------------------------------------|
| Title words  | live wallpaper, seamless, loop, 4k, ambient, …    | how to, tutorial, top 10, reaction, vlog… |
| Duration     | 30s–10min (peak 1–5min)                           | <15s clips, 30min+ marathons              |
| Resolution   | 1080p / 1440p / 4K+                                | sub-720p                                   |
| Views        | gentle ladder up to 1M+                            | near-zero view uploads                     |

Each result carries a `breakdown` field showing exactly how its score was computed.

## Notes

- The SQLite cache file (`wallfinder.db`) is created automatically and git-ignored.
- Cache entries expire after 24h.
- Community ratings and deployment are intentionally **not** in v1.
