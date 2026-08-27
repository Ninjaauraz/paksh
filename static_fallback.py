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

# Paksh 6C: search normalization constants live in database.py (added Phase 6B) -
# imported, not re-declared, since (unlike database.py<->supabase_content.py, which
# genuinely can't share due to a real import cycle - see database.py's own comment)
# database.py has no module-level dependency on this file, only local/deferred
# imports inside function bodies (get_all_events(), get_event(), etc.) - so a
# module-level import here in the other direction is safe. Verified empirically:
# `import database; import static_fallback` and the reverse order both load cleanly.
from database import MAX_SEARCH_QUERY_LEN, MAX_SEARCH_TOKENS, DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT

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


def get_events_archive():
    """Paksh 6C: the older tail beyond RECENT_FEED_N (see export_static.py's
    build() - events.json and events-archive.json are both written from the
    SAME `feed_row()`, so their row shapes are identical, just the head vs
    tail split of the full corpus). This file was already committed and
    already read by the live site's frontend (apiGet("events-archive")) -
    this function is simply the first thing that reads it server-side.

    Added specifically to close a real gap found while auditing for Phase 6C:
    before this, static_fallback.py had no way to reach the archived ~12.2k
    events at all - only the 1,500-row recent window (get_events() above) -
    so database.get_all_events()'s existing static-fallback path, and
    main.py's /api/events-archive route built on top of it, silently
    returned an EMPTY archive during a true Supabase+SQLite outage (slicing
    the already-1,500-row snapshot at [1500:] leaves nothing). That pre-existing
    gap is not fixed here (main.py's /api/events-archive route is unchanged -
    out of scope for this phase, see the Phase 6C report); this function
    exists so the NEW static search tier below does not inherit it."""
    return _load("events-archive")


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


def search_events(query: str, limit: int = DEFAULT_SEARCH_LIMIT):
    """Paksh 6C: the final search tier, reached only when Supabase is unavailable
    AND SQLite has no usable content (see database.search_events()'s fallback into
    this function). Returns the SAME {"query","count","limit","results"} envelope
    and result-row shape Phase 6A/6B established, or None if the snapshot itself is
    unavailable/malformed - matching every other function in this module's "return
    None, never raise" convention, so the caller can fall through to its own final
    empty-result behavior exactly as it already does for get_events()/get_event().

    Matching semantics are PORTED from the existing, proven client-side matcher in
    static/app.jsx (SearchPage, see the token-AND filter around app.jsx:3276-3278) -
    not redesigned: case-insensitive substring match, every token must appear
    SOMEWHERE in the haystack, no fuzzy/similarity ranking invented for this tier.
    Two adaptations from the client version, both forced by /api/search's existing
    contract rather than chosen for elegance:
      * the client haystack is language-gated (only the currently-displayed
        title/summary, per the site's EN/HI toggle) via toCard()'s headline/lead
        fields; /api/search has no language parameter (6A/6B never added one, and
        this phase is not allowed to introduce new query parameters), so this
        tier searches title+title_hi+summary+summary_hi together, same as the
        Supabase/SQLite tiers - language-agnostic, not client-parity on this one
        specific point (documented here and in the Phase 6C report, not hidden).
      * "topic" IS included in the haystack (the client matcher's `_hay` includes
        `c.topic`) - Phase 6A/6B deliberately did NOT search topic (out of scope
        for those phases' narrower brief). Kept here because this phase's own
        instructions explicitly name "headline + lead + summary + topic haystack"
        as a property of the existing matcher to preserve.

    No ranking beyond the corpus's own existing order: get_events() + get_events_archive()
    are already created_at-DESC (the same order database.get_all_events() produces,
    which export_static.py sliced into these two files) - preserved as-is, matching
    the client matcher's own behavior of filtering baseCards in place rather than
    re-sorting by relevance. No new ranking formula invented for this tier.

    Full corpus: reads get_events() (recent 1,500) AND get_events_archive() (the
    remaining ~12.2k) together - NOT capped at either file alone."""
    q = " ".join((query or "").split())
    if not q:
        return {"query": "", "count": 0, "limit": int(limit), "results": []}
    if len(q) > MAX_SEARCH_QUERY_LEN:
        q = q[:MAX_SEARCH_QUERY_LEN].rstrip()
    lim = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    tokens = [t for t in q.split(" ") if t][:MAX_SEARCH_TOKENS]
    if not tokens:
        return {"query": q, "count": 0, "limit": lim, "results": []}

    recent = get_events()
    archive = get_events_archive()
    if recent is None and archive is None:
        return None   # snapshot itself unavailable/malformed - let the caller fall through
    corpus = (recent["events"] if recent else []) + (archive["events"] if archive else [])

    from export_static import _snippet   # local import: mirrors this module's own
                                          # get_events()-style lazy pattern; export_static.py
                                          # has no dependency back on this module (verified),
                                          # kept local anyway for consistency with the rest
                                          # of this file's import style
    tok_lower = [t.lower() for t in tokens]
    matched = []
    for e in corpus:
        hay = (f"{e.get('title','')} {e.get('title_hi','')} "
               f"{e.get('summary','')} {e.get('summary_hi','')} {e.get('topic','')}").lower()
        if all(tok in hay for tok in tok_lower):
            matched.append(e)

    results = []
    for e in matched[:lim]:
        lean_counts = e.get("lean_counts") or {"left": 0, "center": 0, "right": 0}
        results.append({
            "id": e["id"], "title": e.get("title") or "", "title_hi": e.get("title_hi") or "",
            "summary": _snippet(e.get("summary")), "summary_hi": _snippet(e.get("summary_hi")),
            "topic": e.get("topic"), "lean_counts": lean_counts,
            "sources": e.get("source_count", sum(lean_counts.values())),
            "storyline_id": e.get("storyline_id"),
            "created_at": e.get("created_at"), "published_at": e.get("published_at"),
        })
    return {"query": q, "count": len(results), "limit": lim, "results": results}
