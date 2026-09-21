"""
test_publisher_url.py - Phase 12: publisher-URL recovery for news.google.com wrapper articles (additive provenance) and its use by
evidence retrieval. Temp databases only; no network. Run:  py test_publisher_url.py
"""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import database as d
import evidence_retrieval as er
import publisher_url as pu
import si_queue as q

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


def fresh(name):
    d.DB_PATH, d._db_initialized = Path(tempfile.mkdtemp(prefix="pu_")) / f"{name}.db", False
    return d.get_connection()


T0 = datetime(2026, 9, 20, 10, 0, 0)
GN = "https://news.google.com/rss/articles/CBMiOpaqueIdThatCannotBeDecoded"
_n = [0]


def art(conn, source, title, url, when=T0, event=1):
    _n[0] += 1
    conn.execute("INSERT INTO articles (source, language, title, url, summary, image_url, published, fetched_at, event_id) VALUES (?,?,?,?,?,?,?,?,?)",
                 (source, "en", title, url, "", "", when.isoformat(timespec="seconds"), when.isoformat(timespec="seconds"), event))
    return conn.execute("SELECT MAX(id) FROM articles").fetchone()[0]


def recover(conn, write=False):
    rows = pu.wrapper_rows(conn)
    if write:
        pu.init_schema(conn)
    return pu.recover_batch(conn, rows, write=write)


print("TEST 1: what counts as the same article")
check("1a: the trailing ' - publisher' is ignored, punctuation and case too", pu.norm_title("Fire At Plant, Rescue On - thehindu.com") == pu.norm_title("fire at plant , rescue on"))
c = fresh("basic")
g1 = art(c, "The Hindu", "Fire at chemical plant kills twelve workers - thehindu.com", GN + "1")
s1 = art(c, "The Hindu", "Fire at chemical plant kills twelve workers", "https://www.thehindu.com/news/national/fire-at-plant/article1.ece", T0 + timedelta(minutes=20), 2)
st, out = recover(c)
check("1b: identical headline, same publisher, 20 min apart, a real registry host = VERIFIED_SIBLING", st.get("VERIFIED_SIBLING") == 1 and out[0][1]["publisher_url"].endswith("article1.ece"))
check("1c: the result names its origin (sibling article id) and a confidence, never claims to be the original url", out[0][1]["matched_article_id"] == s1 and 0.9 <= out[0][1]["confidence"] <= 1.0)
c = fresh("other_source")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", GN + "2")
art(c, "NDTV", "Fire at chemical plant kills twelve workers", "https://www.ndtv.com/india/fire-1", T0)
check("1d: a different publisher's identical headline is NOT a match", recover(c)[0].get("VERIFIED_SIBLING", 0) == 0)
c = fresh("late")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", GN + "3")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", "https://www.thehindu.com/news/a/article2.ece", T0 + timedelta(days=5))
check("1e: five days apart is not the same event/article", recover(c)[0].get("VERIFIED_SIBLING", 0) == 0)
c = fresh("short")
art(c, "The Hindu", "Morning Digest", GN + "4")
art(c, "The Hindu", "Morning Digest", "https://www.thehindu.com/news/a/article3.ece", T0)
check("1f: a very short headline (recurring column) is never matched", recover(c)[0].get("VERIFIED_SIBLING", 0) == 0)
c = fresh("ambig")
art(c, "The Hindu", "Sensex and Nifty today what to expect from markets", GN + "5")
art(c, "The Hindu", "Sensex and Nifty today what to expect from markets", "https://www.thehindu.com/business/a/article4.ece", T0)
art(c, "The Hindu", "Sensex and Nifty today what to expect from markets", "https://www.thehindu.com/business/a/article5.ece", T0 + timedelta(hours=30))
st, out = recover(c)
check("1g: two different URLs for the same headline inside the window = AMBIGUOUS, none used", st.get("AMBIGUOUS") == 1 and out[0][1]["publisher_url"] is None)
c = fresh("recurring")
art(c, "The Hindu", "Sensex and Nifty today what to expect from markets", GN + "6", T0 + timedelta(hours=20))
art(c, "The Hindu", "Sensex and Nifty today what to expect from markets", "https://www.thehindu.com/business/a/article6.ece", T0)
art(c, "The Hindu", "Sensex and Nifty today what to expect from markets", "https://www.thehindu.com/business/a/article7.ece", T0 + timedelta(days=9))
st, out = recover(c)
check("1h: a headline that several different URLs share needs a close (<=6 h) match, otherwise AMBIGUOUS", st.get("AMBIGUOUS") == 1 and st.get("VERIFIED_SIBLING", 0) == 0)
c = fresh("domain")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", GN + "7")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", "https://www.thehindubusinessline.com/news/a/article8.ece", T0)
st, out = recover(c)
check("1i: a candidate on ANOTHER registry publisher's domain is REJECTED_DOMAIN and yields no URL", st.get("REJECTED_DOMAIN") == 1 and out[0][1]["publisher_url"] is None)
c = fresh("unknownhost")
art(c, "Some Long Tail Outlet", "Fire at chemical plant kills twelve workers", GN + "8")
art(c, "Some Long Tail Outlet", "Fire at chemical plant kills twelve workers", "https://longtail.example/news/a-9", T0)
st, out = recover(c)
check("1j: a host the registry does not know is not rejected, and domain_consistent stays unknown (None)", st.get("VERIFIED_SIBLING") == 1 and out[0][1]["domain_consistent"] is None)

