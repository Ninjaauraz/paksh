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


def get_unclustered_articles(limit=1100, per_source=60):
    """Return un-grouped articles, BALANCED across outlets.

    A naive 'most recent N' lets a prolific outlet (e.g. Indian Express with many
    section feeds) flood the window and crowd out the cross-outlet overlap that
    actually forms events. So we take each outlet's most-recent `per_source`
    articles, giving every outlet a fair shot at landing on the same big stories."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, source, language, title, summary
           FROM articles WHERE event_id IS NULL
           ORDER BY fetched_at DESC"""
    ).fetchall()
    conn.close()
    by_source, out = {}, []
    for r in rows:
        s = r["source"]
        if by_source.get(s, 0) >= per_source:
            continue
        by_source[s] = by_source.get(s, 0) + 1
        out.append(dict(r))
    return out[:limit]


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
    A Blindspot = a story one side is barely covering while another dominates.
    Returns {side, pct} for the under-covering side, or None.
    Needs 3+ total sources so it's a real story, one side >=50%, another <=15%.
    """
    total = sum(counts.values())
    if total < 3:
        return None
    pcts = {s: counts[s] / total * 100 for s in LEAN_ORDER}
    top = max(LEAN_ORDER, key=lambda s: pcts[s])
    low = min(LEAN_ORDER, key=lambda s: pcts[s])
    if pcts[top] >= 50 and pcts[low] <= 15:
        return {"side": low, "pct": round(pcts[low])}
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
    return {
        "id": r["id"],
        "title": r["title"],
        "summary": r["summary"],
        "summary_points": data.get("summary_points", []),
        "title_hi": data.get("title_hi", ""),
        "summary_hi": data.get("summary_hi", ""),
        "summary_points_hi": data.get("summary_points_hi", []),
        "topic": data.get("topic", "General"),
        "lang": event_language(data),
        "image_url": data.get("image_url", ""),
        "is_demo": bool(r["is_demo"]),
        "source_count": len(data.get("sources", [])),
        "lean_counts": counts,
        "dominant": dominant_lean(counts),
        "blindspot": compute_blindspot(counts),
        "created_at": r["created_at"],
    }


def get_all_events():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_event_summary_row(r) for r in rows]


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