"""
database.py
-----------
All database access lives here. SQLite — a real SQL database in a single file
(paksh.db), zero install. Swap for PostgreSQL when you deploy.

V2 adds: article images, event topics, dominant-lean + Blindspot computation.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "paksh.db"
LEAN_ORDER = ["left", "center", "right"]

# Paksh perf phase 4C: main.py no longer calls init_db() eagerly at startup when
# PAKSH_CONTENT_BACKEND=supabase (that mode never reads SQLite on its happy path).
# This flag guarantees init_db() still runs, exactly once, before any real SQLite
# access - whether that's the SQLite-mode startup call or the first fallback read
# after Supabase fails. get_connection() is the one chokepoint every function in
# this file already goes through, so guarding it here covers every caller without
# needing a change at each fallback call site in main.py.
_db_initialized = False


def get_connection():
    global _db_initialized
    # timeout=30: without a busy-timeout, the moment ANOTHER process holds the write lock
    # (reframe/analyze/live all touch paksh.db), the very next commit raises
    # "database is locked" instantly. This makes a would-be writer WAIT up to 30s instead.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL lets many readers coexist with one writer; busy_timeout backs up the connect
    # timeout; synchronous=NORMAL is safe under WAL and faster. Wrapped because the DB may
    # itself be momentarily locked at connect time - the PRAGMAs then apply on a later call.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass
    if not _db_initialized:
        _db_initialized = True   # set before calling init_db() - it also calls
                                  # get_connection(), so this prevents recursion
        init_db()
    return conn


def has_content() -> bool:
    """Paksh phase 5.1C: cheap, CORRECT check for "does SQLite have real
    content" - a row-existence probe against the raw events table, not an
    inference from an empty get_all_events() result. get_all_events() also
    drops events with fewer than 2 rated outlets, which could legitimately
    zero out its result for a real-but-early corpus; checking the raw table
    directly avoids treating that as "SQLite is empty". LIMIT 1 makes this a
    single-row existence check, not a full-table scan."""
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM events LIMIT 1").fetchone()
    conn.close()
    return row is not None


def init_db():
    """Create tables if missing, and migrate older databases safely."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            language    TEXT NOT NULL,
            title       TEXT NOT NULL,
            url         TEXT NOT NULL UNIQUE,
            summary     TEXT,
            image_url   TEXT,
            published   TEXT,
            fetched_at  TEXT NOT NULL,
            event_id    INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL,
            summary       TEXT,
            divergence    TEXT,
            omissions     TEXT,
            analysis_json TEXT NOT NULL,
            is_demo       INTEGER DEFAULT 0,
            created_at    TEXT NOT NULL
        )
    """)

    # embedding cache: each article's vector, stored once, reused across runs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            key        TEXT PRIMARY KEY,
            vec        BLOB NOT NULL,
            created_at TEXT
        )
    """)

    # --- migrations for users upgrading from an older paksh.db ---
    art_cols = [r["name"] for r in cur.execute("PRAGMA table_info(articles)").fetchall()]
    if "image_url" not in art_cols:
        cur.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")

    # updated_at (Paksh 2.0 Phase 1.5): a genuine "last changed" signal, DISTINCT from
    # created_at. created_at is deliberately preserved across in-place edits (reframe.py,
    # recount_migrate.py both call update_event(..., bump_created=False) specifically so
    # the feed order doesn't reshuffle) - so it cannot answer "what changed since X" and
    # was never meant to. updated_at is set on every insert_event()/update_event() call,
    # unconditionally, and is read by sync_to_supabase.py to find events needing a sync
    # without touching anything else in the pipeline. Backfilled to created_at for
    # existing rows (a safe, conservative default: their first sync run will see them all
    # as "changed since epoch", which is correct - they were never synced before).
    ev_cols = [r["name"] for r in cur.execute("PRAGMA table_info(events)").fetchall()]
    if "updated_at" not in ev_cols:
        cur.execute("ALTER TABLE events ADD COLUMN updated_at TEXT")
        cur.execute("UPDATE events SET updated_at = created_at WHERE updated_at IS NULL")

    # --- indexes (idempotent) ---------------------------------------------------
    # The tables had only their auto UNIQUE indexes (articles.url, embeddings.key), so
    # every pipeline query scanned all ~240k articles. These cover the hot paths:
    #   * get_unclustered_articles: WHERE event_id IS NULL ORDER BY fetched_at DESC.
    #     A PARTIAL index indexes ONLY the unclustered rows (a small, shrinking set) and
    #     already carries them in fetched_at order -> the per-cycle clustering read stops
    #     scanning the whole table. This is the single biggest speedup.
    #   * per-event reads / recount / coverage: WHERE event_id = ?.
    #   * event listing / windows: ORDER BY created_at.
    #   * embedding-cache pruning: WHERE created_at < ? (see prune_cache.py).
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_unclustered "
                "ON articles(fetched_at) WHERE event_id IS NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_event_id ON articles(event_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_updated_at ON events(updated_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at)")

    conn.commit()
    conn.close()


