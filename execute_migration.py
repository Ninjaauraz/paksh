"""
execute_migration.py - Paksh 2.0A: the REAL executable SQLite -> Supabase migration.

migrate_to_supabase.py (Phase 1) only ever EMITS SQL text files, because no execution
credential existed in this repo's environment at the time. .env.local now provides
SUPABASE_URL / SUPABASE_SECRET_KEY (a privileged PostgREST key), so this module adds
the missing "how to actually send it" layer - batched PostgREST upserts, retries,
checkpointing - WITHOUT reinterpreting the data model.

Reuses, unchanged, from migrate_to_supabase.py:
    _event_row(sqlite_row)      -> the exact per-event Supabase row dict
    _outlet_rows(referenced)    -> the exact per-outlet Supabase row dict
    TOPIC_HI                    -> the same topic-name -> Hindi-name map

Everything here is additive: migrate_to_supabase.py is untouched, its SQL-emission
path still works exactly as before for small MCP-relayed batches.

SECURITY
--------
SUPABASE_SECRET_KEY is read from .env.local into a local dict held only in this
process's memory (never os.environ, never printed, never logged, never written to
the checkpoint file or any output file). Every error path is careful to surface
only the SERVER's response body, never our own request headers.

IDEMPOTENCY
-----------
Every write is a PostgREST upsert (Prefer: resolution=merge-duplicates) on the
same primary/natural key migrate_to_supabase.py's SQL ON CONFLICT clauses already
use (id for events/articles/storylines, name for topics/outlets) - re-running any
batch, or the whole script, converges to the same end state.

USAGE
-----
    py execute_migration.py --single-event 15944        # Step 1 write-path proof
    py execute_migration.py --stage topics,outlets       # small, cheap stages
    py execute_migration.py --stage events,articles --limit 50   # first test batch
    py execute_migration.py --stage events,articles --limit 0    # full corpus
    py execute_migration.py --resume                     # continue from checkpoint
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

import database
from migrate_to_supabase import _event_row, _outlet_rows, TOPIC_HI

try:
    from storylines import build_storylines
except ImportError:
    build_storylines = None

CHECKPOINT_FILE = Path(__file__).with_name(".migration_checkpoint.json")
ENV_LOCAL = Path(__file__).with_name(".env.local")


# --------------------------------------------------------------- credentials

def _load_env_local():
    """Reads .env.local into a dict held only in memory. Never prints, never
    touches os.environ (so nothing downstream can accidentally dump it)."""
    if not ENV_LOCAL.exists():
        raise RuntimeError(".env.local not found - cannot proceed without credentials")
    out = {}
    for line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY") if not out.get(k)]
    if missing:
        raise RuntimeError(f".env.local is missing: {', '.join(missing)}")
    return out


# --------------------------------------------------------------- PostgREST writer

class SupabaseWriter:
    def __init__(self, env):
        self._url = env["SUPABASE_URL"].rstrip("/")
        self._key = env["SUPABASE_SECRET_KEY"]
        self._session = requests.Session()

    def _headers(self, prefer):
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        }

    def upsert(self, table, rows, on_conflict="id", max_retries=4, timeout=60):
        """POST rows (list of dicts) as one idempotent upsert batch.
        Retries transient failures (network error, 429, 5xx) with exponential
        backoff. A 4xx is NOT retried - raised immediately as a real data/schema
        problem, not treated as flakiness. Never includes secret values in any
        exception message - only the server's own response body."""
        if not rows:
            return {"count": 0, "attempts": 0, "bytes": 0}
        url = f"{self._url}/rest/v1/{table}?on_conflict={on_conflict}"
        prefer = "resolution=merge-duplicates,return=minimal"
        body = json.dumps(rows, ensure_ascii=False).encode("utf-8")
        attempt = 0
        while True:
            attempt += 1
            try:
                r = self._session.post(url, headers=self._headers(prefer), data=body, timeout=timeout)
            except requests.RequestException as e:
                if attempt > max_retries:
                    raise RuntimeError(f"{table}: network failure after {attempt} attempt(s): {type(e).__name__}") from e
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code in (200, 201, 204):
                return {"count": len(rows), "attempts": attempt, "bytes": len(body)}
            if r.status_code in (429, 500, 502, 503, 504) and attempt <= max_retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"{table}: HTTP {r.status_code} after {attempt} attempt(s): {r.text[:500]}")

    def select_one(self, table, filters, timeout=30):
        """Read-only GET, for the write-path proof / spot checks. filters is a
        dict of PostgREST query params, e.g. {'id': 'eq.15944'}."""
        url = f"{self._url}/rest/v1/{table}"
        r = self._session.get(url, headers=self._headers(""), params=filters, timeout=timeout)
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None