print("\nTEST 2: additive, idempotent, provenance kept")
c = fresh("write")
g = art(c, "The Hindu", "Fire at chemical plant kills twelve workers", GN + "9")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", "https://www.thehindu.com/news/a/article9.ece", T0 + timedelta(minutes=5), 2)
before = c.execute("SELECT url FROM articles WHERE id=?", (g,)).fetchone()[0]
recover(c, write=True)
recover(c, write=True)
row = c.execute("SELECT * FROM article_publisher_url WHERE article_id=?", (g,)).fetchone()
check("2a: articles.url is NEVER changed", c.execute("SELECT url FROM articles WHERE id=?", (g,)).fetchone()[0] == before == row["original_url"])
check("2b: one row per article after two runs (idempotent), with method and version", c.execute("SELECT COUNT(*) FROM article_publisher_url").fetchone()[0] == 1
      and row["method"] == "DIRECT_FEED_TITLE_MATCH" and row["method_version"] == "pu-1" and row["status"] == "VERIFIED_SIBLING")
check("2c: only VERIFIED rows are returned by lookup", pu.lookup(c, [g]) == {g: "https://www.thehindu.com/news/a/article9.ece"})
c.execute("UPDATE article_publisher_url SET status='AMBIGUOUS'")
c.commit()
check("2d: an AMBIGUOUS / rejected row is never served", pu.lookup(c, [g]) == {})
check("2e: lookup on a database without the table is empty, not an error", pu.lookup(fresh("notable"), [1]) == {})

print("\nTEST 3: evidence retrieval uses a verified publisher url, never the wrapper")
c = fresh("evi")
calls = []
real = er.fetch_page


def fake_fetch(url, session=None, deadline_s=15):
    calls.append(url)
    html = "<html><article><p>" + ("A fire broke out at the chemical plant on Monday and officials said rescue teams pulled several people from the debris. " * 3) + "</p></article></html>"
    return er.FetchResult(url=url, status="ok", http_status=200, final_url=url, html=html, nbytes=len(html), ttl=er.TTL_OK, requests_made=2)


