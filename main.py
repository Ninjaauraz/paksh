"""
main.py
-------
STEP 3 — the web server. Serves the Paksh site AND its data API from one process.

Run with:   uvicorn main:app --reload
Open:       http://127.0.0.1:8000

Endpoints:
  GET /                  -> the Paksh web app
  GET /api/events        -> all analysed events (newest first)
  GET /api/blindspots    -> only Blindspot events (one side barely covering)
  GET /api/topics        -> distinct topics present (for the filter bar)
  GET /api/storylines    -> the storyline index
  GET /api/events/{id}   -> full analysis for one event
  GET /api/stats         -> header counts

PAKSH 2.0 PHASE 1 — content backend toggle
-------------------------------------------
Set PAKSH_CONTENT_BACKEND=supabase to read events/topics/sources/storylines
from the new Supabase content tables (supabase_content.py) instead of the
local paksh.db. Default is unchanged: PAKSH_CONTENT_BACKEND unset (or any
value other than "supabase") reads SQLite exactly as before - this file's
behavior does not change unless you explicitly opt in, per the Phase 1 brief
(goal G: existing production behavior remains unchanged unless the live API
is explicitly enabled). If Supabase is unreachable while the backend is set to
"supabase", each route falls back to SQLite automatically rather than 500ing -
"fail safely", per the brief's API design requirement. Static JSON remains a
separate, independent fallback for the Vercel-deployed static site (see
export_static.py) - this toggle affects every deployment of `main.py`,
including the Render-hosted production API (PAKSH_CONTENT_BACKEND=supabase)
that paksh.news's frontend calls directly since Phase 3.8, not just local runs.
"""

import os
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from database import (
    init_db, get_all_events, get_blindspot_events, get_topics,
    get_event, count_articles,
)
from sources import SOURCES, coverage_summary
from export_static import feed_row, RECENT_FEED_N
import supabase_content as sb
import content_cache

try:
    from storylines import build_storylines
except ImportError:
    build_storylines = None

CONTENT_BACKEND = os.environ.get("PAKSH_CONTENT_BACKEND", "sqlite").lower()

app = FastAPI(title="Paksh", description="News transparency for India")
STATIC_DIR = Path(__file__).parent / "static"

# The site is served from this same process (same origin), so CORS isn't needed
# for it. This permissive policy only matters if you later run a separate
# frontend (e.g. a Vite/React dev server) that calls this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    if CONTENT_BACKEND == "supabase":
        # Paksh 2.7: best-effort, non-blocking warm of the two expensive homepage
        # caches, so the first real visitor doesn't pay the cold-build cost. Never
        # blocks app startup - see content_cache.warm()'s docstring. If this warm
        # fails or hasn't finished yet, the routes below fall back to the normal
        # lazy single-flight path, which is correct either way.
        content_cache.warm("events", sb.get_events)
        content_cache.warm("blindspots", sb.get_blindspots)


@app.get("/api/events")
def list_events():
    if CONTENT_BACKEND == "supabase":
        try:
            data, _status = content_cache.get_or_build(
                "events", sb.get_events, unavailable_exc=sb.SupabaseUnavailable)
            return data
        except sb.SupabaseUnavailable:
            pass  # fail safe -> SQLite below
    return {"events": get_all_events()}


@app.get("/api/events-archive")
def events_archive():
    """Phase 1.75: the older tail beyond the RECENT_FEED_N window app.jsx lazy-loads on
    Search/Topic (see app.jsx's apiGet("events-archive") call). Same row shape as
    /api/events (via the same feed_row() export_static.py itself uses for events.json/
    events-archive.json), just the tail slice instead of the head."""
    if CONTENT_BACKEND == "supabase":
        try:
            return sb.get_events_archive()
        except sb.SupabaseUnavailable:
            pass
    events = get_all_events()
    archive = events[RECENT_FEED_N:]
    now = datetime.utcnow()
    story_map = {}
    if build_storylines is not None:
        try:
            _, story_map = build_storylines(events)
        except Exception:
            pass  # storyline_id annotation is best-effort, never blocks the archive itself
    return {"events": [feed_row(e, story_map, now) for e in archive]}


