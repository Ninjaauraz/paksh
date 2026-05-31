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
  GET /api/events/{id}   -> full analysis for one event
  GET /api/stats         -> header counts
"""

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


@app.get("/api/events")
def list_events():
    return {"events": get_all_events()}


@app.get("/api/blindspots")
def list_blindspots():
    return {"events": get_blindspot_events()}


@app.get("/api/topics")
def list_topics():
    return {"topics": get_topics()}


@app.get("/api/events/{event_id}")
def event_detail(event_id: int):
    event = get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.get("/api/stats")
def stats():
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
    fields = ("id", "name", "language", "website", "ownership", "lean", "label",
              "confidence", "contested", "review_status", "last_reviewed",
              "rationale", "subscores")
    rows = [{k: s.get(k) for k in fields} for s in SOURCES]
    return {"sources": rows, "summary": coverage_summary()}


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