er.fetch_page = fake_fetch
try:
    row, act = er.get_evidence(c, {"id": 1, "url": GN + "x"}, budget=er.FetchBudget())
    check("3a: a wrapper url with no verified publisher url is NEVER fetched", act == "NO_FETCH:google_news_redirect_url" and calls == [])
    row, act = er.get_evidence(c, {"id": 1, "url": GN + "x", "publisher_url": "https://www.thehindu.com/news/a/article9.ece"}, budget=er.FetchBudget())
    check("3b: with a verified publisher url the PUBLISHER url is fetched", act == "FETCHED_OK" and calls == ["https://www.thehindu.com/news/a/article9.ece"])
    r = c.execute("SELECT url, url_source, original_url FROM si_evidence WHERE article_id=1").fetchone()
    check("3c: the cache records which url was really used, its source and the original", (r["url"], r["url_source"], r["original_url"]) ==
          ("https://www.thehindu.com/news/a/article9.ece", "PUBLISHER_URL", GN + "x"))
    row, act = er.get_evidence(c, {"id": 1, "url": GN + "x", "publisher_url": "https://www.thehindu.com/news/a/article9.ece"}, budget=er.FetchBudget())
    check("3d: a second call is a cache hit (no duplicate fetch)", act == "CACHE_HIT" and len(calls) == 1)
    row, act = er.get_evidence(c, {"id": 2, "url": GN + "y", "publisher_url": "javascript:alert(1)"}, budget=er.FetchBudget())
    check("3e: an unsafe 'publisher url' is refused", act.startswith("NO_FETCH") and len(calls) == 1)
    row, act = er.get_evidence(c, {"id": 3, "url": "https://www.thehindu.com/news/a/direct.ece", "publisher_url": "https://other.example/x"}, budget=er.FetchBudget())
    check("3f: an article's own direct url always wins over a recovered one", calls[-1] == "https://www.thehindu.com/news/a/direct.ece" and c.execute("SELECT url_source FROM si_evidence WHERE article_id=3").fetchone()[0] == "ORIGINAL")
finally:
    er.fetch_page = real

print("\nTEST 4: queue interaction")
c = fresh("queue")
NOW = datetime(2026, 9, 22, 12, 0, 0)
ISO = lambda x: x.isoformat(timespec="seconds")
c.execute("INSERT INTO events (id, title, summary, is_demo, analysis_json, created_at, updated_at) VALUES (1,'s','s',0,?,?,?)", (json.dumps({"content_complete": True}), ISO(NOW - timedelta(hours=2)), ISO(NOW - timedelta(hours=2))))
gid = art(c, "The Hindu", "Fire at plant number one update zero", GN + "q", NOW - timedelta(hours=3))
for i, s in enumerate(("NDTV", "Indian Express")):
    art(c, s, f"Fire at plant number one update {i + 1}", f"https://x.test/{i}", NOW - timedelta(hours=3, minutes=-10 * (i + 1)))
q.scan_and_enqueue(c, now=NOW)
q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=NOW)
check("4a: baseline: processed, nothing to re-queue", q.scan_and_enqueue(c, now=NOW + timedelta(minutes=1))["queued"] == 0)
pu.init_schema(c)
c.execute("INSERT INTO article_publisher_url (article_id, original_url, publisher_url, status, method, verified_at, method_version) VALUES (?,?,?,?,?,?,?)",
          (gid, GN + "q", "https://www.thehindu.com/news/a/q.ece", "VERIFIED_SIBLING", pu.METHOD, ISO(NOW + timedelta(hours=1)), "pu-1"))
c.commit()
r = q.scan_and_enqueue(c, now=NOW + timedelta(hours=2))
check("4b: a newly verified publisher url for a story's article re-queues the story", r["queued"] == 1)
c.close()
c = fresh("hook")
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", GN + "h", datetime.utcnow() - timedelta(hours=1))
art(c, "The Hindu", "Fire at chemical plant kills twelve workers", "https://www.thehindu.com/news/a/h.ece", datetime.utcnow() - timedelta(hours=1))
st = pu.recover_recent(c, days=3)
check("4c: the nightly hook recovers recent wrapper articles and is idempotent", st.get("VERIFIED_SIBLING") == 1 and pu.recover_recent(c, days=3).get("VERIFIED_SIBLING") == 1
      and c.execute("SELECT COUNT(*) FROM article_publisher_url").fetchone()[0] == 1)

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL publisher_url CHECKS PASSED")
