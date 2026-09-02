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
from Supabase content tables (supabase_content.py) instead of the local
paksh.db. Default is unchanged: PAKSH_CONTENT_BACKEND unset (or any value
other than "supabase") reads SQLite exactly as before - this file's behavior
does not change unless you explicitly opt in, per the Phase 1 brief (goal G:
existing production behavior remains unchanged unless the live API is
explicitly enabled). If Supabase is unreachable while the backend is set to
"supabase", each route falls back to SQLite automatically rather than 500ing -
"fail safely", per the brief's API design requirement. Static JSON remains a
separate, independent fallback for the Vercel-deployed static site (see
export_static.py).

Historical note: this file was briefly deployed to Render as a live content
API (2026-08-21 to 2026-09-01), with the Supabase content tables it reads
mirrored from paksh.db for that purpose. That deployment was retired and the
mirrored tables were dropped; production (paksh.vercel.app) now serves only
the static JSON export and never calls this file. It remains here for local
development and as the read layer this toggle exercises.
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
    get_event, count_articles, has_content, search_events as sqlite_search_events,
)
from sources import SOURCES, coverage_summary
from export_static import feed_row, RECENT_FEED_N
import supabase_content as sb
import content_cache
import static_fallback

# Paksh perf phase 4B: storylines (and the numpy/cluster imports it pulls in)
# is only needed by the SQLite-fallback storyline routes below, never by the
# Supabase-mode happy path - deferred so importing main.py doesn't pay for it.
# Cached after the first attempt (success or failure) so it's a no-op after that.
_build_storylines_fn = None
_build_storylines_loaded = False


def _get_build_storylines():
    global _build_storylines_fn, _build_storylines_loaded
    if not _build_storylines_loaded:
        try:
            from storylines import build_storylines as _bs
        except ImportError:
            _bs = None
        _build_storylines_fn = _bs
        _build_storylines_loaded = True
    return _build_storylines_fn

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
    # Paksh perf phase 4C: Supabase mode never reads SQLite on its happy path, so
    # don't pay for opening/migrating paksh.db at every boot. database.get_connection()
    # guarantees init_db() still runs, exactly once, before any real SQLite access -
    # so if Supabase ever fails and a route falls back to SQLite, the schema is
    # created on that first fallback read instead of having been skipped entirely.
    if CONTENT_BACKEND != "supabase":
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
    # Paksh phase 5.1: only run live clustering against real SQLite rows -
    # get_all_events() may now return static_fallback's (lightened) shape when
    # SQLite has no usable content, and that hasn't been verified to interact
    # correctly with build_storylines(). Skipping it here just means no
    # storyline_id annotation during that degraded tier - already best-effort,
    # never blocks the archive itself either way.
    if has_content():
        build_storylines = _get_build_storylines()
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
    if not has_content():
        # Paksh phase 5.1: same reasoning as list_storylines() above - serve
        # the pre-built per-storyline file directly, don't run build_storylines()
        # against static_fallback's event shape.
        snapshot = static_fallback.get_storyline(storyline_id)
        if snapshot is not None:
            return snapshot
        raise HTTPException(status_code=404, detail="Storyline not found")
    build_storylines = _get_build_storylines()
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
    if not has_content():
        # Paksh phase 5.1: the static snapshot's blindspots.json carries the
        # richer {events, left_heavier, right_heavier, aggregate} shape (the
        # SAME field names app.jsx already reads from the Supabase path) -
        # deliberately used here rather than the narrower SQLite-mode shape
        # below, so Coverage Gaps stays meaningful during an outage instead
        # of rendering empty. See the Phase 5.1 report for the reasoning.
        snapshot = static_fallback.get_blindspots()
        if snapshot is not None:
            # Paksh 7B (P3-A hardening): the same "not explicitly incomplete" check
            # database.get_all_events()'s own static-fallback branch already applies
            # (content_complete is not False) - export_static.py writes this file from
            # a single already-gated get_all_events() call, so this is a no-op on real
            # data today, but it closes the same defense-in-depth gap for this direct
            # read route, matching the pattern already used elsewhere.
            def _pub(e):
                return e.get("content_complete") is not False
            snapshot = {
                **snapshot,
                "events": [e for e in snapshot.get("events", []) if _pub(e)],
                "left_heavier": [e for e in snapshot.get("left_heavier", []) if _pub(e)],
                "right_heavier": [e for e in snapshot.get("right_heavier", []) if _pub(e)],
            }
            return snapshot
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
    if not has_content():
        # Paksh phase 5.1: serve the pre-built storylines.json directly rather
        # than feeding static_fallback's (lightened) events into
        # build_storylines() - the two haven't been verified to interact
        # correctly, and the pre-built file already matches this route's
        # exact output shape (traced field-by-field, see the Phase 5.1 report).
        snapshot = static_fallback.get_storylines()
        if snapshot is not None:
            return snapshot
        return {"storylines": []}
    build_storylines = _get_build_storylines()
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
    # Paksh 7B: content_complete is False ONLY for a newly-generated event the
    # publication gate has explicitly decided not to show (see analyze.py::
    # compute_content_complete). None (grandfathered/pre-gate) and True both pass -
    # same "not is False" rule get_all_events()/database._is_publishable() apply.
    # A direct /api/events/{id} request must not be able to bypass that decision.
    if CONTENT_BACKEND == "supabase":
        try:
            event = sb.get_event(event_id)
            if event is None or event.get("content_complete") is False:
                raise HTTPException(status_code=404, detail="Event not found")
            return event
        except sb.SupabaseUnavailable:
            pass
    event = get_event(event_id)
    if event is None or event.get("content_complete") is False:
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


