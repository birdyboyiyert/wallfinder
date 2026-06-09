# Wallpaper Finder

Wallpaper Finder is a FastAPI project that searches YouTube for live wallpaper loops, ranks the
results for desktop-wallpaper quality, and lets people vote on the best finds.

It is built for Lively Wallpaper, which can use a YouTube URL as an animated desktop wallpaper.
The app does not download videos. It only asks `yt-dlp` for YouTube search metadata, scores the
results, and returns useful links.

## API Requirement Checklist

This project has **4 GET endpoints** and **1 POST endpoint**.

| Method | Endpoint | What it does |
|--------|----------|--------------|
| GET | `/` | Serves the web app |
| GET | `/api/health` | Health check for uptime/testing |
| GET | `/api/search` | Searches YouTube, ranks wallpaper loops, returns cached JSON |
| GET | `/api/top` | Returns top community-rated videos |
| POST | `/api/rate` | Adds or updates a community vote for a video |

There is also a human-readable docs page at `/api-docs`, plus FastAPI's automatic interactive
docs at `/docs`.

## How The API Works

1. A user calls `/api/search?q=lofi rain wallpaper`.
2. The server normalizes the query and checks SQLite for a cached result.
3. If the cache is fresh, the API returns instantly with `"cached": true`.
4. If there is no fresh cache, `yt-dlp` runs a flat YouTube search for metadata only.
5. `app/ranking.py` scores every result using title keywords, resolution clues, aspect ratio,
   duration, and community votes.
6. Bad matches like tutorials, reactions, gameplay, top-10 lists, and vertical Shorts are filtered
   out.
7. The response is returned as a JSON envelope with the query, cache state, count, and results.
8. Users can vote with `/api/rate`; those votes affect future search ranking and `/api/top`.

## Stack

- Python 3.12
- FastAPI
- uvicorn
- yt-dlp
- SQLite through Python's standard `sqlite3`
- Vanilla HTML/CSS/JS frontend

## Project Layout

```text
app/
  main.py      FastAPI app, routes, CORS, response models
  search.py    YouTube metadata search through yt-dlp
  ranking.py   wallpaper scoring, filtering, and vote bonus logic
  db.py        SQLite cache and ratings helpers
static/
  index.html   web app
  style.css    neo-brutalist styling
  app.js       frontend search, preview, copy, and voting
  api-docs.html branded API docs page
requirements.txt
Procfile       production start command
```

## Run Locally

First, clone the repo:

```powershell
git clone https://github.com/birdyboyiyert/wallfinder.git
cd wallfinder
```

Create a virtual environment and install dependencies:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the app:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Then open:

```text
http://127.0.0.1:8010
```

API docs:

```text
http://127.0.0.1:8010/api-docs
http://127.0.0.1:8010/docs
```

If port `8010` is blocked on Windows, use another port:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

## Where Things Install

The Python packages install into the local virtual environment:

```text
wallfinder/venv/
```

The app creates a local SQLite database automatically:

```text
wallfinder/wallfinder.db
```

That database stores cached searches and community votes. It is ignored by git.

## Endpoints

### GET `/`

Serves the browser UI.

```bash
curl "http://127.0.0.1:8010/"
```

### GET `/api/health`

Simple health check.

```bash
curl "http://127.0.0.1:8010/api/health"
```

Response:

```json
{ "status": "ok" }
```

### GET `/api/search`

Searches YouTube, filters bad matches, ranks wallpaper loops, blends community votes, and caches
the result for 24 hours.

Query parameters:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | required | Search query |
| `strict` | bool | `false` | Require wallpaper-related title keywords |
| `limit` | int | `25` | Number of YouTube candidates to inspect, from 1 to 50 |
| `refresh` | bool | `false` | Bypass cache and force a new YouTube search |

Example:

```bash
curl "http://127.0.0.1:8010/api/search?q=lofi%20rain%20wallpaper&limit=10"
```

Response shape:

