"""
test_si_queue.py - Story Intelligence reprocessing queue + evidence-aware processing. Temp databases only.
Run:  py test_si_queue.py
"""
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import database as d
import evidence_retrieval as er
import si_queue as q
import story_intelligence as si

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


def fresh(name):
    d.DB_PATH, d._db_initialized = Path(tempfile.mkdtemp(prefix="siq_")) / f"{name}.db", False
    return d.get_connection()


NOW = datetime(2026, 9, 22, 12, 0, 0)
ISO = lambda dt: dt.isoformat(timespec="seconds")
_aid = [0]


def add_event(conn, eid, updated=None, n_articles=3, sources=("The Hindu", "NDTV", "Indian Express", "Reuters"), url_base="https://x.test"):
    updated = updated or ISO(NOW - timedelta(hours=1))
    conn.execute("INSERT INTO events (id, title, summary, is_demo, analysis_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                 (eid, f"Story {eid}", "s", 0, json.dumps({"content_complete": True}), updated, updated))
    for i in range(n_articles):
        add_article(conn, eid, sources[i % len(sources)], f"Fire at plant number {eid} update {i}", f"{url_base}/{eid}/{i}", i)
    conn.commit()


def add_article(conn, eid, source, title, url, i=0):
    _aid[0] += 1
    conn.execute("INSERT INTO articles (source, language, title, url, summary, image_url, published, fetched_at, event_id) VALUES (?,?,?,?,?,?,?,?,?)",
                 (source, "en", title, url, "", "", ISO(NOW - timedelta(hours=3, minutes=-10 * i)), ISO(NOW - timedelta(hours=1)), eid))


print("TEST 1: schema and scanning")
c = fresh("scan")
q.init_queue_schema(c)
q.init_queue_schema(c)
add_event(c, 1)
add_event(c, 2, n_articles=1)                       # a one-article story is never queued
r = q.scan_and_enqueue(c, now=NOW)
check("1a: a new story is queued as NEW; a 1-article story is not", r["queued"] == 1 and r["by_reason"] == {"NEW": 1})
check("1b: a second scan queues nothing (no duplicate)", q.scan_and_enqueue(c, now=NOW)["queued"] == 0)
check("1c: the queue row carries reason, priority, enqueued_at, engine version", dict(c.execute("SELECT status, reason, priority, engine_version FROM si_queue").fetchone()) ==
      {"status": "QUEUED", "reason": "NEW", "priority": q.compute_priority("NEW", ISO(NOW - timedelta(hours=1)), 3, True, False, NOW), "engine_version": si.ENGINE_VERSION})

print("\nTEST 2: processing, idempotency, unchanged inputs")
out = q.process_queue(c, limit=10, budget_s=60, allow_evidence=False, now=NOW)
check("2a: the story is processed", out["processed"] == 1 and c.execute("SELECT status, outcome FROM si_queue").fetchone()["status"] == "PROCESSED")
check("2b: state and graph rows exist", c.execute("SELECT COUNT(*) FROM si_story_state").fetchone()[0] == 1 and c.execute("SELECT COUNT(*) FROM si_reporting_event_articles").fetchone()[0] == 3)
check("2c: rescan queues nothing for an unchanged story", q.scan_and_enqueue(c, now=NOW + timedelta(minutes=5))["queued"] == 0)
c.execute("UPDATE events SET updated_at=? WHERE id=1", (ISO(NOW + timedelta(hours=1)),))
c.commit()
r = q.scan_and_enqueue(c, now=NOW + timedelta(hours=2))
check("2d: an updated story is queued as STORY_UPDATED", r["by_reason"] == {"STORY_UPDATED": 1})
out = q.process_queue(c, limit=10, budget_s=60, allow_evidence=False, now=NOW + timedelta(hours=2))
check("2e: the unchanged input signature is recognised: outcome 'unchanged', nothing recomputed", out["unchanged"] == 1 and out["processed"] == 0)
check("2f: ...and it is not queued again and again (verified-as-of moves forward)", q.scan_and_enqueue(c, now=NOW + timedelta(hours=3))["queued"] == 0)

print("\nTEST 3: membership change keeps detected_at")
det = c.execute("SELECT detected_at FROM si_reporting_event_articles WHERE article_id=1").fetchone()[0]
add_article(c, 1, "The Tribune", "Fire at plant number 1 update 9", "https://x.test/1/9", 9)
c.execute("UPDATE events SET updated_at=? WHERE id=1", (ISO(NOW + timedelta(hours=5)),))
c.commit()
r = q.scan_and_enqueue(c, now=NOW + timedelta(hours=6))
check("3a: a new article is MEMBERSHIP_CHANGED", r["by_reason"] == {"MEMBERSHIP_CHANGED": 1})
q.process_queue(c, limit=10, budget_s=60, allow_evidence=False, now=NOW + timedelta(hours=6))
check("3b: reprocessed with 4 articles", c.execute("SELECT COUNT(*) FROM si_reporting_event_articles WHERE event_id=1").fetchone()[0] == 4)
check("3c: detected_at of surviving rows is preserved", c.execute("SELECT detected_at FROM si_reporting_event_articles WHERE article_id=1").fetchone()[0] == det)

print("\nTEST 4: engine version invalidation and evidence")
orig = si.ENGINE_VERSION
si.ENGINE_VERSION = "si-next"
r = q.scan_and_enqueue(c, now=NOW + timedelta(hours=7))
check("4a: a new engine version queues previously processed stories (ENGINE_VERSION)", r["by_reason"] == {"ENGINE_VERSION": 1})
si.ENGINE_VERSION = orig
c.execute("UPDATE si_queue SET status='PROCESSED', finished_at=?", (ISO(NOW),))
c.commit()
er.init_evidence_schema(c)
c.execute("INSERT INTO si_evidence (article_id, url, status, extraction_status, text, extractor_version, updated_at) VALUES (1,'https://x.test/1/0','ok','ok','text',?,?)",
          (er.EXTRACTOR_VERSION, ISO(NOW + timedelta(days=1))))
c.commit()
r = q.scan_and_enqueue(c, now=NOW + timedelta(days=1, hours=1))
check("4b: new evidence for a story's article queues it (EVIDENCE_UPDATED)", r["by_reason"] == {"EVIDENCE_UPDATED": 1})

print("\nTEST 5: priority")
c = fresh("prio")
add_event(c, 10, updated=ISO(NOW - timedelta(days=20)), sources=("The Hindu", "NDTV", "Indian Express", "Reuters"))
add_event(c, 11, updated=ISO(NOW - timedelta(hours=2)), sources=("The Hindu", "NDTV", "Indian Express", "Reuters"))
add_event(c, 12, updated=ISO(NOW - timedelta(hours=2)), sources=("The Hindu", "The Hindu", "The Hindu", "The Hindu"))
q.scan_and_enqueue(c, days=60, now=NOW)
order = [r[0] for r in c.execute("SELECT event_id FROM si_queue ORDER BY priority DESC, enqueued_at, event_id")]
check("5a: recent + broad (many publishers) first, old backlog last", order == [11, 12, 10], str(order))
check("5b: priority is deterministic", q.compute_priority("NEW", ISO(NOW), 4, True, False, NOW) == q.compute_priority("NEW", ISO(NOW), 4, True, False, NOW))

print("\nTEST 6: bounded processing, budget, pause")
out = q.process_queue(c, limit=2, budget_s=60, allow_evidence=False, now=NOW)
check("6a: at most `limit` stories are processed; the rest stay QUEUED", out["claimed"] == 2 and out["processed"] == 2 and c.execute("SELECT COUNT(*) FROM si_queue WHERE status='QUEUED'").fetchone()[0] == 1)
q.enqueue(c, 12, "MANUAL", 5000)
out = q.process_queue(c, limit=5, budget_s=-1, allow_evidence=False, now=NOW)
st = {r[0]: r[1] for r in c.execute("SELECT event_id, status FROM si_queue")}
check("6b: budget exhausted -> nothing is marked processed, claimed rows go back to the queue untouched", out["processed"] == 0 and out["returned_to_queue"] >= 1
      and st[10] == "QUEUED", str(st))
q.control_set(c, "paused", 1)
check("6c: paused -> nothing is processed", q.process_queue(c, limit=5, budget_s=60, now=NOW) == {"paused": True} and q.queue_counts(c).get("QUEUED", 0) >= 1)
q.control_set(c, "paused", 0)

print("\nTEST 7: failure, retry, backoff, stale recovery")
c = fresh("fail")
add_event(c, 20)
q.scan_and_enqueue(c, now=NOW)
real = q.process_one
q.process_one = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
out = q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=NOW)
row = c.execute("SELECT status, attempts, last_error, next_attempt_at FROM si_queue").fetchone()
check("7a: a failure is recorded (RETRY, attempts=1, error, next attempt in the future) and the run carries on", out["failed"] == 1 and row["status"] == "RETRY" and row["attempts"] == 1
      and "boom" in row["last_error"] and row["next_attempt_at"] > ISO(NOW))
