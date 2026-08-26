"""
static_fallback.py - Phase 5.1: the final, read-only emergency content tier.

Fallback hierarchy:  Supabase  ->  SQLite (real content)  ->  this module  ->  empty.

Reads the SAME committed `_site/data/*.json` files export_static.py already
produces for the Vercel-deployed static site (see .gitignore's own note:
"_site/ IS committed on purpose"). These files are already present on every
Render deploy today - this module is simply the first thing that reads them
server-side, from the API process, as an emergency source.

Shapes were traced field-by-field against database.py's current SQLite-mode
output before writing this (see the Phase 5.1 report): topics, storylines,
single-storyline-detail, and single-event-detail match EXACTLY. events and
blindspots differ from the raw SQLite shape (no summary_points/summary_points_hi,
plus importance/feed_rank/storyline_id) - a safe, strictly additive superset,
since Phase 2 already proved summary_points/summary_points_hi have zero
frontend rendering consumers.

STRICT RULES (do not relax these without a fresh review):
  * Read-only. Never writes into _site/data, never writes into paksh.db.
  * Each file is parsed once per process and cached in memory - these are
    multi-MB files; re-parsing on every request during an outage would be
    its own performance problem.
  * Fails safe: a missing or malformed file returns None and never raises
    past this module's boundary, so whatever called it can fall through to
    its own existing final-fallback behavior unchanged.
"""
import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "_site" / "data"
_STORYLINES_DIR = _DATA_DIR / "storylines"
_EVENTS_DIR = _DATA_DIR / "events"
_cache: dict = {}


def _load(name: str):
    """Parse _site/data/<name>.json once, cache the result. Returns None
    (never raises) if the file is missing or not valid JSON."""
    if name in _cache:
        return _cache[name]
    try:
        with open(_DATA_DIR / f"{name}.json", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    _cache[name] = data
    return data


def _load_one(cache_key: str, path: Path):
    if cache_key in _cache:
        return _cache[cache_key]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    _cache[cache_key] = data
    return data


def is_available() -> bool:
    """Cheap check for /health - existence only, never parses the file."""
    return (_DATA_DIR / "events.json").exists()


def snapshot_built_at():
    """Phase 5.1G: the snapshot's own build timestamp, already written by
    export_static.py to freshness.json - surfaced as-is, not invented here."""
    data = _load("freshness")
    return data.get("built_at") if data else None


def get_events():
    """Returns the same {"events": [...]} shape as database.get_all_events()
    wrapped in a dict, or None if the snapshot is unavailable/malformed."""
    return _load("events")


def get_blindspots():
    """Returns {"events", "left_heavier", "right_heavier", "aggregate"} - a
    RICHER shape than main.py's current SQLite-mode /api/blindspots (which
    only ever returns {"events": [...]}). Deliberate: these are the SAME
    field names the Supabase-mode contract and app.jsx's loadAll() already
    use (`b.left_heavier||[]`, `b.right_heavier||[]`, `b.aggregate||{}}`) -
    not new/invented fields - and the frontend already defends against their
    absence, so adding them here is additive-safe, not a breaking shape
    change. Chosen deliberately over the narrower SQLite-mode shape because
    it's what actually makes the Coverage Gaps rail meaningful instead of
    empty during an outage - see the Phase 5.1 report for the full reasoning."""
    return _load("blindspots")


def get_topics():
    return _load("topics")


def get_storylines():
    return _load("storylines")


def get_storyline(storyline_id: str):
    """Per-storyline files live one-per-id under _site/data/storylines/ -
    cached individually on first request rather than all at once, since
    there are hundreds of small files and most won't be requested during
    any single outage."""
    return _load_one(f"storylines/{storyline_id}", _STORYLINES_DIR / f"{storyline_id}.json")


def get_event(event_id):
    return _load_one(f"events/{event_id}", _EVENTS_DIR / f"{event_id}.json")