# --------------------------------------------------------------- checkpoint

def _load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    return {"migration_start": None, "stages": {}}


def _save_checkpoint(cp):
    # Never contains credentials - only ids/counts/timestamps/status strings.
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")


def _batches(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# --------------------------------------------------------------- dict shaping (topics/storylines)
# Reuses TOPIC_HI (imported, unchanged) - just returns dicts instead of SQL text,
# since PostgREST wants JSON, not migrate_to_supabase.py's SQL strings.

def _topic_rows(names):
    return [{"name": n, "name_hi": TOPIC_HI.get(n)} for n in sorted(names) if n]


def _storyline_rows(storylines, touched_ids):
    return [{
        "id": s["id"], "title": s.get("title"), "title_hi": s.get("title_hi"),
        "topic": s.get("topic"), "region": s.get("region"), "n_events": s.get("n_events"),
        "starts_at": s.get("start"), "ends_at": s.get("end"), "updated_at": s.get("updated_at"),
    } for s in storylines if s["id"] in touched_ids]


# --------------------------------------------------------------- Step 1: single-event proof

def single_event_test(writer, event_id):
    print(f"=== Step 1: write-path proof for event {event_id} ===")
    conn = database.get_connection()
    row = conn.execute(
        "SELECT id, title, analysis_json, is_demo, created_at FROM events WHERE id=?", (event_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise RuntimeError(f"event {event_id} not found in SQLite")
    sqlite_row = _event_row(row)

    if build_storylines is not None:
        try:
            all_events = database.get_all_events()
            _, story_map = build_storylines(all_events)
            sqlite_row["storyline_id"] = story_map.get(event_id)
        except Exception as e:
            print(f"  (storyline linking skipped: {e})")

    before = writer.select_one("events", {"id": f"eq.{event_id}", "select": "*"})
    print(f"  Supabase BEFORE: {'found' if before else 'not found'}"
          + (f", synced_at={before.get('synced_at')}" if before else ""))

    result = writer.upsert("events", [sqlite_row], on_conflict="id")
    print(f"  upsert result: {result['count']} row(s), {result['attempts']} attempt(s), {result['bytes']} bytes")

    after = writer.select_one("events", {"id": f"eq.{event_id}", "select": "*"})
    if after is None:
        raise RuntimeError("event not found in Supabase immediately after upsert")

    # field-level comparison
    compare_fields = ("title", "title_hi", "summary", "summary_hi", "topic", "region",
                       "lean_left", "lean_center", "lean_right", "dominant_lean",
                       "dominant_pct", "blindspot_side", "blindspot_pct", "storyline_id")
    mismatches = []
    for f in compare_fields:
        a, b = sqlite_row.get(f), after.get(f)
        if a != b:
            mismatches.append((f, a, b))
    print(f"  field comparison ({len(compare_fields)} fields): "
          + ("ALL MATCH" if not mismatches else f"{len(mismatches)} MISMATCH(ES)"))
    for f, a, b in mismatches:
        print(f"    MISMATCH {f}: sqlite={a!r} supabase={b!r}")
    print(f"  synced_at after write: {after.get('synced_at')}")
    return not mismatches


# --------------------------------------------------------------- staged bulk migration

def _now_iso():
    return datetime.utcnow().isoformat()


def migrate_topics(writer, event_rows, storylines_out, cp):
    t0 = time.time()
    names = {r["topic"] for r in event_rows} | {s.get("topic") for s in storylines_out if s.get("topic")} | set(TOPIC_HI.keys())
    names.discard(None)
    rows = _topic_rows(names)
    res = writer.upsert("topics", rows, on_conflict="name")
    dt = time.time() - t0
    print(f"  topics: {res['count']} rows, {res['attempts']} attempt(s), {dt:.1f}s")
    cp["stages"]["topics"] = {"status": "done", "count": res["count"], "duration_s": round(dt, 1),
                               "timestamp": _now_iso()}
    _save_checkpoint(cp)
    return res["count"]


def migrate_outlets(writer, referenced_names, cp):
    t0 = time.time()
    rows = _outlet_rows(referenced_names)
    for r in rows:
        r["updated_at"] = _now_iso()   # column has DEFAULT now() but that only fires on INSERT
    res = writer.upsert("outlets", rows, on_conflict="name")
    dt = time.time() - t0
    print(f"  outlets: {res['count']} rows ({sum(1 for r in rows if r['is_curated'])} curated, "
          f"{sum(1 for r in rows if not r['is_curated'])} verified-registry), "
          f"{res['attempts']} attempt(s), {dt:.1f}s")
    cp["stages"]["outlets"] = {"status": "done", "count": res["count"], "duration_s": round(dt, 1),
                                "timestamp": _now_iso()}
    _save_checkpoint(cp)
    return res["count"]


def migrate_storylines(writer, storylines_out, touched_ids, cp):
    t0 = time.time()
    rows = _storyline_rows(storylines_out, touched_ids)
    res = writer.upsert("storylines", rows, on_conflict="id")
    dt = time.time() - t0
    print(f"  storylines: {res['count']} rows (of {len(storylines_out)} total; "
          f"{len(touched_ids)} touch a migrated event), {res['attempts']} attempt(s), {dt:.1f}s")
    cp["stages"]["storylines"] = {"status": "done", "count": res["count"], "duration_s": round(dt, 1),
                                   "timestamp": _now_iso()}
    _save_checkpoint(cp)
    return res["count"]


def migrate_events(writer, event_rows, cp, batch_size):
    """Batched, checkpointed, resumable. event_rows must already be sorted by id
    ascending (deterministic order) so checkpoint batch-index resume is safe."""
    stage = cp["stages"].setdefault("events", {"status": "in_progress", "batches": [],
                                                "completed_count": 0, "failed_ids": []})
    done_batches = {b["index"] for b in stage["batches"] if b["status"] == "done"}
    batches = list(_batches(event_rows, batch_size))
    total = len(event_rows)
    print(f"  events: {total} rows in {len(batches)} batch(es) of <= {batch_size} "
          f"({len(done_batches)} already done, resuming)" if done_batches else
          f"  events: {total} rows in {len(batches)} batch(es) of <= {batch_size}")
    for i, batch in enumerate(batches):
        if i in done_batches:
            continue
        for r in batch:
            r["synced_at"] = _now_iso()   # DEFAULT now() only fires on INSERT, not on UPDATE
        t0 = time.time()
        try:
            res = writer.upsert("events", batch, on_conflict="id")
        except Exception as e:
            dt = time.time() - t0
            stage["batches"].append({"index": i, "start_id": batch[0]["id"], "end_id": batch[-1]["id"],
                                      "count": len(batch), "status": "FAILED", "error": str(e)[:300],
                                      "duration_s": round(dt, 1), "timestamp": _now_iso()})
            stage["status"] = "FAILED"
            _save_checkpoint(cp)
            print(f"    batch {i} FAILED ({batch[0]['id']}..{batch[-1]['id']}): {e}")
            raise
        dt = time.time() - t0
        stage["batches"].append({"index": i, "start_id": batch[0]["id"], "end_id": batch[-1]["id"],
                                  "count": res["count"], "status": "done", "attempts": res["attempts"],
                                  "duration_s": round(dt, 1), "timestamp": _now_iso()})
        stage["completed_count"] += res["count"]
        _save_checkpoint(cp)
        if i % 10 == 0 or i == len(batches) - 1:
            print(f"    batch {i+1}/{len(batches)}: ids {batch[0]['id']}..{batch[-1]['id']}, "
                  f"{res['count']} rows, {dt:.1f}s, {res['attempts']} attempt(s)")
    stage["status"] = "done"
    _save_checkpoint(cp)
    return stage["completed_count"]


def migrate_articles(writer, event_ids, cp, batch_size):
    stage = cp["stages"].setdefault("articles", {"status": "in_progress", "batches": [],
                                                  "completed_count": 0})
    done_batches = {b["index"] for b in stage["batches"] if b["status"] == "done"}
    conn = database.get_connection()
    ph = ",".join(str(i) for i in event_ids)
    art_rows = [dict(r) for r in conn.execute(
        f"SELECT id, event_id, source, language, title, url, summary, image_url, published, fetched_at "
        f"FROM articles WHERE event_id IN ({ph}) ORDER BY id ASC"
    ).fetchall()] if event_ids else []
    conn.close()
    batches = list(_batches(art_rows, batch_size))
    print(f"  articles: {len(art_rows)} rows in {len(batches)} batch(es) of <= {batch_size} "
          f"({len(done_batches)} already done, resuming)" if done_batches else
          f"  articles: {len(art_rows)} rows in {len(batches)} batch(es) of <= {batch_size}")
    for i, batch in enumerate(batches):
        if i in done_batches:
            continue
        t0 = time.time()
        try:
            res = writer.upsert("articles", batch, on_conflict="id")
        except Exception as e:
            dt = time.time() - t0
            stage["batches"].append({"index": i, "start_id": batch[0]["id"], "end_id": batch[-1]["id"],
                                      "count": len(batch), "status": "FAILED", "error": str(e)[:300],
                                      "duration_s": round(dt, 1), "timestamp": _now_iso()})
            stage["status"] = "FAILED"
            _save_checkpoint(cp)
            print(f"    batch {i} FAILED ({batch[0]['id']}..{batch[-1]['id']}): {e}")
            raise
        dt = time.time() - t0
        stage["batches"].append({"index": i, "start_id": batch[0]["id"], "end_id": batch[-1]["id"],
                                  "count": res["count"], "status": "done", "attempts": res["attempts"],
                                  "duration_s": round(dt, 1), "timestamp": _now_iso()})
        stage["completed_count"] += res["count"]
        _save_checkpoint(cp)
        if i % 20 == 0 or i == len(batches) - 1:
            print(f"    batch {i+1}/{len(batches)}: ids {batch[0]['id']}..{batch[-1]['id']}, "
                  f"{res['count']} rows, {dt:.1f}s, {res['attempts']} attempt(s)")
    stage["status"] = "done"
    _save_checkpoint(cp)
    return stage["completed_count"]


def run_stages(writer, stages, limit, event_batch, article_batch, resume):
    cp = _load_checkpoint() if resume else {"migration_start": None, "stages": {}}
    if cp.get("migration_start") is None:
        cp["migration_start"] = _now_iso()
    cp.setdefault("stages", {})
    print(f"=== migration_start snapshot: {cp['migration_start']} ===")

    conn = database.get_connection()
    q = "SELECT id, title, analysis_json, is_demo, created_at FROM events WHERE COALESCE(is_demo,0)=0 ORDER BY id ASC"
    if limit:
        # deterministic snapshot: most-recent-N by id, but batches still process ascending
        all_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM events WHERE COALESCE(is_demo,0)=0 ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]
        id_set = set(all_ids)
        sqlite_rows = [r for r in conn.execute(q).fetchall() if r["id"] in id_set]
    else:
        sqlite_rows = conn.execute(q).fetchall()
    conn.close()
    event_rows = [_event_row(r) for r in sqlite_rows]
    event_ids = [r["id"] for r in event_rows]
    print(f"  snapshot: {len(event_rows)} non-demo event(s) (limit={limit or 'ALL'})")
    cp["snapshot_event_count"] = len(event_rows)
    cp["snapshot_min_id"] = min(event_ids) if event_ids else None
    cp["snapshot_max_id"] = max(event_ids) if event_ids else None

    storylines_out, touched = [], set()
    if build_storylines is not None:
        try:
            t0 = time.time()
            all_events = database.get_all_events()
            storylines_out, story_map = build_storylines(all_events)
            for r in event_rows:
                r["storyline_id"] = story_map.get(r["id"])
            touched = {sid for eid, sid in story_map.items() if eid in set(event_ids)}
            print(f"  storylines computed: {len(storylines_out)} total, {len(touched)} touch this snapshot "
                  f"({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  storylines: skipped ({e})")

    referenced = set()
    for r in event_rows:
        for s in r["sources"]:
            referenced.add(s["source"])

    if "topics" in stages:
        print("=== topics ===")
        migrate_topics(writer, event_rows, storylines_out, cp)
    if "outlets" in stages:
        print("=== outlets ===")
        migrate_outlets(writer, referenced, cp)
    if "storylines" in stages:
        print("=== storylines ===")
        migrate_storylines(writer, storylines_out, touched, cp)
    if "events" in stages:
        print("=== events ===")
        migrate_events(writer, event_rows, cp, event_batch)
    if "articles" in stages:
        print("=== articles ===")
        migrate_articles(writer, event_ids, cp, article_batch)

    cp["migration_end"] = _now_iso()
    _save_checkpoint(cp)
    print(f"\n=== done. checkpoint: {CHECKPOINT_FILE} ===")
    return cp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--single-event", type=int, help="Step 1: idempotent write-path proof for one event id")
    ap.add_argument("--stage", help="comma-separated: topics,outlets,storylines,events,articles")
    ap.add_argument("--limit", type=int, default=0, help="most recent N non-demo events (0 = ALL)")
    ap.add_argument("--event-batch", type=int, default=50)
    ap.add_argument("--article-batch", type=int, default=500)
    ap.add_argument("--resume", action="store_true", help="continue from .migration_checkpoint.json")
    args = ap.parse_args()

    env = _load_env_local()
    writer = SupabaseWriter(env)

    if args.single_event:
        ok = single_event_test(writer, args.single_event)
        sys.exit(0 if ok else 1)
    elif args.stage:
        stages = set(s.strip() for s in args.stage.split(","))
        run_stages(writer, stages, args.limit, args.event_batch, args.article_batch, args.resume)
    else:
        print("Nothing to do - pass --single-event <id> or --stage <...>")
