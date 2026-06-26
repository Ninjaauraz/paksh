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


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    from sources import LEAN_BY_SOURCE
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, source, language, title, summary
           FROM articles WHERE event_id IS NULL
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
        f"""SELECT id, source, language, title, url, summary, image_url
            FROM articles WHERE id IN ({placeholders})""",
        ids,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
        try:
            topic = json.loads(e["analysis_json"]).get("topic")
        except Exception:
            topic = None
        out.append({
            "event_id": e["id"], "created_at": e["created_at"], "title": e["title"],
            "topic": topic, "source_count": len({a["source"] for a in arts}),
            "articles": [dict(a) for a in arts],
        })
    conn.close()
    return out


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

def insert_event(analysis: dict, is_demo: bool = False):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO events (title, summary, divergence, omissions, analysis_json, is_demo, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            analysis.get("title", "Untitled event"),
            analysis.get("summary", ""),
            analysis.get("divergence", ""),
            analysis.get("omissions", ""),
            json.dumps(analysis, ensure_ascii=False),
            1 if is_demo else 0,
            datetime.utcnow().isoformat(),
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
        "lean_counts": counts,
        "dominant": dominant_lean(counts),
        "blindspot": compute_blindspot(counts),
        "created_at": r["created_at"],
    }


def get_all_events():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    conn.close()
    out = [_event_summary_row(r) for r in rows]
    # Hide events that lack a real bias comparison (<2 rated outlets) -- e.g.
    # all-unrated GDELT/syndication events saved before the rated-gate existed.
    # Non-destructive: rows stay in the DB, they're just not published.
    return [e for e in out if sum(e["lean_counts"].values()) >= 2]


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


def get_event(event_id):
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