out = q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=NOW)
check("7b: it is not retried before next_attempt_at", out["claimed"] == 0)
t = NOW
for i in range(5):
    t = t + timedelta(days=2)
    q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=t)
row = c.execute("SELECT status, attempts FROM si_queue").fetchone()
check("7c: after MAX_ATTEMPTS it is FAILED (needs a manual retry)", row["status"] == "FAILED" and row["attempts"] == q.MAX_ATTEMPTS)
check("7d: manual retry re-queues it with attempts reset", q.retry_failed(c, 10) == 1 and c.execute("SELECT status, attempts FROM si_queue").fetchone()[:] == ("QUEUED", 0))
q.process_one = real
out = q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=NOW)
check("7e: once the fault is gone the story succeeds", out["processed"] == 1 and c.execute("SELECT status FROM si_queue").fetchone()[0] == "PROCESSED")
c.execute("UPDATE si_queue SET status='PROCESSING', started_at=?", (ISO(NOW - timedelta(hours=2)),))
c.commit()
check("7f: a crashed (stale) PROCESSING row is recovered to QUEUED", q.recover_stale(c, NOW) == 1 and c.execute("SELECT status, reason FROM si_queue").fetchone()[:] == ("QUEUED", "STALE_RECOVERED"))

print("\nTEST 8: consolidation removes vanished stories")
c = fresh("prune")
add_event(c, 30)
q.scan_and_enqueue(c, now=NOW)
q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=NOW)
c.execute("DELETE FROM events WHERE id=30")
c.commit()
q.scan_and_enqueue(c, now=NOW)
check("8a: queue rows and si_* rows of a deleted story are pruned", c.execute("SELECT COUNT(*) FROM si_queue").fetchone()[0] == 0 and c.execute("SELECT COUNT(*) FROM si_story_state").fetchone()[0] == 0
      and c.execute("SELECT COUNT(*) FROM si_reporting_event_articles").fetchone()[0] == 0)

