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

    # Phase 40D-A: reframe attempt/failure bookkeeping, internal to the reframe
    # pipeline only - see get_reframe_meta()/record_reframe_attempt() below. Nullable,
    # no backfill needed (NULL simply means "no attempt recorded by this mechanism
    # yet", true for every pre-existing row and a safe default). Deliberately NOT
    # exposed via get_event()/get_events_by_ids() (which feed the public per-story
    # JSON export) - kept as a separate narrow query so this can never leak into
    # /data/events/<id>.json.
    if "reframe_last_attempt_at" not in ev_cols:
        cur.execute("ALTER TABLE events ADD COLUMN reframe_last_attempt_at TEXT")
    if "reframe_last_failure_class" not in ev_cols:
        cur.execute("ALTER TABLE events ADD COLUMN reframe_last_failure_class TEXT")

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


WINDOW_TAIL_SHARE = 0.10   # share of the window reserved for vetted (registry) outlets that carry no vote


def _fair_take(candidates, cap_total, per_source):
    """Pick up to `cap_total` rows from `candidates` (given newest-first) so that every
    outlet gets an EQUAL share, instead of the newest rows winning regardless of outlet.

    Round-robin by recency rank: round 0 takes each outlet's newest row, round 1 its
    second newest, and so on (at most `per_source` rounds). Inside a round, outlets are
    ordered by how recent that round's row is, so when the cap lands mid-round the
    fresher rows win. Each outlet's own picks stay newest-first, and the result is
    returned in the input (newest-first) order.

    Why: the old take ('newest N rows, <= per_source per outlet') was decided by
    `fetched_at`, and ingest runs outlets one after another, so the outlets ingested
    LAST always carried the newest timestamps and filled the window. Measured on the
    live DB (docs/SOURCE_UTILIZATION_AUDIT.md): outlets early in the registry reached
    clustering 32% of the time against 87% for the last ones, every run hit the cap.
    Pure function - no DB access - so it is unit-testable."""
    by_src = {}
    for pos, r in enumerate(candidates):
        s = r["source"]
        lst = by_src.setdefault(s, [])
        if len(lst) < per_source:
            lst.append((pos, r))
    picked, rank = [], 0
    live = list(by_src.values())
    while live and len(picked) < cap_total:
        layer = sorted((lst[rank] for lst in live if len(lst) > rank), key=lambda pr: pr[0])
        for pos, r in layer:
            if len(picked) >= cap_total:
                break
            picked.append((pos, r))
        rank += 1
        live = [lst for lst in live if len(lst) > rank]
    picked.sort(key=lambda pr: pr[0])
    return [dict(r) for _, r in picked]


WINDOW_MAX_AGE_HOURS = 72   # older un-grouped rows never enter the window (see select_unclustered_window)


def select_unclustered_window(rows, limit=3000, per_source=60, rated_first=True,
                              is_rated=None, is_vetted=None, tail_share=WINDOW_TAIL_SHARE,
                              max_age_hours=WINDOW_MAX_AGE_HOURS, now=None):
    """The window of un-grouped articles handed to clustering (pure; `rows` newest-first).

    Order of claims: RATED outlets first (they can form events), then a bounded reserve
    for VETTED outlets that carry no vote (the editor-verified foreign registry - they add
    regional breadth and can never create an event on their own), then whatever is left to
    unknown long-tail domains. Inside every tier the allocation is per-outlet fair
    (see _fair_take).

    Recency bound: fair sharing would otherwise hand an outlet whose newest rows are days old
    its full quota of STALE rows (the old 'newest N' cut-off excluded them implicitly). Rows whose
    `fetched_at` is older than `max_age_hours` are dropped, so old news can never form a 'new'
    event stamped as fresh. Rows without a `fetched_at` are kept (nothing to judge)."""
    if max_age_hours:
        from datetime import datetime, timedelta
        cutoff = ((now or datetime.utcnow()) - timedelta(hours=max_age_hours)).isoformat()

        def _fetched(r):
            # rows are plain dicts in tests but sqlite3.Row in production (no .get, and a missing
            # column raises IndexError, not KeyError) - a dict-only test once hid exactly this
            try:
                return r["fetched_at"]
            except (KeyError, IndexError):
                return None
        rows = [r for r in rows if not _fetched(r) or _fetched(r) >= cutoff]
    if not rated_first:
        return _fair_take(rows, limit, per_source)
    is_rated = is_rated or (lambda s: False)
    is_vetted = is_vetted or (lambda s: False)
    rated = [r for r in rows if is_rated(r["source"])]
    vetted = [r for r in rows if not is_rated(r["source"]) and is_vetted(r["source"])]
    other = [r for r in rows if not is_rated(r["source"]) and not is_vetted(r["source"])]
    # The reserve is only held back for vetted rows that actually exist: an unused reserve goes
    # back to the RATED outlets first (as before), never to unknown domains.
    v_res = _fair_take(vetted, int(limit * tail_share), per_source)
    out = _fair_take(rated, limit - len(v_res), per_source)              # rated get first claim
    slack = limit - len(out) - len(v_res)
    v = _fair_take(vetted, len(v_res) + slack, per_source) if slack > 0 else v_res   # vetted reserve (+ slack rated left)
    out += v
    out += _fair_take(other, limit - len(out), per_source)               # unknown domains fill only what is left
    return out


