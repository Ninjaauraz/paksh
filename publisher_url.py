"""
publisher_url.py - Phase 12: recover a publisher's REAL article URL for articles stored with a news.google.com wrapper URL,
using only legitimate metadata Paksh already holds. Additive: `articles.url` is never changed.

What was measured (docs/PHASE12_PUBLISHER_URL_AND_BACKUP.md):
  * Google News RSS items carry only the wrapper link, a guid that is the same opaque id, and <source url="..."> = the publisher's
    HOME PAGE. In all 1,500 sampled stored wrapper ids the payload is the encrypted "AU_yqL" format (no URL inside), so nothing can
    be decoded offline. Nothing is fetched, unwrapped, redirected or scraped by this module.
  * The one legitimate source of the real URL is the same article arriving a second time through a DIRECT feed / GDELT (real URL,
    same publisher, identical headline, same time). That happens for ~4 % of wrapper articles, concentrated in publishers that have
    both kinds of feed.

Method `pu-1` (all conditions required, otherwise no URL is recovered):
  1. same `source` (publisher) as the wrapper article, 2. identical normalised headline (trailing " - publisher" removed) of >= 4 words,
  3. published (else first-seen) time within 72 h (6 h if that headline is used by several different URLs), 4. exactly ONE distinct candidate publisher URL (several = AMBIGUOUS, none used),
  5. the URL is http(s), is not a wrapper, and its host belongs to that publisher in the source registry when the registry knows the host.
The result says where it came from (`method`, `matched_article_id`) and is never presented as the article's original URL.

Table `article_publisher_url` (own migration, keyed by article id): original_url, publisher_url, status (VERIFIED_SIBLING | AMBIGUOUS |
REJECTED_DOMAIN), method, matched_article_id, confidence, time_gap_s, domain_consistent, verified_at, method_version.
Unrecovered articles get NO row (a sibling may still arrive later, so "no sibling yet" is not recorded as a fact).
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

METHOD = "DIRECT_FEED_TITLE_MATCH"
METHOD_VERSION = "pu-1"
MAX_GAP = timedelta(hours=72)
MIN_TITLE_WORDS = 4
RECURRING_MAX_GAP = timedelta(hours=6)
WRAPPER_PREFIX = "https://news.google.com/"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS article_publisher_url (
    article_id INTEGER PRIMARY KEY, original_url TEXT NOT NULL, publisher_url TEXT, status TEXT NOT NULL,
    method TEXT NOT NULL, matched_article_id INTEGER, confidence REAL, time_gap_s INTEGER, domain_consistent INTEGER,
    verified_at TEXT NOT NULL, method_version TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_apu_status ON article_publisher_url(status);
"""


def init_schema(conn):
    conn.executescript(_SCHEMA)
    conn.commit()


def norm_title(t):
    t = (t or "").lower()
    t = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", t)
    return re.sub(r"[^a-z0-9ऀ-ॿ]+", " ", t).strip()


def _ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d
    except Exception:
        return None


def _when(r):
    return _ts(r["published"]) or _ts(r["fetched_at"])


def _host_ok(host, source):
    """True/False when the source registry can say whether `host` belongs to `source`; None when it does not know the host
    (an unrated long-tail host resolves to its own registrable domain, which is not evidence either way)."""
    try:
        import sources
        name, rated = sources.resolve_source(host)
    except Exception:
        return None
    if not rated:
        return None
    return name == source


def _canon(url):
    p = urlparse(url)
    return f"{p.netloc.lower()}{p.path.rstrip('/')}"


def build_index(conn, sources=None):
    """(source, normalised title) -> [rows] of DIRECT-URL articles (the only place a real publisher URL can come from)."""
    idx = defaultdict(list)
    sql = "SELECT id, source, title, url, published, fetched_at, event_id FROM articles WHERE url NOT LIKE 'https://news.google.com/%'"
    args = ()
    if sources:
        sql += " AND source IN (%s)" % ",".join("?" * len(sources))
        args = tuple(sources)
    for r in conn.execute(sql, args):
        if r["url"] and r["url"].startswith(("http://", "https://")):
            idx[(r["source"], norm_title(r["title"]))].append(r)
    return idx


