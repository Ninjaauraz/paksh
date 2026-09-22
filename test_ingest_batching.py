"""
test_ingest_batching.py - database.ArticleWriter (batched article inserts) must behave exactly like a loop of
insert_article() calls, differing only in WHEN rows are committed. Temp databases only; never touches paksh.db.

Run:  py test_ingest_batching.py
"""
import os
import sqlite3
import tempfile
from pathlib import Path

import database as d

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


def fresh(name):
    d.DB_PATH, d._db_initialized = Path(tempfile.mkdtemp(prefix="ingest_batch_")) / f"{name}.db", False
    d.get_connection().close()
    return d.DB_PATH


def rows_of(path):
    c = sqlite3.connect(path)
    r = c.execute("SELECT id, source, language, title, url, summary, image_url, published, event_id FROM articles ORDER BY id").fetchall()
    f = [x[0] for x in c.execute("SELECT fetched_at FROM articles ORDER BY id")]
    c.close()
    return r, f


DATA = [("The Hindu", "en", f"Title {i}", f"https://x.test/{i % 9}", f"summary {i}", "img", "2026-09-20T00:00:00+00:00") for i in range(14)]
# urls repeat (i % 9): 9 unique, 5 duplicates -> the IntegrityError path

print("TEST 1: same results, same rows as a loop of insert_article()")
p1 = fresh("perrow")
res1 = [d.insert_article(*r) for r in DATA]
rows1, f1 = rows_of(p1)
p2 = fresh("batched")
with d.ArticleWriter(batch_size=4) as w:
    res2 = [w.insert(*r) for r in DATA]
rows2, f2 = rows_of(p2)
check("1a: returned ids / None-for-duplicate sequence identical", res1 == res2, f"{res1} vs {res2}")
check("1b: stored rows identical (every column but fetched_at)", rows1 == rows2)
check("1c: 9 unique rows, 5 duplicates ignored", len(rows2) == 9 and res2.count(None) == 5)
check("1d: fetched_at is set per row and never decreases", all(f2) and f2 == sorted(f2))

print("\nTEST 2: batch boundaries and visibility")
p3 = fresh("bounds")
w = d.ArticleWriter(batch_size=3)
for r in DATA[:2]:
    w.insert(*r)
other = sqlite3.connect(p3)
check("2a: below the batch size nothing is committed yet (another connection sees 0 rows)", other.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0)
w.insert(*DATA[2])
check("2b: reaching the batch size commits (3 rows visible, 1 commit)", other.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 3 and w.commits == 1)
w.insert(*DATA[3])
w.flush()
check("2c: flush() commits the partial batch", other.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 4 and w.commits == 2)
w.flush()
check("2d: flushing with nothing pending is a no-op", w.commits == 2)
w.close()
other.close()
p4 = fresh("counts")
with d.ArticleWriter(batch_size=4) as w:
    for r in DATA:
        w.insert(*r)
check("2e: 9 inserted rows at batch 4 = 3 commits (4 + 4 + 1)", w.commits == 3 and w.inserted == 9)

print("\nTEST 3: failure semantics")
p5 = fresh("crash")
w = d.ArticleWriter(batch_size=100)
for r in DATA[:5]:
    w.insert(*r)
w._conn.close()                                          # simulate the process dying: connection dropped without commit
w._conn = None
c = sqlite3.connect(p5)
check("3a: an un-flushed batch is simply not committed (no partial garbage; the next cycle re-ingests it)", c.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0)
c.close()
p6 = fresh("nonintegrity")
w = d.ArticleWriter(batch_size=100)
for r in DATA[:3]:
    w.insert(*r)
try:
    w.insert("S", "en", "T", "https://x.test/zzz", ["not", "sqlite", "type"], "", "")
    raised = False
except Exception:
    raised = True
w.close()
c = sqlite3.connect(p6)
check("3b: a non-integrity error propagates (as insert_article would) ...", raised)
check("3c: ... after the rows already inserted were committed (what the per-row version had persisted)", c.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 3)
c.close()
p7 = fresh("notnull")
with d.ArticleWriter(batch_size=2) as w:
    a = w.insert("S", "en", None, "https://x.test/n1", "s", "", "")         # NOT NULL title -> IntegrityError -> None, like insert_article
    b = w.insert("S", "en", "ok", "https://x.test/n2", "s", "", "")
check("3d: any IntegrityError (not only duplicate urls) returns None and the run continues", a is None and b is not None)

print("\nTEST 4: lazy connection")
p8 = fresh("lazy")
orig = d.get_connection
d.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("must not connect"))
try:
    with d.ArticleWriter() as w:
        pass
    lazy_ok = True
except RuntimeError:
    lazy_ok = False
finally:
    d.get_connection = orig
check("4a: a writer that never inserts never opens the database", lazy_ok)

print("\nTEST 5: the real callers give the same result with and without a writer")
import ingest


class _Parsed:
    bozo = False
    entries = [object() for _ in range(8)]


def fake_norm(entry, source):
    i = _Parsed.entries.index(entry)
    return {"source": source["name"], "language": "en", "title": f"Story {i}", "url": f"https://x.test/f/{i % 6}", "summary": "s",
            "image_url": "", "published": "2026-09-20T00:00:00+00:00"}


ingest.fetch_feed = lambda u: _Parsed
ingest.normalize_entry = fake_norm
src = {"id": "x", "name": "The Hindu", "language": "en"}
pa = fresh("ing_a")
na = ingest.ingest_feed("u", src, set())
ra, _ = rows_of(pa)
pb = fresh("ing_b")
with d.ArticleWriter(batch_size=3) as w:
    nb = ingest.ingest_feed("u", src, set(), w)
rb, _ = rows_of(pb)
check("5a: ingest_feed returns the same (new, considered) with and without a writer", na == nb == (6, 8), f"{na} {nb}")
check("5b: ...and stores identical rows", ra == rb)
check("5c: ingest_feed flushes at the end of each feed (nothing left pending)", w.commits >= 1)

import gdelt_source as g
g.init_db = lambda: None
g._fetch = lambda q, timespan=None, **k: [{"i": i} for i in range(5)]
g.normalize_gdelt = lambda art: {"source": "Reuters", "language": "en", "title": f"G{art['i']}", "url": f"https://g.test/{art['i'] % 4}", "summary": "s",
                                 "image_url": "", "published": "2026-09-20T00:00:00+00:00", "rated": True, "domain": "g.test"}
g.SLEEP = 0
g.gdelt_gate.wait_for_slot = lambda *a, **k: 0.0                 # Phase 21C: no real lock/sleep in a unit test
g.METRICS_PATH = os.path.join(tempfile.mkdtemp(), "test_gdelt_metrics.jsonl")  # Phase 21D: never touch the real file
pc = fresh("gd")
added = g.run(queries=["q1", "q2"], verbose=False)
rc, _ = rows_of(pc)
check("5d: gdelt_source.run counts and stores the same rows through the writer (4 unique of 5, second query all duplicates)", added == 4 and len(rc) == 4, f"{added} {len(rc)}")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL ingest batching CHECKS PASSED")