def get_unclustered_articles(limit=3000, per_source=60, rated_first=True):
    """Return un-grouped articles, BALANCED across outlets, RATED sources first.

    A naive 'most recent N' lets a prolific outlet flood the window, and so does 'newest N
    with a per-outlet cap' (the cap only bites the biggest outlets; the cut-off still falls on
    whoever was ingested last). So every tier is filled per-outlet fair - see _fair_take and
    select_unclustered_window. RATED outlets (registry sources, plus GDELT articles that
    resolved to one) still get their quota BEFORE any unrated long-tail fills the remaining
    capacity. Without that, a GDELT flood of unrated domains - much heavier in English than
    Hindi - crowds rated articles out of the window and their events stop forming (which is
    exactly how the English feed went stale while Hindi kept working).
    """
    import sources
    sources._load_verified_registry()   # perf phase 4A: registry is lazy now - see sources.py
    from sources import LEAN_BY_SOURCE, VERIFIED_BY_NAME
    conn = get_connection()
    # ~60% of articles sit unclustered, so ORDER BY fetched_at over that set is the pipeline's
    # hottest read. INDEXED BY forces the PARTIAL index (fetched_at, WHERE event_id IS NULL),
    # which is already in fetched_at order -> no temp-B-tree sort of 100k+ rows (measured
    # 358ms -> ~1ms). We force it because the planner otherwise picks the plain event_id index
    # and re-sorts. init_db() always creates this index, so INDEXED BY can't fail to find it.
    # The recency bound is pushed into the query too (a range scan on the same partial index), so a
    # 400k-row backlog is never even loaded; select_unclustered_window re-applies it (pure/testable).
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=WINDOW_MAX_AGE_HOURS)).isoformat()
    rows = conn.execute(
        """SELECT id, source, language, title, summary, fetched_at
           FROM articles INDEXED BY idx_articles_unclustered
           WHERE event_id IS NULL AND fetched_at >= ?
           ORDER BY fetched_at DESC""", (cutoff,)
    ).fetchall()
    conn.close()
    return select_unclustered_window(
        rows, limit=limit, per_source=per_source, rated_first=rated_first,
        is_rated=lambda s: s in LEAN_BY_SOURCE, is_vetted=lambda s: s in VERIFIED_BY_NAME)


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
    merge matching. Returns [{event_id, created_at, title, topic, region, source_count,
    articles:[{title, summary, language, source}]}].

    Paksh 10: region added alongside the existing topic extraction, for the
    cross-cycle merge topic-guard in analyze.py::_merge_into_existing() - both are
    read-only lookups of the event's OWN already-stored classification, never
    computed here."""
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
            region = _aj.get("region")
            smethod = _aj.get("summary_method", "llm")
        except Exception:
            topic, region, smethod = None, None, "llm"
        out.append({
            "event_id": e["id"], "created_at": e["created_at"], "title": e["title"],
            "topic": topic, "region": region, "summary_method": smethod,
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


def get_reframe_meta(event_ids):
    """Phase 40D-A: {id: {"last_attempt_at": str|None, "last_failure_class": str|None}}
    for reframe.py's OWN candidate-ranking use only. Deliberately separate from
    get_event()/get_events_by_ids() - those feed export_static.py's public per-story
    JSON output, and this bookkeeping (when a candidate last failed, and why) must
    never appear there. Every id gets an entry (None/None for a row with no recorded
    attempt yet), same no-membership-check contract as get_events_by_ids()."""
    event_ids = list(event_ids)
    out = {eid: {"last_attempt_at": None, "last_failure_class": None} for eid in event_ids}
    if not event_ids:
        return out
    conn = get_connection()
    CH = 400
    for i in range(0, len(event_ids), CH):
        chunk = event_ids[i:i + CH]
        ph = ",".join("?" for _ in chunk)
        for r in conn.execute(
            f"SELECT id, reframe_last_attempt_at, reframe_last_failure_class "
            f"FROM events WHERE id IN ({ph})", chunk
        ):
            out[r["id"]] = {"last_attempt_at": r["reframe_last_attempt_at"],
                             "last_failure_class": r["reframe_last_failure_class"]}
    conn.close()
    return out


def record_reframe_attempt(event_id, failure_class=None):
    """Phase 40D-A: record the outcome of one reframe.py attempt against event_id.
    Touches ONLY the two reframe_* bookkeeping columns - never analysis_json, title,
    summary, framing, content_complete, created_at, or updated_at, so this can never
    affect what a reader sees or the event's publication status. failure_class is one
    of reframe.py's own category strings, or None on a successful repair (clearing
    any previously-recorded failure, so a later-recovered event isn't still treated
    as failing by the ranking in _rank_key())."""
    conn = get_connection()
    conn.execute(
        "UPDATE events SET reframe_last_attempt_at = ?, reframe_last_failure_class = ? "
        "WHERE id = ?",
        (datetime.utcnow().isoformat(), failure_class, event_id),
    )
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
    # Phase 40B: demo/fixture events (seed_demo.py, is_demo=1) must never reach the
    # public export/sitemap - they're dev-only preview data, indistinguishable from
    # real news once published. Every OTHER read path in this file already filters
    # is_demo (see the WHERE clauses below); this was the one gap, since
    # get_all_events() queries every column directly instead of through one of those.
    # Non-destructive: rows stay in the DB, only hidden from this read path.
    out = [e for e in out if not e["is_demo"]]
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


def get_events_by_ids(event_ids) -> dict:
    """Batched form of get_event(): {id: event_dict_or_None} for MANY ids in one
    connection, chunked IN (...) queries - same pattern as get_articles_for_events()
    above, used where a caller would otherwise call get_event() once per id in a
    loop (Phase 7B F3: reframe.py::_collect() used to do exactly that across the
    whole catalog - measured at ~30ms/call, dominated by json.loads() of the full
    analysis_json blob plus the same derived-field computation done below, not by
    connection overhead alone; batching into one connection removes the per-call
    connect/close cost entirely). Every id in event_ids gets an entry - None for a
    genuine miss - so callers never need a membership check, matching get_event()'s
    own "not found -> None" contract exactly.

    Produces the SAME fields, in the SAME way, as get_event() per row (json.loads
    of analysis_json, then id/is_demo/created_at/lean_counts/lang/dominant/blindspot)
    - deliberately not a new shape. No demo filtering here, exactly like get_event()
    itself (callers that need is_demo=0 filtering already do it themselves, e.g. via
    get_all_events()).

    Falls through to get_event() per id (which itself falls through to
    static_fallback.get_event()) when SQLite has no usable content - the same rare
    empty-database condition get_event() already handles; not worth a bulk fast
    path since it only matters when the corpus is small/absent, never the case
    this function exists to speed up."""
    event_ids = list(event_ids)
    if not has_content():
        return {eid: get_event(eid) for eid in event_ids}
    out = {eid: None for eid in event_ids}
    if not event_ids:
        return out
    conn = get_connection()
    CH = 400  # keep the IN (...) list within SQLite's parameter limit
    for i in range(0, len(event_ids), CH):
        chunk = event_ids[i:i + CH]
        ph = ",".join("?" for _ in chunk)
        for r in conn.execute(f"SELECT * FROM events WHERE id IN ({ph})", chunk):
            data = json.loads(r["analysis_json"])
            counts = lean_counts_from(data)
            data["id"] = r["id"]
            data["is_demo"] = bool(r["is_demo"])
            data["created_at"] = r["created_at"]
            data["lean_counts"] = counts
            data["lang"] = event_language(data)
            data["dominant"] = dominant_lean(counts)
            data["blindspot"] = compute_blindspot(counts)
            out[r["id"]] = data
    conn.close()
    return out


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