def recover_one(row, idx):
    """-> None (nothing recovered; no row written) or a dict describing the outcome. Pure."""
    key = (row["source"], norm_title(row["title"]))
    if len(key[1].split()) < MIN_TITLE_WORDS:
        return None
    cands = idx.get(key)
    if not cands:
        return None
    tg = _when(row)
    near = []
    for x in cands:
        tx = _when(x)
        if tg is not None and tx is not None and abs(tx - tg) <= MAX_GAP:
            near.append((abs(tx - tg), x))
    if not near:
        return None
    near.sort(key=lambda p: (p[0], p[1]["id"]))
    urls = {_canon(x["url"]) for _, x in near}
    if len(urls) > 1:
        return {"status": "AMBIGUOUS", "publisher_url": None, "matched_article_id": None, "confidence": 0.0,
                "time_gap_s": int(near[0][0].total_seconds()), "domain_consistent": None}
    gap, best = near[0]
    if len({_canon(x["url"]) for x in cands}) > 1 and gap > RECURRING_MAX_GAP:
        # this headline is used by several different URLs for this publisher (a recurring column / market wrap): only a close match counts
        return {"status": "AMBIGUOUS", "publisher_url": None, "matched_article_id": None, "confidence": 0.0,
                "time_gap_s": int(gap.total_seconds()), "domain_consistent": None}
    host = urlparse(best["url"]).hostname or ""
    dom = _host_ok(host, row["source"])
    if dom is False:
        return {"status": "REJECTED_DOMAIN", "publisher_url": None, "matched_article_id": best["id"], "confidence": 0.0,
                "time_gap_s": int(gap.total_seconds()), "domain_consistent": 0}
    conf = 0.98 if gap <= timedelta(hours=1) else 0.95
    return {"status": "VERIFIED_SIBLING", "publisher_url": best["url"], "matched_article_id": best["id"], "confidence": conf,
            "time_gap_s": int(gap.total_seconds()), "domain_consistent": (1 if dom else None), "sibling_event_id": best["event_id"]}


def recover_batch(conn, rows, idx=None, write=False, now=None):
    """rows: wrapper-URL article rows (id, source, title, url, published, fetched_at, event_id). -> stats dict (+ writes when write=True)."""
    idx = idx if idx is not None else build_index(conn, sorted({r["source"] for r in rows}))
    now = (now or datetime.now(timezone.utc).replace(tzinfo=None)).isoformat(timespec="seconds")
    st = defaultdict(int)
    out = []
    for r in rows:
        res = recover_one(r, idx)
        if res is None:
            st["unresolved"] += 1
            continue
        st[res["status"]] += 1
        out.append((r, res))
        if write:
            conn.execute("INSERT OR REPLACE INTO article_publisher_url (article_id, original_url, publisher_url, status, method, matched_article_id, "
                         "confidence, time_gap_s, domain_consistent, verified_at, method_version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (r["id"], r["url"], res["publisher_url"], res["status"], METHOD, res["matched_article_id"], res["confidence"],
                          res["time_gap_s"], res["domain_consistent"], now, METHOD_VERSION))
    if write:
        conn.commit()
    st["total"] = len(rows)
    return dict(st), out


def wrapper_rows(conn, since_iso=None, limit=5000, after_id=None):
    sql = "SELECT id, source, title, url, published, fetched_at, event_id FROM articles WHERE url LIKE 'https://news.google.com/%'"
    args = []
    if since_iso:
        sql += " AND fetched_at >= ?"
        args.append(since_iso)
    if after_id is not None:
        sql += " AND id > ?"
        args.append(after_id)
    return conn.execute(sql + " ORDER BY id LIMIT ?", (*args, limit)).fetchall()


def recover_recent(conn, days=3, limit=5000):
    """The nightly hook: wrapper articles first seen in the last `days` days (a sibling may arrive after the wrapper). Bounded, idempotent."""
    init_schema(conn)
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = wrapper_rows(conn, since_iso=since, limit=limit)
    st, _ = recover_batch(conn, rows, write=True)
    return st


def lookup(conn, article_ids):
    """{article_id: publisher_url} for VERIFIED rows only. Read-only; empty if the table does not exist."""
    out = {}
    try:
        ids = list(article_ids)
        for i in range(0, len(ids), 400):
            ch = ids[i:i + 400]
            for r in conn.execute("SELECT article_id, publisher_url FROM article_publisher_url WHERE status='VERIFIED_SIBLING' AND article_id IN (%s)" % ",".join("?" * len(ch)), ch):
                out[r[0]] = r[1]
    except Exception:
        return {}
    return out
