"""
supabase_content.py - Paksh 2.0 Phase 1: thin read layer over the Supabase
content tables (public.events/articles/outlets/storylines/topics).

Deliberately minimal, per the Phase 1 brief's "thinnest safe server layer"
requirement:
  * No new dependency - uses `requests` (already a real, declared transitive
    dependency via google-genai in requirements.txt) against Supabase's
    PostgREST REST API (the SAME `/rest/v1/...` surface app.jsx already talks
    to for accounts, just a different table set). A single shared, pooled
    Session (perf phase 4D) avoids paying a fresh TCP+TLS handshake on every
    call - see `_session` below.
  * No service-role key anywhere. Content tables are PUBLIC-READ (RLS policy
    "public read <table>" applied in the paksh_content_schema_v1 migration)
    and have NO write policy for anon/authenticated - verified live: an
    unauthenticated POST to /rest/v1/events returns 401 / row-level security
    violation. So the anon key (already public in app.jsx) is sufficient and
    appropriate for every function here; nothing privileged is held server-side.
  * Reshapes PostgREST's raw-array responses into the exact JSON shape
    `static/app.jsx`'s apiGet() already expects from BOTH `/api/<resource>`
    and `/data/<resource>.json` (e.g. {"events": [...]}), so main.py's routes
    can serve this data with zero frontend change.

This module does not replace database.py or the SQLite pipeline - it is an
ADDITIVE read path over the (currently partial - see the Phase 1 report)
Supabase content mirror.
"""
import json
import os
import urllib.parse
import requests
from datetime import datetime

# Reused, not reimplemented (Phase 1.5 objective 3): _importance/_feed_rank/_civic_mult
# are pure functions of fields already present on an event (lean counts, international
# count, created_at/published_at, topic, title) - but they decay against `now`, so they
# are inherently REQUEST-TIME values, not something safe to persist as a static column
# (a stored feed_rank would be stale the instant time passes). export_static.py already
# computes an "as of export time" snapshot of these for the static JSON; here we compute
# the "as of right now" value on every call, using the identical formulas, imported
# directly rather than re-derived, so results can never drift from what the static
# export/production site already does.
from export_static import _importance, _feed_rank, _civic_mult, _lighten, RECENT_FEED_N
from database import event_language

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zzjsjqqcpyyodatlmcux.supabase.co")
# Public anon key - the same one already shipped to the browser in static/app.jsx.
# Never a secret; RLS is what actually protects the tables (see module docstring).
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp6anNqcXFjcHl5b2RhdGxtY3V4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxNzU1OTIsImV4cCI6MjA5Mzc1MTU5Mn0.U-TRJegvnt7iO1mM9nok319FJHszJ9HNzuRZLfuuvys",
)


class SupabaseUnavailable(Exception):
    """Raised on any network/HTTP failure talking to Supabase, so callers
    (main.py) can fail safe rather than 500 - the static export stays the
    fallback per the Phase 1 brief (goal F: static JSON remains the fallback)."""


request_count = 0  # Paksh 2.7: diagnostic-only counter (never read by request-
                    # serving code) - lets tests PROVE a cache hit makes zero
                    # Supabase calls, rather than infer it from timing alone.

# Paksh perf phase 4D: one shared, connection-pooled Session per process instead
# of a fresh TCP+TLS handshake on every _get()/_count() call - measured ~260-320ms
# for a cold connection vs ~120ms for a reused one. `requests` is already a real
# (transitive) dependency here - it's declared by google-genai in requirements.txt
# - so this adds no new package. Session's pooling goes through urllib3's
# connection pool, which is thread-safe by design; every call here is a simple
# stateless GET with no per-call mutation of session state (headers are passed
# per-request, not set on the session), so sharing one Session across FastAPI's
# threadpool is safe.
_session = requests.Session()


