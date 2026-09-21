"""
si_queue.py - the Story Intelligence reprocessing queue (SQLite only, no new infrastructure).

It answers: which stories need (re)processing, why, since when, for which engine version, how the last attempt went,
how many retries, and when the next attempt is due - so stories are reprocessed when their inputs, the engine version or
their evidence change, and never by a full-corpus rebuild.

    QUEUED --claim--> PROCESSING --ok--> PROCESSED
                          |--error--> RETRY (attempt < MAX_ATTEMPTS, next_attempt_at = now + backoff) --> ... --> FAILED (manual `retry`)
    PROCESSING older than STALE_PROCESSING_MIN (a crashed run) is recovered to QUEUED.  PROCESSED rows are the audit trail.

"Needs processing" is decided by cheap prefilters (no state, other engine version, article count changed, story updated
since it was last verified, new evidence) and CONFIRMED at processing time by the input signature, which stays the single
source of truth: an unchanged signature is recorded as outcome 'unchanged' and never recomputed (so nothing is queued
twice for the same input).  Evidence retrieval (fetching) only ever happens here, inside the strict budgets below, and only
when switched on (`evidence --enable`); with it off the queue processes metadata-only stories exactly like si-1.

Everything is non-fatal for publication: the pipeline step wraps run_cycle() and never lets it raise.
"""
import json
import time
from datetime import datetime, timedelta, timezone

import story_intelligence as si

