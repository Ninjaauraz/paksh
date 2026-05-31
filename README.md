# पक्ष · Paksh

**See every side of India's news.** Paksh is a Ground News-style media
transparency platform built for India. It reads the same news event across many
outlets — English and Hindi — and shows how each side of the spectrum
(**Left · Centre · Right**) covers it: a neutral bullet brief, a bias
distribution, how each side framed it, and the **Blindspots** — stories one side
is barely covering, so you never miss what the other side is (or isn't) saying.

Free to run. Powered by Google Gemini's free tier.

## What's inside (V2)

- **Top Stories feed** — image cards with a dominant-lean callout ("67% Centre · 9 sources") and a bias bar.
- **Blindspot feed** — stories one side is barely covering (the "burst your bubble" view).
- **Topic filters** — Politics, Economy, International, Sports, and more.
- **The Prism (per story)** — neutral brief, bias breakdown, a Left/Centre/Right toggle, per-outlet framing, notable language, divergence & omissions.
- **English + Hindi** — clustered together by event.

## What you need first
- **Python 3.9+**
- **A free Gemini API key** — https://aistudio.google.com (no credit card)

## Setup (one time)
Open the folder in VS Code, open a **Command Prompt** terminal (not PowerShell):
```bash
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
Copy `.env.example` → `.env` and paste your key:
```
GEMINI_API_KEY=your-key-here
```

## See it instantly (demo data)
```bash
python seed_demo.py
uvicorn main:app --host 0.0.0.0 --port 8000
```
Open **http://localhost:8000**. 4 DEMO events, 2 of them in the **Blindspot** tab.
(Demo data is synthetic with no images, so cards show the topic placeholder; real
ingested news brings real images.) If port 8000 is busy, use `--port 8001`.

## Run it for real (live Indian news)
```bash
python ingest.py     # 1. pull latest articles (+ images) from every feed
python analyze.py    # 2. cluster, summarise, tag topics, analyse framing
uvicorn main:app --host 0.0.0.0 --port 8000
```
Run `ingest.py` a few times across a few hours before `analyze.py`. Paksh only
surfaces events covered by 2+ outlets; Blindspots need enough sources per side.

## How it works
```
ingest.py    →   analyze.py                    →   main.py
(RSS + images)   (Gemini: cluster, brief, topic,    (serves site + /api/events,
                  per-side framing. Lean from        /api/blindspots, /api/topics)
                  YOUR sources.py, not the AI.)
        \             |                              /
         \            v                             /
          ------>   paksh.db (SQLite)  <-----------
```
Blindspots and dominant lean are computed from the lean of each publisher
covering a story — pure maths, not AI opinion.

## Where "lean" comes from (important)
Lean is a property of the publisher, set by YOU in `sources.py` — never guessed
by the AI. Shipped values are placeholders reflecting commonly-cited perceptions;
they're contested. Review them and ground them in citable sources before
publishing. Note: US-style Left/Centre/Right maps imperfectly onto India.

## Make it yours
- Outlets & lean: `sources.py`
- Cost cap & model: `MAX_EVENTS_PER_RUN` / `MODEL` in `analyze.py`
- Blindspot thresholds: `compute_blindspot()` in `database.py`
- Topics: `TOPICS` in `analyze.py`

## Cost
Gemini free tier ~1,500 requests/day — far more than Paksh uses. (Free tier may
use prompts for training; fine for public news text.)

## Going live for India (later)
Railway/Render, SQLite → PostgreSQL, a scheduled ingest+analyse job, proper image
caching (don't hotlink at scale), a domain. Then app, extension, personal bias score.

---
Built step by step. Run it, break it, change it — that's how you learn it.