def _get(path: str, timeout: float = 5.0, max_retries: int = 2):
    """Paksh 2.1: a multi-page pagination fetch (see _get_paginated below) makes
    many requests in a row, and testing found PostgREST occasionally returns a
    genuine transient HTTP 500 under that load (reproduced twice independently -
    once against /api/blindspots in the 2.0B audit, once mid-pagination here).
    A short retry with backoff absorbs that without hiding real problems: only
    5xx/network failures are retried (a 4xx means the request itself is wrong -
    retrying it would just waste time and mask a real bug), and the retry budget
    is small (2 extra tries, <1s total added latency) because this is a live read
    path a user is waiting on, not a batch job - main.py's existing SupabaseUnavailable
    -> SQLite fallback is still the backstop if retries are exhausted."""
    import time
    url = SUPABASE_URL + "/rest/v1" + path
    headers = {"apikey": SUPABASE_ANON_KEY, "Accept": "application/json"}
    global request_count
    attempt = 0
    while True:
        attempt += 1
        request_count += 1
        try:
            resp = _session.get(url, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            if attempt <= max_retries:
                time.sleep(0.3 * attempt)
                continue
            raise SupabaseUnavailable(str(e)) from e
        if resp.status_code >= 400:
            if resp.status_code >= 500 and attempt <= max_retries:
                time.sleep(0.3 * attempt)
                continue
            raise SupabaseUnavailable(f"HTTP Error {resp.status_code}: {url}")
        try:
            return resp.json()
        except ValueError as e:   # malformed JSON body on an otherwise-200 response -
            if attempt <= max_retries:   # same fail-safe treatment as any other bad read
                time.sleep(0.3 * attempt)
                continue
            raise SupabaseUnavailable(str(e)) from e


def _count(path: str, timeout: float = 5.0, max_retries: int = 2) -> int:
    """Paksh 4.3: an exact row count via PostgREST's `Prefer: count=exact`,
    with `limit=0` so zero rows are ever transferred - only the `Content-Range`
    response header (e.g. "*/13486") is read. Same retry/fail-safe shape as
    _get() above, so a stats query is exactly as robust as any other read
    here - never a second, competing way of talking to Supabase."""
    import time
    sep = "&" if "?" in path else "?"
    url = SUPABASE_URL + "/rest/v1" + path + f"{sep}limit=0"
    headers = {"apikey": SUPABASE_ANON_KEY, "Accept": "application/json", "Prefer": "count=exact"}
    global request_count
    attempt = 0
    while True:
        attempt += 1
        request_count += 1
        try:
            resp = _session.get(url, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            if attempt <= max_retries:
                time.sleep(0.3 * attempt)
                continue
            raise SupabaseUnavailable(str(e)) from e
        if resp.status_code >= 400:
            if resp.status_code >= 500 and attempt <= max_retries:
                time.sleep(0.3 * attempt)
                continue
            raise SupabaseUnavailable(f"HTTP Error {resp.status_code}: {url}")
        return int(resp.headers.get("Content-Range", "*/0").split("/")[-1])


# Paksh 2.1 objective 1: PostgREST's platform default caps any single response at
# 1000 rows regardless of the `limit` query param - confirmed empirically (a request
# for limit=1500 silently came back with exactly 1000, no error). This is NOT
# something to raise via Supabase project settings (that changes behavior for every
# consumer, hides the problem instead of handling it, and isn't ours to reconfigure
# here) - instead, fetch in chunks at-or-under the confirmed-safe size and stitch
# them together client-side.
POSTGREST_MAX_PAGE = 1000


def _get_paginated(base_path: str, limit: int, start_offset: int = 0, timeout: float = 10.0):
    """Fetch up to `limit` rows from `base_path` (which must already include
    ?select=...&order=...&<filters> but NOT limit/offset), paginating in chunks
    of <= POSTGREST_MAX_PAGE so no single request ever crosses PostgREST's cap.

    Stops as soon as either `limit` rows have been collected, or a page comes
    back shorter than requested (== end of the corpus) - so a caller asking for
    more rows than exist gets everything without erroring (req. 12), and a
    caller asking for fewer than one page never fetches more than it needs
    (req. 9). Requires the underlying `order=` to be fully deterministic (a
    unique tiebreaker, not just created_at, which is not guaranteed unique) -
    see the callers below for why `id` is used as that tiebreaker."""
    sep = "&" if "?" in base_path else "?"
    out = []
    offset = start_offset
    while len(out) < limit:
        take = min(POSTGREST_MAX_PAGE, limit - len(out))
        page = _get(f"{base_path}{sep}limit={take}&offset={offset}", timeout=timeout)
        if not page:
            break
        out.extend(page)
        offset += len(page)
        if len(page) < take:
            break  # short page - the corpus ran out before `limit` was reached
    return out


def _naive_iso(ts):
    """Supabase (timestamptz) returns offset-aware ISO strings ('...+00:00');
    SQLite's own timestamps (datetime.utcnow().isoformat(), see database.py) are
    naive. _importance()/_feed_rank() (imported from export_static.py, written
    for the naive SQLite value) can't subtract an aware datetime from a naive
    `now` - strip the offset here so both sides parse identically. Everything
    in this system is already UTC either way, so this drops no information."""
    if not ts:
        return ts
    return ts.replace("+00:00", "").replace("Z", "")


def _event_summary_row(e: dict, now: datetime = None) -> dict:
    """Shape one Supabase `events` row to match database._event_summary_row()'s
    output - the same shape /data/events.json already ships, so app.jsx's
    existing card-rendering code needs no changes.

    `lang` and `feed_rank`/`importance` are computed here, live, from fields
    already on the row - never hardcoded, never persisted (see module docstring
    for why the ranking fields must be request-time)."""
    if now is None:
        now = datetime.utcnow()
    lean_counts = {"left": e["lean_left"], "center": e["lean_center"], "right": e["lean_right"]}
    row = {
        "id": e["id"], "title": e["title"], "summary": e["summary"],
        "summary_points": e.get("summary_points") or [],
        "title_hi": e.get("title_hi") or "", "summary_hi": e.get("summary_hi") or "",
        "summary_points_hi": e.get("summary_points_hi") or [],
        "topic": e.get("topic") or "Society", "region": e.get("region") or "India",
        "lang": event_language({"sources": e.get("sources") or []}),
        "image_url": e.get("image_url") or "",
        "is_demo": bool(e.get("is_demo")),
        "source_count": e.get("total_sources", 0),
        "summary_method": e.get("summary_method") or "llm",
        "lean_counts": lean_counts,
        "international": e.get("international_count", 0),
        "dominant": {"side": e["dominant_lean"], "pct": e["dominant_pct"],
                     "total": sum(lean_counts.values())} if e.get("dominant_lean") else None,
        "blindspot": {"side": e["blindspot_side"], "pct": e["blindspot_pct"]} if e.get("blindspot_side") else None,
        "created_at": _naive_iso(e.get("created_at")), "published_at": _naive_iso(e.get("published_at")),
        "storyline_id": e.get("storyline_id"),
    }
    row["importance"] = _importance(row, now)
    row["feed_rank"] = round(_feed_rank(row, now) * _civic_mult(row), 4)
    return row


def get_events(limit: int = 1500) -> dict:
    # order=created_at.desc,id.desc - created_at stays the PRIMARY sort (unchanged public
    # semantics), but created_at is not unique (two events can share a timestamp), so
    # offset-based pagination across multiple requests needs a tiebreaker or a tied row
    # could be skipped or duplicated depending on which page it lands on. `id` is unique,
    # already indexed (primary key), and higher ids are newer events, so ordering by it
    # DESC as the secondary key agrees with the intended "newest first" semantics rather
    # than fighting them.
    # Paksh 2.6: was select=* (17.14MB/1000 rows, measured in the 2.5 investigation -
    # 43% of that was analysis_json alone, a field _event_summary_row() never reads).
    # Narrowed to SUMMARY_ROW_COLUMNS - the exact fields _event_summary_row() actually
    # uses, already proven for get_blindspots() in Phase 2.1. Measured effect on this
    # exact query in 2.5: 17.14MB->7.54MB (-56%), 5.88s->1.89s (-68%) for a single
    # unthrottled request - the anon role's statement_timeout=3s is the reason this
    # matters: unlike get_event()/get_blindspots() reads, this endpoint was still
    # shipping the full row including analysis_json/coverage/framing/framing_hi, none
    # of which _event_summary_row() reads.
    rows = _get_paginated(
        f"/events?select={SUMMARY_ROW_COLUMNS}&is_demo=eq.false&order=created_at.desc,id.desc",
        int(limit),
    )
    now = datetime.utcnow()  # one instant shared across the whole response, so every
                              # event's rank/importance decay is computed consistently
    return {"events": [_lighten(_event_summary_row(e, now)) for e in rows]}


def get_event(event_id: int) -> dict | None:
    rows = _get(f"/events?select=*&id=eq.{int(event_id)}")
    if not rows:
        return None
    e = rows[0]
    out = _event_summary_row(e)
    out.update({
        "coverage": e.get("coverage") or {}, "framing": e.get("framing") or {},
        "framing_hi": e.get("framing_hi") or {}, "sources": e.get("sources") or [],
        "divergence": e.get("analysis_json", {}).get("divergence", ""),
        "omissions": e.get("analysis_json", {}).get("omissions", ""),
    })
    return out


def get_events_archive(limit: int = 3000) -> dict:
    """Phase 1.75: the Supabase equivalent of events-archive.json - events beyond the
    recent RECENT_FEED_N window (the SAME constant export_static.py uses for the
    events.json/archive split, imported rather than duplicated), lightened the same
    way (_lighten, also imported) so archive rows match events.json's payload shape.

    Paksh 2.1: paginated the same way as get_events() (same id.desc tiebreaker,
    same reasoning) - the archive is exactly the corpus most likely to exceed
    PostgREST's 1000-row cap, since it holds everything past the recent window.

    Paksh 2.6: narrowed to SUMMARY_ROW_COLUMNS, same as get_events() above and
    for the same measured reason (analysis_json/coverage/framing were dead
    weight - _lighten() strips summary_points/summary_points_hi afterward
    anyway, so this endpoint needed the full row even less than get_events())."""
    rows = _get_paginated(
        f"/events?select={SUMMARY_ROW_COLUMNS}&is_demo=eq.false&order=created_at.desc,id.desc",
        int(limit), start_offset=int(RECENT_FEED_N),
    )
    now = datetime.utcnow()
    return {"events": [_lighten(_event_summary_row(e, now)) for e in rows]}


def get_storyline(storyline_id: str) -> dict | None:
    """Phase 1.75: single-storyline detail, matching the shape storylines.build_storylines()
    produces (and export_static.py writes to data/storylines/<id>.json) - {..., "events": [...]}.
    The Supabase `storylines` table only holds the lean summary columns (see
    migrate_to_supabase.build_storylines_sql) with no per-event payload, so the events
    array is reconstructed here from `events.storyline_id`, which the sync/migration
    scripts already populate on every event row."""
    rows = _get(f"/storylines?select=*&id=eq.{urllib.parse.quote(str(storyline_id))}")
    if not rows:
        return None
    s = rows[0]
    members = _get(
        f"/events?select=id,title,title_hi,created_at,published_at,topic,"
        f"dominant_lean,dominant_pct,blindspot_side,blindspot_pct,"
        f"lean_left,lean_center,lean_right"
        f"&storyline_id=eq.{urllib.parse.quote(str(storyline_id))}&order=created_at.asc"
    )
    ev_list = []
    for m in members:
        lean_counts = {"left": m["lean_left"], "center": m["lean_center"], "right": m["lean_right"]}
        # same priority as storylines._event_date(): real article publish time first,
        # falling back to pipeline created_at - keeps "date" identical to the SQLite path.
        date = _naive_iso(m.get("published_at")) or _naive_iso(m.get("created_at"))
        ev_list.append({
            "id": m["id"], "title": m["title"], "title_hi": m.get("title_hi", ""),
            "date": date, "topic": m.get("topic"),
            "dominant": {"side": m["dominant_lean"], "pct": m["dominant_pct"],
                         "total": sum(lean_counts.values())} if m.get("dominant_lean") else None,
            "blindspot": {"side": m["blindspot_side"], "pct": m["blindspot_pct"]} if m.get("blindspot_side") else None,
            "lean_counts": lean_counts,
        })
    return {
        "id": s["id"], "title": s["title"], "title_hi": s.get("title_hi", ""),
        "topic": s.get("topic"), "region": s.get("region", "India"),
        "n_events": s.get("n_events", len(ev_list)),
        "start": _naive_iso(s.get("starts_at")), "end": _naive_iso(s.get("ends_at")),
        "updated_at": _naive_iso(s.get("updated_at")),
        "events": ev_list,
    }


def get_topics() -> dict:
    rows = _get("/topics?select=name&order=name.asc")
    return {"topics": [r["name"] for r in rows]}


def get_sources() -> dict:
    rows = _get("/outlets?select=name,domain,owner,lean,label,confidence,contested,"
                "review_status,last_reviewed,region,language,rationale,axes"
                "&is_curated=eq.true&order=name.asc")
    sources = [{
        "id": r["name"], "name": r["name"], "language": r.get("language"),
        "website": ("https://" + r["domain"]) if r.get("domain") else None,
        "ownership": r.get("owner"), "owner": r.get("owner"), "lean": r.get("lean"),
        "label": r.get("label"), "confidence": r.get("confidence"),
        "contested": r.get("contested"), "review_status": r.get("review_status"),
        "last_reviewed": r.get("last_reviewed"),
        "rationale": r.get("rationale"), "axes": r.get("axes"),
    } for r in rows]
    by_lean = {}
    for s in sources:
        by_lean[s["lean"]] = by_lean.get(s["lean"], 0) + 1
    return {"sources": sources, "summary": {"total": len(sources), "by_lean": by_lean}}


def get_stats() -> dict:
    """Paksh 4.3: the Supabase-backed /api/stats - same shape as main.py's
    SQLite-mode stats() (events/articles/sources/blindspots), a drop-in swap
    rather than a new schema. Every figure is a genuine count=exact query
    against the same tables every other Supabase-backed route already reads -
    never hardcoded, never a cached/partial estimate. `sources` counts
    curated (voting) outlets only, matching len(SOURCES) in the SQLite path -
    verified-registry entries never voted there either."""
    return {
        "events": _count("/events?is_demo=eq.false"),
        "articles": _count("/articles"),
        "sources": _count("/outlets?is_curated=eq.true"),
        "blindspots": _count("/events?blindspot_side=not.is.null"),
    }


def get_storylines() -> dict:
    rows = _get("/storylines?select=id,title,title_hi,topic,region,n_events,starts_at,ends_at,updated_at"
                "&order=updated_at.desc")
    return {"storylines": [{
        "id": r["id"], "title": r["title"], "title_hi": r.get("title_hi"),
        "topic": r.get("topic"), "region": r.get("region"), "n_events": r.get("n_events"),
        "start": r.get("starts_at"), "end": r.get("ends_at"), "updated_at": r.get("updated_at"),
    } for r in rows]}


# Paksh 2.1 objective 2: the exact (and only) columns _event_summary_row() reads -
# traced field-by-field from its body. Excludes analysis_json (duplicates the whole
# row), coverage/framing/framing_hi (only needed by the single-event detail view,
# get_event(), which already fetches them separately), degraded, unrated_count, and
# synced_at - none of those are read to build the summary-row shape, so shipping
# them here was pure waste. Named as a constant (not inlined) so any other summary-
# row query - not just blindspots - can reuse the identical minimal projection
# instead of a second, possibly-drifting column list.
SUMMARY_ROW_COLUMNS = (
    "id,title,summary,summary_points,summary_points_hi,title_hi,summary_hi,"
    "topic,region,sources,image_url,is_demo,total_sources,summary_method,"
    "lean_left,lean_center,lean_right,international_count,"
    "dominant_lean,dominant_pct,blindspot_side,blindspot_pct,"
    "created_at,published_at,storyline_id"
)


def get_blindspots() -> dict:
    """Blindspot columns exist on `events` (populated at migration time from
    database.compute_blindspot()) but the LEFT/RIGHT-heavier split JSON shape
    /data/blindspots.json ships is a build-time aggregate export_static.py
    computes, not stored per-row. Reconstructed here from the same rows.

    Paksh 2.1: was `select=*` (pulling analysis_json/coverage/framing for all ~813
    rows - the measured 4.3-7.0s latency, and one HTTP 500, at full scale). Narrowed
    to SUMMARY_ROW_COLUMNS, the same fields _event_summary_row() actually reads -
    same response shape, same _event_summary_row() reuse, just less bytes moved."""
    rows = _get(f"/events?select={SUMMARY_ROW_COLUMNS}&blindspot_side=not.is.null"
                f"&order=created_at.desc,id.desc", timeout=10.0)
    left_heavier, right_heavier = [], []
    for e in rows:
        row = _lighten(_event_summary_row(e))
        row["counts"] = row["lean_counts"]
        (left_heavier if e["blindspot_side"] == "right" else right_heavier).append(row)
    return {"events": left_heavier + right_heavier, "left_heavier": left_heavier,
            "right_heavier": right_heavier,
            "aggregate": {"total": len(rows), "left_heavier": len(left_heavier),
                          "right_heavier": len(right_heavier)}}