print("\nTEST 9: evidence in the queue (fake pages, no network)")
c = fresh("evq")
add_event(c, 40, n_articles=4)
q.scan_and_enqueue(c, now=NOW)
PAGES = {"https://x.test/40/1": "<html><article><p>NEW DELHI (PTI) A fire broke out at a chemical plant on the outskirts of the city on Monday, killing at least twelve workers and injuring dozens more, officials said.</p><p>Rescue teams pulled several people from the debris through the night while the district administration announced compensation for the families.</p></article></html>"}
calls = []


def fake_fetch(url, session=None, deadline_s=15):
    calls.append(url)
    if url in PAGES:
        return er.FetchResult(url=url, status="ok", http_status=200, final_url=url, html=PAGES[url], nbytes=len(PAGES[url]), ttl=er.TTL_OK, requests_made=2)
    return er.FetchResult(url=url, status="failed", http_status=500, error_class="http_500", ttl=er.TTL_FAILED, requests_made=2)


real_fetch = er.fetch_page
er.fetch_page = fake_fetch
try:
    out = q.process_queue(c, limit=5, budget_s=60, allow_evidence=False, now=NOW)
    check("9a: evidence disabled (the default): no fetch at all", calls == [] and out["processed"] == 1 and out["evidence"] is False)
    row = c.execute("SELECT role, reason, evidence_source, metadata_role FROM si_reporting_event_articles WHERE article_id=(SELECT MIN(id) FROM articles WHERE event_id=40)").fetchone()
    check("9b: with no evidence every verdict's source is METADATA", c.execute("SELECT COUNT(*) FROM si_reporting_event_articles WHERE evidence_source!='METADATA'").fetchone()[0] == 0)
    q.enqueue(c, 40, "MANUAL", 100)
    c.execute("UPDATE si_story_state SET input_sig='force'")
    c.commit()
    er._robots.clear()
    er._robots["https://x.test"] = (10 ** 12, __import__("urllib.robotparser", fromlist=["x"]).RobotFileParser())
    er._robots["https://x.test"][1].parse([])
    er._host_is_public = lambda h: True
    er.DOMAIN_DELAY_S = 0
    out = q.process_queue(c, limit=5, budget_s=60, allow_evidence=True, now=NOW)
    check("9c: evidence enabled: triggered articles are fetched within the budget", len(calls) >= 1 and out["fetch"]["fetches"] == len(calls) and out["fetch"]["fetches"] <= 30, str((calls, out)))
    fa = c.execute("SELECT role, reason, evidence_source, metadata_role, metadata_reason, evidence_version, evidence_json FROM si_reporting_event_articles WHERE evidence_source='FETCHED_ARTICLE'").fetchall()
    check("9d: a fetched dateline turns an UNCERTAIN article into ATTRIBUTED_REPETITION with provenance FETCHED_ARTICLE",
          len(fa) == 1 and fa[0]["role"] == "ATTRIBUTED_REPETITION" and fa[0]["reason"] == "FETCHED_ATTRIBUTION" and fa[0]["evidence_version"] == si.EVIDENCE_LOGIC_VERSION)
    check("9e: the original metadata verdict is preserved beside it (never erased)", fa[0]["metadata_role"] == "UNCERTAIN" and "metadata_verdict" in json.loads(fa[0]["evidence_json"]))
    n = len(calls)
    q.enqueue(c, 40, "MANUAL", 100)
    c.execute("UPDATE si_story_state SET input_sig='force'")
    c.commit()
    q.process_queue(c, limit=5, budget_s=60, allow_evidence=True, now=NOW)
    check("9f: nothing is fetched twice (cache hits and cached failures)", len(calls) == n, f"{calls}")
    check("9g: the evidence table records the outcomes", er.cache_stats(c)["rows"] >= 1)
finally:
    er.fetch_page = real_fetch

print("\nTEST 10: the pipeline hook")
c = fresh("hook")
add_event(c, 50)
c.close()
out = q.run_cycle(limit=10, budget_s=30)
check("10a: run_cycle scans, processes and reports (evidence off by default)", out["scan"]["queued"] == 1 and out["process"]["processed"] == 1 and out["process"]["evidence"] is False)
check("10b: run_cycle never raises", "error" not in out)
d.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("card unplugged"))
check("10c: ...even when the database is unavailable", "card unplugged" in q.run_cycle().get("error", ""))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL si_queue CHECKS PASSED")