```json
{
  "query": "lofi rain wallpaper",
  "strict": false,
  "cached": false,
  "count": 2,
  "results": [
    {
      "title": "Example Live Wallpaper 4K Loop",
      "channel": "Example Channel",
      "thumbnail": "https://i.ytimg.com/vi/VIDEO_ID/hqdefault.jpg",
      "duration": 120,
      "resolution": "2160p",
      "url": "https://www.youtube.com/watch?v=VIDEO_ID",
      "video_id": "VIDEO_ID",
      "score": 106,
      "votes": 0,
      "breakdown": {
        "base": 10,
        "title_keywords": ["live wallpaper", "4k", "loop"],
        "title_points": 64,
        "resolution_points": 24,
        "aspect_points": 10,
        "duration_points": 8,
        "vote_points": 0,
        "total": 106
      }
    }
  ]
}
```

Run the same search twice. The second response should include:

```json
"cached": true
```

### GET `/api/top`

Returns the highest net-rated videos.

```bash
curl "http://127.0.0.1:8010/api/top?limit=20"
```

Response:

```json
[
  {
    "video_id": "VIDEO_ID",
    "net_votes": 5,
    "url": "https://www.youtube.com/watch?v=VIDEO_ID"
  }
]
```

### POST `/api/rate`

Adds or updates a vote for one YouTube video.

Request body:

```json
{
  "video_id": "VIDEO_ID",
  "vote": 1
}
```

`vote` must be `1` or `-1`.

Example:

```bash
curl -X POST "http://127.0.0.1:8010/api/rate" \
  -H "Content-Type: application/json" \
  -d '{"video_id": "VIDEO_ID", "vote": 1}'
```

Response:

```json
{
  "video_id": "VIDEO_ID",
  "net_votes": 1
}
```

Voting rules:

- One person gets one vote per video.
- Re-voting updates the existing vote instead of stacking votes.
- The server stores a SHA-256 hash of IP plus user-agent, not the raw IP.
- More than 20 votes per minute returns `429`.
- Invalid votes return `400`.

## Ranking Logic

The ranking code lives in `app/ranking.py`.

Positive signals:

- `live wallpaper`
- `moving wallpaper`
- `animated wallpaper`
- `wallpaper engine`
- `wallpaper`
- `seamless`
- `loop`
- `4k`, `8k`, `2160p`, `1440p`, `1080p`
- good desktop aspect ratios
- reasonable loop duration
- community upvotes

Hard exclusions:

- tutorials
- guides
- reactions
- reviews
- gameplay
- trailers
- lyrics
- podcasts
- vlogs
- top-10 style videos
- vertical Shorts

Each search result includes a `breakdown` object so reviewers can see how the score was built.

## Deployment

The live demo is deployed on Render:

```text
https://wallfinder.onrender.com
```

The public API docs are here:

```text
https://wallfinder.onrender.com/api-docs
```

The `Procfile` contains the production start command:

```text
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render sets `$PORT` automatically.

Render deploy steps:

1. Push this repo to GitHub.
2. Go to Render.
3. Click **New**.
4. Choose **Deploy from GitHub repo**.
5. Select `birdyboyiyert/wallfinder`.
6. Use `pip install -r requirements.txt` as the build command.
7. Use `uvicorn app.main:app --host 0.0.0.0 --port $PORT` as the start command.
8. Render gives the app a public `.onrender.com` URL.
9. Test the live API:

```bash
curl "https://wallfinder.onrender.com/api/search?q=lofi%20rain%20wallpaper&limit=10"
```

Test the POST endpoint:

```bash
curl -X POST "https://wallfinder.onrender.com/api/rate" \
  -H "Content-Type: application/json" \
  -d '{"video_id": "VIDEO_ID", "vote": 1}'
```

Open the public docs page:

```text
https://wallfinder.onrender.com/api-docs
```

## Important Notes

- CORS is open, so browser apps can call the API.
- SQLite is fine for local use and demos.
- On Render's free tier, `wallfinder.db` is ephemeral and can reset after redeploys.
- Sorry for any Render weirdness: free Render services can sleep or cold-start. The first request
  or two may briefly return `404`/wake-up behavior, then the same endpoint works once the service
  is running.
- YouTube may rate-limit `yt-dlp` from cloud IP addresses. If that happens, future options are
  the official YouTube Data API or running the project from the Raspberry Pi.