# ---------- Embedding cache ----------

def _ensure_embeddings(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS embeddings (
        key TEXT PRIMARY KEY, vec BLOB NOT NULL, created_at TEXT)""")


def embeddings_get(keys):
    """Return {key: raw_bytes} for the keys already cached (missing keys omitted)."""
    if not keys:
        return {}
    conn = get_connection()
    _ensure_embeddings(conn)
    out = {}
    CH = 400  # keep the IN (...) list within SQLite's parameter limit
    for i in range(0, len(keys), CH):
        chunk = keys[i:i + CH]
        ph = ",".join("?" for _ in chunk)
        for r in conn.execute(f"SELECT key, vec FROM embeddings WHERE key IN ({ph})", chunk):
            out[r["key"]] = bytes(r["vec"])
    conn.close()
    return out


def embeddings_put(items):
    """Store {key: raw_bytes} embeddings (insert or replace)."""
    if not items:
        return
    conn = get_connection()
    _ensure_embeddings(conn)
    now = datetime.utcnow().isoformat()
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings (key, vec, created_at) VALUES (?, ?, ?)",
        [(k, v, now) for k, v in items.items()],
    )
    conn.commit()
    conn.close()


# ---------- Articles ----------

def insert_article(source, language, title, url, summary, image_url, published):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO articles (source, language, title, url, summary, image_url, published, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, language, title, url, summary, image_url, published, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_unclustered_articles(limit=3000, per_source=60, rated_first=True):
    """Return un-grouped articles, BALANCED across outlets, RATED sources first.

    A naive 'most recent N' lets a prolific outlet flood the window, so we take
    each outlet's most-recent `per_source` articles. On top of that, RATED
    outlets (registry sources, plus GDELT articles that resolved to one) get
    their quota BEFORE any unrated long-tail fills the remaining capacity.
    Without this, a GDELT flood of unrated domains — much heavier in English than
    Hindi — crowds rated articles out of the window and their events stop forming
    (which is exactly how the English feed went stale while Hindi kept working).
    """
    import sources
    sources._load_verified_registry()   # perf phase 4A: registry is lazy now - see sources.py
    from sources import LEAN_BY_SOURCE
    conn = get_connection()
    # ~60% of articles sit unclustered, so ORDER BY fetched_at over that set is the pipeline's
    # hottest read. INDEXED BY forces the PARTIAL index (fetched_at, WHERE event_id IS NULL),
    # which is already in fetched_at order -> no temp-B-tree sort of 100k+ rows (measured
    # 358ms -> ~1ms). We force it because the planner otherwise picks the plain event_id index
    # and re-sorts. init_db() always creates this index, so INDEXED BY can't fail to find it.
    rows = conn.execute(
        """SELECT id, source, language, title, summary
           FROM articles INDEXED BY idx_articles_unclustered
           WHERE event_id IS NULL
           ORDER BY fetched_at DESC"""
    ).fetchall()
    conn.close()

    def _take(candidates, cap_total):
        by_source, picked = {}, []
        for r in candidates:
            if len(picked) >= cap_total:
                break
            s = r["source"]
            if by_source.get(s, 0) >= per_source:
                continue
            by_source[s] = by_source.get(s, 0) + 1
            picked.append(dict(r))
        return picked

    if not rated_first:
        return _take(rows, limit)

    rated = [r for r in rows if r["source"] in LEAN_BY_SOURCE]
    unrated = [r for r in rows if r["source"] not in LEAN_BY_SOURCE]
    out = _take(rated, limit)                       # rated get first claim
    out += _take(unrated, limit - len(out))         # unrated fill the remainder
    return out


def get_articles_by_ids(ids):
    if not ids:
        return []
    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""SELECT id, source, language, title, url, summary, image_url, published
            FROM articles WHERE id IN ({placeholders})""",
        ids,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


_JUNK_TITLE_RE = __import__("re").compile(
    r"(diverse\s+local\s+news|diverse\s+\w+\s+news\s+topics|news\s+bulletins?\b|"
    r"bulletins?\s+and\s+updates|various\s+editions|newspapers?\s+publish|"
    r"publish\s+various|topics\s+reported|round[\s-]?up\b|coverage\s+overview|"
    r"video\s+gallery|premarket\s+movers|calendar\s+events|astrological|"
    r"share\s+price\b)", __import__("re").I)


def get_recent_events_for_merge(days=5, limit=400):
    """READ-ONLY. Recent non-demo events with their member articles, for cross-cycle
    merge matching. Returns [{event_id, created_at, title, topic, source_count,
    articles:[{title, summary, language, source}]}]."""
    import json
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = get_connection()
    erows = conn.execute(
        "SELECT id, title, analysis_json, created_at FROM events "
        "WHERE created_at >= ? AND COALESCE(is_demo, 0) = 0 "
        "ORDER BY created_at DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()
    out = []
    for e in erows:
        arts = conn.execute(
            "SELECT title, summary, language, source FROM articles WHERE event_id = ?",
            (e["id"],),
        ).fetchall()
        if not arts:
            continue
        if _JUNK_TITLE_RE.search(e["title"] or ""):
            continue   # publisher roundup / bulletin / edition dump - not a real event
        try:
            _aj = json.loads(e["analysis_json"])
            topic = _aj.get("topic")
            smethod = _aj.get("summary_method", "llm")
        except Exception:
            topic, smethod = None, "llm"
        out.append({
            "event_id": e["id"], "created_at": e["created_at"], "title": e["title"],
            "topic": topic, "summary_method": smethod,
            "source_count": len({a["source"] for a in arts}),
            "articles": [dict(a) for a in arts],
        })
    conn.close()
    return out


def release_event_articles(event_id):
    """Paksh 2.2: the function cleanup.py --recycle has always called but that
    never existed (a real, pre-existing bug - see the 2.0B audit). Sets
    event_id = NULL for every article currently belonging to `event_id`, so a
    subsequent delete_event(event_id) leaves no article pointing at a deleted
    row (the ON DELETE behavior consolidate.py relies on by reassigning to a
    survivor first; cleanup.py has no survivor to reassign to - a grab-bag/dump/
    generic event isn't one real story - so freeing to NULL, to be picked up by
    a future cluster.py run, is the correct alternative, matching this
    function's own name and cleanup.py's --recycle docstring).

    Never deletes rows, never touches title/url/summary/source/any article
    content - only the event_id foreign key. Returns the number of articles
    released so the caller can report and verify it (required by the 2.2 brief).
    A single UPDATE is atomic in SQLite - conn.commit() finalizes it; no
    partial-release state is reachable if it fails, since nothing commits."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE articles SET event_id = NULL WHERE event_id = ?", (event_id,)
    )
    released = cur.rowcount
    conn.commit()
    conn.close()
    return released


def delete_event(event_id):
    """Remove an event row. Used by consolidation AFTER its articles have been
    reassigned to the surviving event - so no article is left orphaned."""
    conn = get_connection()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def get_event_articles(event_id):
    """All member articles of an event (for recount after a cross-cycle merge)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, source, language, title, url, summary, image_url "
        "FROM articles WHERE event_id = ?", (event_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_articles_for_events(event_ids):
    """Batched form of get_event_articles: {event_id: [articles]} for MANY events in
    one connection, chunked IN (...) queries - the same shape as embeddings_get(), used
    where a caller would otherwise call get_event_articles() once per event in a loop
    (e.g. storylines.py's _centroids(), which used to open one connection per event).
    Every id in event_ids gets an entry (possibly []), so callers never need a
    membership check for a zero-article event. Row shape and column set are identical
    to get_event_articles(); only how they're fetched differs."""
    event_ids = list(event_ids)
    out = {eid: [] for eid in event_ids}
    if not event_ids:
        return out
    conn = get_connection()
    CH = 400  # keep the IN (...) list within SQLite's parameter limit
    cols = ("id", "source", "language", "title", "url", "summary", "image_url")
    for i in range(0, len(event_ids), CH):
        chunk = event_ids[i:i + CH]
        ph = ",".join("?" for _ in chunk)
        for r in conn.execute(
                f"SELECT event_id, {', '.join(cols)} FROM articles WHERE event_id IN ({ph})", chunk):
            out[r["event_id"]].append({k: r[k] for k in cols})
    conn.close()
    return out


def update_event(event_id, analysis, bump_created=True):
    """Rewrite an event's stored analysis after its membership changed. bump_created
    refreshes created_at so a continuing story resurfaces as recently-updated.
    updated_at is ALWAYS refreshed, independent of bump_created - it is the one
    reliable "this event genuinely changed" signal (see init_db()'s docstring for
    the column), read by sync_to_supabase.py. Callers like reframe.py/
    recount_migrate.py that intentionally keep created_at stable (bump_created=False)
    still need updated_at to move, or a content fix would never get synced."""
    conn = get_connection()
    sets = ["title = ?", "summary = ?", "analysis_json = ?", "updated_at = ?"]
    params = [analysis.get("title", "Untitled event"), analysis.get("summary", ""),
              json.dumps(analysis, ensure_ascii=False), datetime.utcnow().isoformat()]
    if bump_created:
        sets.append("created_at = ?")
        params.append(datetime.utcnow().isoformat())
    params.append(event_id)
    conn.execute("UPDATE events SET %s WHERE id = ?" % ", ".join(sets), params)
    conn.commit()
    conn.close()


def assign_articles_to_event(article_ids, event_id):
    if not article_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" for _ in article_ids)
    conn.execute(
        f"UPDATE articles SET event_id = ? WHERE id IN ({placeholders})",
        [event_id, *article_ids],
    )
    conn.commit()
    conn.close()


def count_articles():
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    conn.close()
    return n


# ---------- Lean maths (shared) ----------

def lean_counts_from(data):
    cov = data.get("coverage", {})
    return {s: cov.get(s, {}).get("count", 0) for s in LEAN_ORDER}


def event_language(data):
    """Majority language of an event's sources ('en'/'hi'). Ties prefer English.
    Used so the site can show English-sourced and Hindi-sourced stories separately."""
    from collections import Counter
    langs = [s.get("language", "en") for s in data.get("sources", [])]
    if not langs:
        return "en"
    counts = Counter(langs)
    return max(counts.items(), key=lambda kv: (kv[1], kv[0] == "en"))[0]


def dominant_lean(counts):
    """The side with the most coverage + its percentage. For the card callout."""
    total = sum(counts.values())
    if total == 0:
        return None
    side = max(LEAN_ORDER, key=lambda s: counts[s])
    return {"side": side, "pct": round(counts[side] / total * 100), "total": total}


def compute_blindspot(counts):
    """
    A Blindspot = a partisan asymmetry: one political wing covers the story
    while the OPPOSITE wing stays almost entirely away. Centre-only stories are
    'thinly covered', not blindspots, so they no longer qualify (this is what
    used to flag ~80% of events).

    All of these must hold:
      - 4+ total sources            -> a real, multi-outlet story
      - the covering wing is >=40%  AND has >=2 distinct outlets
      - the opposite wing is <=15%  (effectively absent)
    Returns {side, pct} where `side` is the under-covering (blindspot) wing.
    """
    total = sum(counts.values())
    if total < 4:
        return None
    left, right = counts.get("left", 0), counts.get("right", 0)
    lpct, rpct = left / total, right / total
    LOW, PRESENT = 0.15, 0.40
    # right (and/or centre) cover it, the left is absent -> Left blindspot
    if lpct <= LOW and rpct >= PRESENT and right >= 2:
        return {"side": "left", "pct": round(lpct * 100)}
    # left (and/or centre) cover it, the right is absent -> Right blindspot
    if rpct <= LOW and lpct >= PRESENT and left >= 2:
        return {"side": "right", "pct": round(rpct * 100)}
    return None


# ---------- Events ----------

def insert_event(analysis: dict, is_demo: bool = False, created_at: str = None):
    """Insert a new event. created_at defaults to NOW (live pipeline); a backfill run
    over OLD articles passes the article's real publish date so it doesn't jump to the
    top of the created_at-DESC homepage as if it were fresh."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        """INSERT INTO events (title, summary, divergence, omissions, analysis_json, is_demo, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            analysis.get("title", "Untitled event"),
            analysis.get("summary", ""),
            analysis.get("divergence", ""),
            analysis.get("omissions", ""),
            json.dumps(analysis, ensure_ascii=False),
            1 if is_demo else 0,
            created_at or now,
            now,  # updated_at is always the real wall-clock time, unlike created_at above
        ),
    )
    conn.commit()
    event_id = cur.lastrowid
    conn.close()
    return event_id


def _event_summary_row(r):
    """Shared shaping for list + blindspot feeds."""
    data = json.loads(r["analysis_json"])
    counts = lean_counts_from(data)
    region = data.get("region")
    if region not in ("India", "World"):           # back-fill old events
        region = "World" if data.get("topic") == "International" else "India"
    return {
        "id": r["id"],
        "title": r["title"],
        "summary": r["summary"],
        "summary_points": data.get("summary_points", []),
        "title_hi": data.get("title_hi", ""),
        "summary_hi": data.get("summary_hi", ""),
        "summary_points_hi": data.get("summary_points_hi", []),
        "topic": data.get("topic", "General"),
        "region": region,
        "lang": event_language(data),
        "image_url": data.get("image_url", ""),
        "is_demo": bool(r["is_demo"]),
        "source_count": len(data.get("sources", [])),
        "summary_method": data.get("summary_method", "llm"),
        # Paksh 7B: publication-completeness flag (see analyze.py::compute_content_complete).
        # None means the event predates this field - see _is_publishable() below.
        "content_complete": data.get("content_complete"),
        "lean_counts": counts,
        "international": data.get("coverage", {}).get("international", {}).get("count", 0),
        "dominant": dominant_lean(counts),
        "blindspot": compute_blindspot(counts),
        "created_at": r["created_at"],
        # Real article publish time (newest member article). The feed shows THIS as "x ago";
        # created_at stays the pipeline touch-time used for internal recency math. None for
        # events analysed before this field existed -> the UI falls back to created_at.
        "published_at": data.get("published_at"),
    }


# Paksh 7B: the publication-completeness gate. content_complete is written by
# analyze.py::postprocess() going forward; an event with NO such key (every event
# generated before this field existed) is grandfathered - it was never evaluated by
# this rule and stays visible unless/until it's naturally re-analysed (backfill.py/
# reframe.py/recount_migrate.py), at which point postprocess() writes a real value.
# Only an EXPLICIT False hides an event. This is the one place the predicate is
# read from a stored value - the CALCULATION lives only in compute_content_complete().
def _is_publishable(e: dict) -> bool:
    return e.get("content_complete") is not False


def get_all_events(include_incomplete: bool = False):
    """include_incomplete=True is for INTERNAL repair tooling only (reframe.py's own
    candidate discovery) - it must still see newly-incomplete events to find and fix
    them. Every public-facing caller (main.py's routes, export_static.py) uses the
    default False and never sees a non-grandfathered incomplete event."""
    if not has_content():
        # Paksh phase 5.1: SQLite has no usable content (e.g. a fresh Render
        # deploy with no paksh.db - see the Phase 5.1 report). Fall back to
        # the committed static snapshot rather than silently returning an
        # empty, apparently-healthy result. Read-only: never writes back into
        # SQLite, never treated as a new source of truth.
        import static_fallback
        snapshot = static_fallback.get_events()
        out = snapshot["events"] if snapshot else []
        return out if include_incomplete else [e for e in out if _is_publishable(e)]
    conn = get_connection()
    rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    conn.close()
    out = [_event_summary_row(r) for r in rows]
    # Hide events that lack a real bias comparison (<2 rated outlets) -- e.g.
    # all-unrated GDELT/syndication events saved before the rated-gate existed.
    # Non-destructive: rows stay in the DB, they're just not published.
    out = [e for e in out if sum(e["lean_counts"].values()) >= 2]
    if include_incomplete:
        return out
    return [e for e in out if _is_publishable(e)]


def get_blindspot_events():
    """Only events where one side is barely covering the story."""
    return [e for e in get_all_events() if e["blindspot"]]


def get_topics():
    """Distinct topics present, for the filter bar."""
    seen = []
    for e in get_all_events():
        if e["topic"] not in seen:
            seen.append(e["topic"])
    return seen


def get_event_ids(days=None):
    """All non-demo event ids, newest first; optionally only the last `days`."""
    conn = get_connection()
    q = "SELECT id FROM events WHERE COALESCE(is_demo, 0) = 0"
    params = []
    if days:
        from datetime import datetime, timedelta
        q += " AND created_at >= ?"
        params.append((datetime.utcnow() - timedelta(days=days)).isoformat())
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [r["id"] for r in rows]


def get_event_ids_updated_since(since_iso: str):
    """Non-demo event ids with updated_at >= since_iso (oldest first, so a sync
    that gets interrupted partway can resume from the last id it completed).
    This is the real "what changed" query for sync_to_supabase.py - unlike
    get_event_ids(days=...) above, it is NOT fooled by reframe.py/
    recount_migrate.py's bump_created=False (see update_event()'s docstring)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM events WHERE COALESCE(is_demo, 0) = 0 AND updated_at >= ? "
        "ORDER BY updated_at ASC",
        (since_iso,),
    ).fetchall()
    conn.close()
    return [r["id"] for r in rows]


def get_event(event_id):
    if not has_content():
        # Paksh phase 5.1: only reached when SQLite as a whole has no usable
        # content - a genuine per-id miss against a POPULATED database still
        # falls through to `if not r: return None` below (a real 404), not
        # here. Read-only, never written back into SQLite.
        import static_fallback
        return static_fallback.get_event(event_id)
    conn = get_connection()
    r = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    if not r:
        return None
    data = json.loads(r["analysis_json"])
    counts = lean_counts_from(data)
    data["id"] = r["id"]
    data["is_demo"] = bool(r["is_demo"])
    data["created_at"] = r["created_at"]
    data["lean_counts"] = counts
    data["lang"] = event_language(data)
    data["dominant"] = dominant_lean(counts)
    data["blindspot"] = compute_blindspot(counts)
    return data


# Paksh 6B: SQLite-backed fallback for GET /api/search, reached when Supabase is
# unavailable (see main.py's /api/search route) or CONTENT_BACKEND=="sqlite".
# Same normalization contract as supabase_content.search_events() (Phase 6A):
# strip/collapse whitespace, cap query length, cap token count, clamp limit.
# Redeclared here (not imported) because supabase_content.py already imports
# FROM this module (event_language) - importing back would be circular. Values
# must be kept in sync by hand with supabase_content.py's Phase 6A constants.
MAX_SEARCH_QUERY_LEN = 200
MAX_SEARCH_TOKENS = 8
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50


def _like_escape(s: str) -> str:
    """Escape a search token's own literal backslash/%/_ so it is matched as
    literal text inside a LIKE pattern, not interpreted as a wildcard - order
    matters (backslash first, or escaping % / _ would introduce a fresh,
    un-escaped backslash). Same technique as the Postgres search_events()
    migration (fix_search_events_escape_wildcards), applied here because SQLite's
    LIKE has the identical wildcard-injection concern, not because of a shared
    performance problem - SQLite has no trigram index either way, so every
    search here is already a full scan (see the Phase 6B report)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_events(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> dict:
    """Paksh 6B: full-corpus search across events.title/summary (real columns)
    and title_hi/summary_hi (inside analysis_json - see _event_summary_row()
    above; SQLite's JSON1 extension, confirmed present in this environment,
    lets json_extract() reach them in the same parameterized WHERE clause as
    the two real columns). Reads the whole `events` table directly - NOT
    get_all_events()'s already-materialized list, and NOT limited to any
    recent-feed window - so an old event far outside the 1,500/3,000-row
    windows main.py's other routes use is still reachable here.

    Matching: token-AND (every token must appear in at least one of the four
    fields, mirroring both Phase 6A and the existing client-side search's
    qTokens.every(...) semantics), via parameterized SQL LIKE - every
    user-controlled value goes through a `?` placeholder, never string-
    interpolated into the SQL text. No SQLite FTS5 - this is a fallback tier
    over a ~13.7k-row table, not a new search engine.

    Ranking (simple, deterministic, no invented scoring formula): 1) the full
    query string appears verbatim in the title, 2) every token appears in the
    title, 3) every token appears in the summary, 4) matched only via
    title_hi/summary_hi. Within each tier, SQL's own `ORDER BY created_at DESC`
    is preserved as the tiebreak (Python's sort is stable, so re-sorting only
    by score keeps that relative order) - reusing the existing recency
    convention rather than inventing a new one.

    Applies the same "<2 rated outlets" content-quality gate get_all_events()
    already applies (a quality filter, not a feed-window limit - the brief
    asks to keep this, not drop it). storyline_id is always None here: SQLite
    mode has no per-row storyline_id column (real events built via
    _event_summary_row() never carry one either - see /api/blindspots in
    SQLite mode); attaching one would mean running build_storylines() (a real
    clustering-adjacent computation) on every search request, which is out of
    scope for a degraded fallback tier."""
    q = " ".join((query or "").split())
    if not q:
        return {"query": "", "count": 0, "limit": int(limit), "results": []}
    if len(q) > MAX_SEARCH_QUERY_LEN:
        q = q[:MAX_SEARCH_QUERY_LEN].rstrip()
    lim = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    tokens = [t for t in q.split(" ") if t][:MAX_SEARCH_TOKENS]
    if not tokens:
        return {"query": q, "count": 0, "limit": lim, "results": []}
    if not has_content():
        # Paksh 6C: same fallback shape get_all_events()/get_event() already use -
        # SQLite has no usable content, so fall through to the static snapshot's
        # own search (full corpus: events.json + events-archive.json together, NOT
        # just the recent window - see static_fallback.search_events()'s docstring).
        # static_fallback functions never raise; a None here means the snapshot
        # itself is unavailable/malformed, so fall through to the same
        # empty-but-200 shape this function already returns in every other
        # empty case - never a 500, never a fabricated result.
        import static_fallback
        snapshot = static_fallback.search_events(q, lim)
        return snapshot if snapshot is not None else {"query": q, "count": 0, "limit": lim, "results": []}

    where_clauses = []
    params = []
    for tok in tokens:
        pattern = "%" + _like_escape(tok) + "%"
        where_clauses.append(
            "(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' "
            "OR json_extract(analysis_json,'$.title_hi') LIKE ? ESCAPE '\\' "
            "OR json_extract(analysis_json,'$.summary_hi') LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, pattern, pattern])
    sql = (
        "SELECT * FROM events WHERE COALESCE(is_demo,0)=0 AND "
        + " AND ".join(where_clauses)
        + " ORDER BY created_at DESC"
    )
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    q_lower = q.lower()
    tok_lower = [t.lower() for t in tokens]
    scored = []
    for r in rows:
        e = _event_summary_row(r)
        if sum(e["lean_counts"].values()) < 2:
            continue  # same content-quality gate get_all_events() applies
        if not _is_publishable(e):
            continue  # Paksh 7B: same publication-completeness gate get_all_events() applies
        title_l = (e["title"] or "").lower()
        summary_l = (e["summary"] or "").lower()
        if q_lower in title_l:
            score = 3
        elif all(t in title_l for t in tok_lower):
            score = 2
        elif all(t in summary_l for t in tok_lower):
            score = 1
        else:
            score = 0   # matched only via title_hi/summary_hi
        scored.append((score, e))
    scored.sort(key=lambda pair: -pair[0])   # stable sort: preserves the SQL
                                              # created_at-DESC order within a tier

    from export_static import _snippet   # local import: export_static.py imports
                                          # FROM database.py at module level, so a
                                          # module-level import here would be circular
                                          # (same reasoning as the static_fallback
                                          # imports elsewhere in this file)
    results = []
    for _score, e in scored[:lim]:
        results.append({
            "id": e["id"], "title": e["title"] or "", "title_hi": e["title_hi"] or "",
            "summary": _snippet(e["summary"]), "summary_hi": _snippet(e["summary_hi"]),
            "topic": e["topic"], "lean_counts": e["lean_counts"],
            "sources": sum(e["lean_counts"].values()), "storyline_id": None,
            "created_at": e["created_at"], "published_at": e.get("published_at"),
        })
    return {"query": q, "count": len(results), "limit": lim, "results": results}