@app.get("/api/search")
def search(q: str = ""):
    """Paksh 6A: full-corpus search over events.title/title_hi/summary/summary_hi
    via supabase_content.search_events() (the search_events() Postgres RPC) - reads
    the Supabase events table directly, so it is NOT limited by /api/events' 1500-row
    window or /api/events-archive's 3000-row cap (together <=33% of the ~13.7k-row
    corpus).

    Paksh 6B: on SupabaseUnavailable (or when CONTENT_BACKEND != "supabase"), falls
    through to database.search_events() - the SAME SQLite-backed full-corpus search,
    following the identical try/except-then-fall-through shape every sibling route in
    this file already uses (e.g. list_events() above). database.search_events()
    itself returns the same empty-but-200 shape when SQLite has no usable content
    (has_content() is False) - no separate "final empty" branch is needed here, and
    no static-snapshot search tier exists yet (that's Phase 6C, out of scope)."""
    if CONTENT_BACKEND == "supabase":
        try:
            return sb.search_events(q)
        except sb.SupabaseUnavailable:
            pass  # fall through to SQLite below - Paksh 6B
    return sqlite_search_events(q)


@app.get("/health")
def health():
    """Paksh phase 5C/5.1F: liveness/readiness signal, deliberately cheap -
    never touches the 13k-event dataset. If a 200 response comes back at all,
    the process is up (that's the process-health signal). In Supabase mode,
    also reports the full fallback ladder's state:
      - supabase_reachable: one small count query (supabase_content.is_reachable())
      - sqlite_fallback_available: phase 5.1 upgrade - now a real content check
        (database.has_content()), not just DB_PATH.exists(). A freshly-created
        empty paksh.db (Render's ephemeral-disk case) satisfies .exists() but
        has zero usable rows - that used to read as "available" when it wasn't.
      - static_snapshot_available: the committed _site/data/*.json emergency tier
      - content_tier: which of the three would actually serve a request right
        now - "supabase" / "sqlite" / "static_snapshot" / "unavailable"."""
    info = {"status": "ok", "content_backend": CONTENT_BACKEND}
    if CONTENT_BACKEND == "supabase":
        supabase_ok = sb.is_reachable()
        sqlite_ok = has_content()
        snapshot_ok = static_fallback.is_available()
        info["supabase_reachable"] = supabase_ok
        info["sqlite_fallback_available"] = sqlite_ok
        info["static_snapshot_available"] = snapshot_ok
        if supabase_ok:
            info["content_tier"] = "supabase"
        elif sqlite_ok:
            info["content_tier"] = "sqlite"
        elif snapshot_ok:
            info["content_tier"] = "static_snapshot"
            info["static_snapshot_built_at"] = static_fallback.snapshot_built_at()
        else:
            info["content_tier"] = "unavailable"
    return info


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