@app.get("/api/storylines/{storyline_id}")
def storyline_detail(storyline_id: str):
    """Phase 1.75: full single-saga detail (app.jsx's apiGet("storylines/"+id) on the
    Storyline page) - the SAME shape build_storylines() produces and export_static.py
    writes to data/storylines/<id>.json, computed live rather than duplicated."""
    if CONTENT_BACKEND == "supabase":
        try:
            sl = sb.get_storyline(storyline_id)
            if sl is None:
                raise HTTPException(status_code=404, detail="Storyline not found")
            return sl
        except sb.SupabaseUnavailable:
            pass
    if build_storylines is None:
        raise HTTPException(status_code=404, detail="Storyline not found")
    storylines, _ = build_storylines(get_all_events())
    for s in storylines:
        if str(s["id"]) == str(storyline_id):
            return s
    raise HTTPException(status_code=404, detail="Storyline not found")


@app.get("/api/blindspots")
def list_blindspots():
    if CONTENT_BACKEND == "supabase":
        try:
            data, _status = content_cache.get_or_build(
                "blindspots", sb.get_blindspots, unavailable_exc=sb.SupabaseUnavailable)
            return data
        except sb.SupabaseUnavailable:
            pass
    return {"events": get_blindspot_events()}


@app.get("/api/topics")
def list_topics():
    if CONTENT_BACKEND == "supabase":
        try:
            return sb.get_topics()
        except sb.SupabaseUnavailable:
            pass
    return {"topics": get_topics()}


@app.get("/api/storylines")
def list_storylines():
    """Paksh 2.2 objective 1: was a hardcoded {"storylines": []} stub in SQLite mode
    (storylines were build-time-only through Phase 2.1). Now reuses the SAME
    build_storylines() call storyline_detail() below already makes live - no second
    algorithm, no changed semantics - and returns the SAME lean-index shape
    sb.get_storylines() already returns (id/title/title_hi/topic/region/n_events/
    start/end/updated_at, no per-event payload), so SQLite and Supabase are
    response-compatible."""
    if CONTENT_BACKEND == "supabase":
        try:
            return sb.get_storylines()
        except sb.SupabaseUnavailable:
            pass
    if build_storylines is None:
        return {"storylines": []}
    storylines, _ = build_storylines(get_all_events())
    storylines = sorted(storylines, key=lambda s: s.get("updated_at") or "", reverse=True)
    return {"storylines": [{
        "id": s["id"], "title": s.get("title"), "title_hi": s.get("title_hi"),
        "topic": s.get("topic"), "region": s.get("region"), "n_events": s.get("n_events"),
        "start": s.get("start"), "end": s.get("end"), "updated_at": s.get("updated_at"),
    } for s in storylines]}


@app.get("/api/events/{event_id}")
def event_detail(event_id: int):
    if CONTENT_BACKEND == "supabase":
        try:
            event = sb.get_event(event_id)
            if event is None:
                raise HTTPException(status_code=404, detail="Event not found")
            return event
        except sb.SupabaseUnavailable:
            pass
    event = get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.get("/api/stats")
def stats():
    if CONTENT_BACKEND == "supabase":
        try:
            return sb.get_stats()
        except sb.SupabaseUnavailable:
            pass  # fail safe -> SQLite below
    events = get_all_events()
    return {
        "events": len(events),
        "articles": count_articles(),
        "sources": len(SOURCES),
        "blindspots": len([e for e in events if e["blindspot"]]),
    }


@app.get("/api/sources")
def list_sources():
    """Public transparency view of the rating registry."""
    if CONTENT_BACKEND == "supabase":
        try:
            return sb.get_sources()
        except sb.SupabaseUnavailable:
            pass
    fields = ("id", "name", "language", "website", "ownership", "lean", "label",
              "confidence", "contested", "review_status", "last_reviewed",
              "rationale", "axes")
    rows = [{k: s.get(k) for k in fields} for s in SOURCES]
    return {"sources": rows, "summary": coverage_summary()}


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