QUEUED, PROCESSING, PROCESSED, RETRY, FAILED = "QUEUED", "PROCESSING", "PROCESSED", "RETRY", "FAILED"
MAX_ATTEMPTS = 5
BACKOFF_BASE_MIN = 15               # next attempt after 15, 30, 60, 120 min (cap 24 h)
STALE_PROCESSING_MIN = 30
KEEP_PROCESSED_DAYS = 14            # audit rows older than this are pruned
DEFAULT_SCAN_LIMIT = 400
DEFAULT_SCAN_DAYS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS si_queue (
    event_id INTEGER PRIMARY KEY, status TEXT NOT NULL, reason TEXT, priority INTEGER NOT NULL DEFAULT 0,
    enqueued_at TEXT NOT NULL, engine_version TEXT, requested_sig TEXT, started_at TEXT, finished_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, next_attempt_at TEXT, outcome TEXT, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_si_queue_pick ON si_queue(status, priority DESC, enqueued_at);
CREATE TABLE IF NOT EXISTS si_control (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
"""


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d):
    return d.isoformat(timespec="seconds")


def init_queue_schema(conn):
    conn.executescript(_SCHEMA)
    conn.commit()


# ------------------------------------------------------------------ control flags
def control_get(conn, key, default=None):
    try:
        r = conn.execute("SELECT value FROM si_control WHERE key=?", (key,)).fetchone()
    except Exception:
        return default
    return r[0] if r else default


def control_set(conn, key, value, now=None):
    init_queue_schema(conn)
    conn.execute("INSERT OR REPLACE INTO si_control (key, value, updated_at) VALUES (?,?,?)", (key, str(value), _iso(now or _now())))
    conn.commit()


def is_paused(conn):
    return control_get(conn, "paused", "0") == "1"


def evidence_enabled(conn):
    import os
    return control_get(conn, "evidence_enabled", "0") == "1" or os.environ.get("PAKSH_SI_EVIDENCE") == "1"


# ------------------------------------------------------------------ priority
def compute_priority(reason, updated_at, n_owners, visible, prev_uncertain, now=None):
    """Deterministic engineering priority (higher first). NOT an editorial ranking: only recency, change, breadth and unresolved
    uncertainty count; nothing about topic, politics or outlet."""
    now = now or _now()
    p = 0
    try:
        hours = (now - datetime.fromisoformat(updated_at)).total_seconds() / 3600 if updated_at else 10 ** 6
    except Exception:
        hours = 10 ** 6
    p += 300 if hours <= 24 else 200 if hours <= 72 else 100 if hours <= 168 else 0     # recently updated
    if reason in ("NEW", "MEMBERSHIP_CHANGED"):
        p += 50                                                                          # new articles joined
    if reason == "EVIDENCE_UPDATED":
        p += 30
    p += min(int(n_owners or 0), 10) * 5                                                 # publisher breadth
    if visible:
        p += 40                                                                          # currently published
    if prev_uncertain:
        p += 30                                                                          # unresolved UNCERTAIN last time
    return p


# ------------------------------------------------------------------ enqueue
def enqueue(conn, event_id, reason, priority=0, now=None, commit=True):
    """-> 'queued' | 'requeued' | 'already_queued'.  A story already QUEUED / PROCESSING / RETRY is never queued twice (its priority
    is only ever raised); a PROCESSED or FAILED story is queued again (attempts reset)."""
    now = _iso(now or _now())
    r = conn.execute("SELECT status, priority FROM si_queue WHERE event_id=?", (event_id,)).fetchone()
    if r is None:
        conn.execute("INSERT INTO si_queue (event_id, status, reason, priority, enqueued_at, engine_version, attempts, updated_at) "
                     "VALUES (?,?,?,?,?,?,0,?)", (event_id, QUEUED, reason, priority, now, si.ENGINE_VERSION, now))
        out = "queued"
    elif r[0] in (QUEUED, PROCESSING, RETRY):
        if priority > (r[1] or 0):
            conn.execute("UPDATE si_queue SET priority=?, updated_at=? WHERE event_id=?", (priority, now, event_id))
        out = "already_queued"
    else:
        conn.execute("UPDATE si_queue SET status=?, reason=?, priority=?, enqueued_at=?, engine_version=?, started_at=NULL, finished_at=NULL, "
                     "attempts=0, last_error=NULL, next_attempt_at=NULL, outcome=NULL, updated_at=? WHERE event_id=?",
                     (QUEUED, reason, priority, now, si.ENGINE_VERSION, now, event_id))
        out = "requeued"
    if commit:
        conn.commit()
    return out


_SCAN_SQL = """
SELECT * FROM (
  SELECT e.id, e.updated_at, s.engine_version AS s_engine, s.n_articles AS s_n, s.computed_at AS s_at, s.stats_json AS s_stats,
         (SELECT COUNT(*) FROM articles a WHERE a.event_id = e.id) AS n_art,
         (SELECT COUNT(DISTINCT a.source) FROM articles a WHERE a.event_id = e.id) AS n_src,
         COALESCE(json_extract(e.analysis_json, '$.content_complete'), 1) AS complete,
         {ev_col}
  FROM events e
  LEFT JOIN si_story_state s ON s.event_id = e.id
  LEFT JOIN si_queue q ON q.event_id = e.id
  WHERE e.is_demo = 0 AND e.updated_at >= ?
    AND (q.event_id IS NULL OR q.status IN ('PROCESSED', 'FAILED'))
) WHERE n_art >= 2
  AND (s_engine IS NULL OR s_engine != ? OR n_art != s_n OR ev_new OR (s_at IS NOT NULL AND updated_at > s_at)
       OR (? AND COALESCE(json_extract(s_stats, '$.evidence_plan.logic'), '') != ?
           AND COALESCE(json_extract(s_stats, '$.distinct_owners'), 0) >= ? AND COALESCE(json_extract(s_stats, '$.role_counts.UNCERTAIN'), 0) > 0))
ORDER BY updated_at DESC, id DESC
LIMIT ?
"""


def scan_and_enqueue(conn, days=DEFAULT_SCAN_DAYS, limit=DEFAULT_SCAN_LIMIT, max_enqueue=None, now=None):
    """Find stories that need processing and queue them. Bounded (`limit` candidate rows). -> {'queued': n, 'by_reason': {...}}"""
    init_queue_schema(conn)
    si.init_si_schema(conn)
    now = now or _now()
    since = _iso(now - timedelta(days=days))
    has_ev = conn.execute("SELECT 1 FROM sqlite_master WHERE name='si_evidence'").fetchone() is not None
    ev_col = ("EXISTS(SELECT 1 FROM si_evidence v JOIN articles a2 ON a2.id = v.article_id WHERE a2.event_id = e.id AND v.updated_at > s.computed_at) AS ev_new"
              if has_ev else "0 AS ev_new")
    counts, queued = {}, 0
    ev_on = 1 if evidence_enabled(conn) else 0
    rows = conn.execute(_SCAN_SQL.format(ev_col=ev_col), (since, si.ENGINE_VERSION, ev_on, si.EVIDENCE_LOGIC_VERSION, si.TRIGGER_ELIGIBLE_MIN_OWNERS, limit)).fetchall()
    for r in rows:
        if (r["n_art"] or 0) < 2:
            continue
        if r["s_engine"] is None:
            reason = "NEW"
        elif r["s_engine"] != si.ENGINE_VERSION:
            reason = "ENGINE_VERSION"
        elif r["n_art"] != r["s_n"]:
            reason = "MEMBERSHIP_CHANGED"
        elif r["ev_new"]:
            reason = "EVIDENCE_UPDATED"
        elif r["updated_at"] and r["s_at"] and r["updated_at"] > r["s_at"]:
            reason = "STORY_UPDATED"
        elif ev_on:
            reason = "EVIDENCE_PENDING"                     # evidence retrieval is on and this story has not been planned under the current logic
        else:
            continue
        prev_unc = 0
        try:
            prev_unc = json.loads(r["s_stats"] or "{}").get("role_counts", {}).get("UNCERTAIN", 0) if r["s_stats"] else 0
        except Exception:
            pass
        pr = compute_priority(reason, r["updated_at"], r["n_src"], bool(r["complete"]) and r["n_src"] >= 2, prev_unc > 0, now)
        if enqueue(conn, r["id"], reason, pr, now, commit=False) in ("queued", "requeued"):
            queued += 1
            counts[reason] = counts.get(reason, 0) + 1
            if max_enqueue and queued >= max_enqueue:
                break
    conn.commit()
    pruned = prune(conn, now)
    return {"queued": queued, "by_reason": counts, "scanned": len(rows), "pruned": pruned}


def enqueue_recent(conn, n, reason="MANUAL_RECENT", now=None):
    init_queue_schema(conn)
    ids = [r[0] for r in conn.execute("SELECT id FROM events WHERE is_demo=0 ORDER BY updated_at DESC, id DESC LIMIT ?", (n,))]
    out = {"queued": 0, "already_queued": 0}
    for eid in ids:
        res = enqueue(conn, eid, reason, 0, now, commit=False)
        out["already_queued" if res == "already_queued" else "queued"] += 1
    conn.commit()
    return out


def prune(conn, now=None):
    """Drop queue rows for stories that no longer exist (consolidation) and old PROCESSED audit rows; drop si_* rows of vanished stories."""
    now = now or _now()
    n = conn.execute("DELETE FROM si_queue WHERE event_id NOT IN (SELECT id FROM events)").rowcount
    n += conn.execute("DELETE FROM si_queue WHERE status='PROCESSED' AND finished_at < ?", (_iso(now - timedelta(days=KEEP_PROCESSED_DAYS)),)).rowcount
    for t in ("si_story_state", "si_reporting_events", "si_reporting_event_articles", "si_developments", "si_claims", "si_relationships"):
        conn.execute(f"DELETE FROM {t} WHERE event_id NOT IN (SELECT id FROM events)")
    conn.commit()
    return n


# ------------------------------------------------------------------ claim / states
def recover_stale(conn, now=None):
    now = now or _now()
    cut = _iso(now - timedelta(minutes=STALE_PROCESSING_MIN))
    n = conn.execute("UPDATE si_queue SET status='QUEUED', reason='STALE_RECOVERED', updated_at=? WHERE status='PROCESSING' AND started_at < ?",
                     (_iso(now), cut)).rowcount
    conn.commit()
    return n


def claim(conn, limit, now=None):
    now = now or _now()
    rows = conn.execute("SELECT event_id, reason, attempts FROM si_queue WHERE status='QUEUED' OR (status='RETRY' AND next_attempt_at <= ?) "
                        "ORDER BY priority DESC, enqueued_at ASC, event_id ASC LIMIT ?", (_iso(now), limit)).fetchall()
    for r in rows:
        conn.execute("UPDATE si_queue SET status='PROCESSING', started_at=?, updated_at=? WHERE event_id=?", (_iso(now), _iso(now), r["event_id"]))
    conn.commit()
    return [dict(r) for r in rows]


def _finish_ok(conn, eid, outcome, sig, now):
    conn.execute("UPDATE si_queue SET status='PROCESSED', finished_at=?, outcome=?, last_error=NULL, requested_sig=?, next_attempt_at=NULL, updated_at=? WHERE event_id=?",
                 (_iso(now), outcome, sig, _iso(now), eid))
    conn.commit()


def _finish_error(conn, eid, err, now):
    r = conn.execute("SELECT attempts FROM si_queue WHERE event_id=?", (eid,)).fetchone()
    attempts = (r[0] if r else 0) + 1
    if attempts >= MAX_ATTEMPTS:
        conn.execute("UPDATE si_queue SET status='FAILED', attempts=?, last_error=?, finished_at=?, next_attempt_at=NULL, updated_at=? WHERE event_id=?",
                     (attempts, err[:300], _iso(now), _iso(now), eid))
    else:
        nxt = now + timedelta(minutes=min(24 * 60, BACKOFF_BASE_MIN * 2 ** (attempts - 1)))
        conn.execute("UPDATE si_queue SET status='RETRY', attempts=?, last_error=?, next_attempt_at=?, updated_at=? WHERE event_id=?",
                     (attempts, err[:300], _iso(nxt), _iso(now), eid))
    conn.commit()
    return attempts


def retry_failed(conn, limit=20, now=None):
    now = now or _now()
    ids = [r[0] for r in conn.execute("SELECT event_id FROM si_queue WHERE status IN ('FAILED','RETRY') ORDER BY priority DESC, enqueued_at LIMIT ?", (limit,))]
    for eid in ids:
        conn.execute("UPDATE si_queue SET status='QUEUED', attempts=0, next_attempt_at=NULL, reason='MANUAL_RETRY', updated_at=? WHERE event_id=?", (_iso(now), eid))
    conn.commit()
    return len(ids)


# ------------------------------------------------------------------ processing
def _cached_evidence(conn, article_ids):
    """{article_id: usable cached text}. Read-only: the queue never fetches here."""
    import evidence_retrieval as er
    out = {}
    for aid in article_ids:
        t = er.usable_text(er.cache_get(conn, aid))
        if t:
            out[aid] = t
    return out


def process_one(conn, eid, rows, owner_of, pub_names, budget=None, allow_fetch=False, now=None):
    """Analyse one story (metadata + cached evidence, plus budgeted fetching when allowed) and persist it.
    -> outcome dict {'outcome': 'processed'|'unchanged'|'too_small', ...}. Raises on failure (the caller records it)."""
    import evidence_retrieval as er
    now = now or _now()
    if len(rows) < 2:
        return {"outcome": "too_small"}
    evidence = _cached_evidence(conn, [r["id"] for r in rows])
    sig = si.input_signature(rows, evidence)
    st = conn.execute("SELECT engine_version, input_sig, stats_json FROM si_story_state WHERE event_id=?", (eid,)).fetchone()
    plan_done = True
    if allow_fetch and st:
        try:
            ep = json.loads(st[2] or "{}").get("evidence_plan") or {}
        except Exception:
            ep = {}
        plan_done = ep.get("logic") == si.EVIDENCE_LOGIC_VERSION and ep.get("complete") is True     # fetching may still be owed
    if st and (st[0], st[1]) == (si.ENGINE_VERSION, sig) and plan_done:
        conn.execute("UPDATE si_story_state SET computed_at=? WHERE event_id=?", (_iso(now), eid))     # verified current as of now
        conn.commit()
        return {"outcome": "unchanged", "sig": sig}
    result = si.analyze_story(rows, owner_of, pub_names, evidence=evidence)
    plan_info = {"decisions": {}, "actions": {}}
    if allow_fetch and budget is not None:
        urls = {r["id"]: r.get("url") for r in rows}
        plan, decisions = si.plan_evidence(result, urls)
        plan_info["decisions"] = decisions
        fetched_new = False
        by_id = {r["id"]: r for r in rows}
        for aid, why in plan:
            row, action = er.get_evidence(conn, {"id": aid, "url": urls.get(aid)}, budget=budget, story_id=eid)
            key = action.split(":")[0] if action.startswith("NO_FETCH") else action
            plan_info["actions"][action if action.startswith("NO_FETCH") else key] = plan_info["actions"].get(action if action.startswith("NO_FETCH") else key, 0) + 1
            t = er.usable_text(row)
            if t and aid not in evidence:
                evidence[aid] = t
                fetched_new = True
        if fetched_new:
            sig = si.input_signature(rows, evidence)
            result = si.analyze_story(rows, owner_of, pub_names, evidence=evidence)
    if allow_fetch:                                       # only a story that was actually planned is marked planned
        plan_info["logic"] = si.EVIDENCE_LOGIC_VERSION
        plan_info["complete"] = not any(k.startswith("NO_FETCH:budget") for k in plan_info["actions"])
        result["stats"]["evidence_plan"] = plan_info
    si.persist_story(conn, eid, result, sig, now=_iso(now))
    return {"outcome": "processed", "sig": sig, "stats": result["stats"], "plan": plan_info}


def process_queue(conn, limit=200, budget_s=180, allow_evidence=None, fetch_budget=None, now=None):
    """Process up to `limit` queued stories within `budget_s`. Never resets the queue; unfinished stories stay queued;
    a failing story is recorded and the run continues."""
    from sources import OWNER_BY_SOURCE
    import evidence_retrieval as er
    owner_of = lambda n: OWNER_BY_SOURCE.get(n, n)
    t0 = time.time()
    init_queue_schema(conn)
    si.init_si_schema(conn)
    if is_paused(conn):
        return {"paused": True}
    injected = now is not None                                        # tests inject a clock; production reads the real one per story
    clock = (lambda: now) if injected else _now
    now = clock()
    recovered = recover_stale(conn, now)
    allow = evidence_enabled(conn) if allow_evidence is None else allow_evidence
    budget = fetch_budget or (er.FetchBudget(max_fetches=int(control_get(conn, "evidence_max_fetches", 30)), max_seconds=min(150.0, budget_s)) if allow else None)
    claimed = claim(conn, limit, now)
    by_event = {c["event_id"]: c for c in claimed}
    rows_by = si._load_rows(conn, list(by_event))
    try:
        si._attach_vectors({e: rows_by.get(e, []) for e in by_event})
    except Exception as e:                                           # vectors are optional: text-only analysis still works
        print(f"  si_queue: vectors unavailable ({type(e).__name__}: {e}); continuing text-only")
    pub_names = si._publisher_names()
    out = {"claimed": len(claimed), "processed": 0, "unchanged": 0, "too_small": 0, "failed": 0, "returned_to_queue": 0,
           "recovered_stale": recovered, "evidence": allow}
    for i, c in enumerate(claimed):
        eid = c["event_id"]
        if time.time() - t0 > budget_s:                              # budget spent: put the rest back, untouched and un-counted
            for c2 in claimed[i:]:
                conn.execute("UPDATE si_queue SET status='QUEUED', started_at=NULL, updated_at=? WHERE event_id=?", (_iso(clock()), c2["event_id"]))
                out["returned_to_queue"] += 1
            conn.commit()
            break
        try:
            res = process_one(conn, eid, rows_by.get(eid, []), owner_of, pub_names, budget=budget, allow_fetch=allow, now=clock())
            _finish_ok(conn, eid, res["outcome"], res.get("sig"), clock())
            out[res["outcome"]] += 1
        except Exception as e:                                        # noqa: BLE001 - one bad story never stops the run
            try:
                conn.rollback()
            except Exception:
                pass
            _finish_error(conn, eid, f"{type(e).__name__}: {e}", clock())
            out["failed"] += 1
    out["seconds"] = round(time.time() - t0, 1)
    if budget is not None:
        out["fetch"] = {"fetches": budget.fetches, "requests": budget.requests, "bytes": budget.bytes}
    return out


# ------------------------------------------------------------------ pipeline hook
def run_cycle(limit=200, budget_s=180, scan_days=DEFAULT_SCAN_DAYS, scan_limit=DEFAULT_SCAN_LIMIT):
    """The nightly step: update the queue, then process a bounded slice. Never raises."""
    try:
        import database
        conn = database.get_connection()
        try:
            init_queue_schema(conn)
            if is_paused(conn):
                return {"paused": True}
            scan = scan_and_enqueue(conn, days=scan_days, limit=scan_limit)
            proc = process_queue(conn, limit=limit, budget_s=budget_s)
            return {"scan": scan, "process": proc, "queue": queue_counts(conn)}
        finally:
            conn.close()
    except Exception as e:                                            # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------ inspection
def queue_counts(conn):
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM si_queue GROUP BY 1")}
    except Exception:
        return {}


def queue_status(conn):
    init_queue_schema(conn)
    out = {"counts": queue_counts(conn), "paused": is_paused(conn), "evidence_enabled": evidence_enabled(conn), "engine_version": si.ENGINE_VERSION}
    out["by_reason"] = {r[0]: r[1] for r in conn.execute("SELECT reason, COUNT(*) FROM si_queue WHERE status IN ('QUEUED','RETRY') GROUP BY 1")}
    r = conn.execute("SELECT MIN(enqueued_at), MAX(priority) FROM si_queue WHERE status='QUEUED'").fetchone()
    out["oldest_queued"], out["top_priority"] = r[0], r[1]
    out["failed"] = [dict(x) for x in conn.execute("SELECT event_id, attempts, last_error, updated_at FROM si_queue WHERE status IN ('FAILED','RETRY') ORDER BY updated_at DESC LIMIT 5")]
    out["stories_with_state"] = conn.execute("SELECT COUNT(*) FROM si_story_state").fetchone()[0]
    out["state_by_engine"] = {r[0]: r[1] for r in conn.execute("SELECT engine_version, COUNT(*) FROM si_story_state GROUP BY 1")}
    try:
        import evidence_retrieval as er
        out["evidence_cache"] = er.cache_stats(conn)
    except Exception:
        pass
    return out


def inspect_story(conn, event_id):
    init_queue_schema(conn)
    q = conn.execute("SELECT * FROM si_queue WHERE event_id=?", (event_id,)).fetchone()
    s = conn.execute("SELECT engine_version, input_sig, n_articles, computed_at, stats_json FROM si_story_state WHERE event_id=?", (event_id,)).fetchone()
    import story_graph as sg
    g = sg.StoryGraph(conn, event_id)
    return {"queue": dict(q) if q else None, "state": ({**dict(s), "stats": json.loads(s["stats_json"] or "{}")} if s else None), "summary": g.summary()}


# ------------------------------------------------------------------ CLI (dispatched from story_intelligence.py)
def cli(argv):
    import argparse
    import database
    import runlocked
    ap = argparse.ArgumentParser(prog="story_intelligence.py", description="Story Intelligence queue operations")
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("queue", help="show the queue")
    q.add_argument("--status", action="store_true")
    q.add_argument("--list", action="store_true")
    q.add_argument("--state", default=None)
    q.add_argument("--limit", type=int, default=20)
    e = sp.add_parser("enqueue", help="queue stories")
    e.add_argument("--event", type=int, action="append")
    e.add_argument("--recent", type=int)
    e.add_argument("--scan", action="store_true", help="queue everything that changed (same logic the nightly uses)")
    e.add_argument("--days", type=int, default=DEFAULT_SCAN_DAYS)
    e.add_argument("--limit", type=int, default=DEFAULT_SCAN_LIMIT)
    e.add_argument("--engine-version", action="store_true", help="queue stories processed by another engine version")
    p = sp.add_parser("process", help="process a bounded number of queued stories")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--budget", type=float, default=180)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--evidence", action="store_true", help="allow evidence fetching for this run")
    g.add_argument("--no-evidence", action="store_true")
    r = sp.add_parser("retry", help="re-queue failed / retrying stories")
    r.add_argument("--limit", type=int, default=20)
    sp.add_parser("pause")
    sp.add_parser("resume")
    i = sp.add_parser("inspect", help="one story: queue row, state, graph summary")
    i.add_argument("--event", type=int, required=True)
    ev = sp.add_parser("evidence", help="evidence retrieval switch / cache statistics")
    ev.add_argument("--enable", action="store_true")
    ev.add_argument("--disable", action="store_true")
    ev.add_argument("--max-fetches", type=int)
    a = ap.parse_args(argv)
    conn = database.get_connection()
    init_queue_schema(conn)
    writes = a.cmd in ("enqueue", "process", "retry", "pause", "resume", "evidence") and not (a.cmd == "evidence" and not (a.enable or a.disable or a.max_fetches))
    locked = False
    if writes:
        if not runlocked.acquire("story-intelligence-" + a.cmd):
            print("another pipeline job holds the lock; try again later")
            return 3
        locked = True
    try:
        if a.cmd == "queue":
            if a.list:
                sql, args = "SELECT event_id, status, reason, priority, attempts, enqueued_at, finished_at, outcome, last_error FROM si_queue", ()
                if a.state:
                    sql, args = sql + " WHERE status=?", (a.state.upper(),)
                for row in conn.execute(sql + " ORDER BY priority DESC, enqueued_at LIMIT ?", args + (a.limit,)):
                    print(dict(row))
            else:
                print(json.dumps(queue_status(conn), indent=1, default=str))
        elif a.cmd == "enqueue":
            if a.event:
                print({eid: enqueue(conn, eid, "MANUAL", 1000) for eid in a.event})
            if a.recent:
                print(enqueue_recent(conn, a.recent))
            if a.scan or a.engine_version:
                print(scan_and_enqueue(conn, days=a.days, limit=a.limit))
        elif a.cmd == "process":
            print(process_queue(conn, limit=a.limit, budget_s=a.budget, allow_evidence=True if a.evidence else (False if a.no_evidence else None)))
        elif a.cmd == "retry":
            print({"requeued": retry_failed(conn, a.limit)})
        elif a.cmd == "pause":
            control_set(conn, "paused", 1)
            print("paused")
        elif a.cmd == "resume":
            control_set(conn, "paused", 0)
            print("resumed")
        elif a.cmd == "inspect":
            print(json.dumps(inspect_story(conn, a.event), indent=1, default=str))
        elif a.cmd == "evidence":
            if a.enable:
                control_set(conn, "evidence_enabled", 1)
            if a.disable:
                control_set(conn, "evidence_enabled", 0)
            if a.max_fetches:
                control_set(conn, "evidence_max_fetches", a.max_fetches)
            print(json.dumps({"evidence_enabled": evidence_enabled(conn), "max_fetches": control_get(conn, "evidence_max_fetches", "30"),
                              "cache": queue_status(conn).get("evidence_cache")}, indent=1, default=str))
        return 0
    finally:
        if locked:
            runlocked.release()
        conn.close()
