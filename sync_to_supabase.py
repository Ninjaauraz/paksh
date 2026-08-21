"""
sync_to_supabase.py - Paksh 2.0 Phase 1.5: incremental SQLite -> Supabase sync.

The ongoing counterpart to migrate_to_supabase.py's one-time backfill. Reuses
its exact row-shaping/SQL-building functions (event/article/outlet/storyline
rows) rather than duplicating them - the two scripts must never drift apart on
what a "correct" Supabase row looks like.

SYNC BOUNDARY (Phase 1.5 objective 4)
--------------------------------------
Content becomes "sufficiently final to sync" at exactly the point
database.insert_event() / database.update_event() are called - i.e. after
analyze.py (or any maintenance script: reframe.py, recount_migrate.py,
consolidate.py, backfill*.py) has written a real change to SQLite. Rather than
add a Supabase write to each of those callers individually ("blindly add
writes to every function" - explicitly not wanted), this script is the ONE
place that boundary is acted on: it reads database.py's new `updated_at`
column (see database.py's init_db()/update_event() docstrings) to find
exactly what changed, and nothing else needs to know Supabase exists.

WHY `updated_at`, NOT `created_at`
------------------------------------
created_at is deliberately preserved across in-place edits (reframe.py,
recount_migrate.py both pass bump_created=False specifically so the feed order
doesn't reshuffle) - a --since query against created_at would silently MISS
every content fix that doesn't also move an event to the top of the feed.
`updated_at` (added this phase) is a genuine, unconditional "this row changed"
signal, read via database.get_event_ids_updated_since().

WHAT THIS SCRIPT DOES NOT DO
-------------------------------
* It does not auto-discover deletions by diffing the full SQLite and Supabase
  corpora - that needs a live query against Supabase this environment can't
  make without relaying bulk IDs through model context, and more importantly,
  auto-diffing is exactly the kind of implicit destructive inference the
  Phase 1.5 brief explicitly warns against ("do not automatically delete...
  unless sync semantics explicitly support it").
* Instead, deletions are 100% EXPLICIT: consolidate.py already prints exactly
  which event ids it deletes when merging duplicates. Pass those same ids to
  --deleted-events and this script emits the corresponding DELETE statements
  for exactly those ids - never inferred, never guessed.
* Article reassignment (an article's event_id changes during a merge) needs NO
  special-case code: re-syncing the surviving event re-selects its current
  member articles from SQLite fresh, and the idempotent UPSERT on articles.id
  simply moves that article's event_id in Supabase too.

USAGE
-----
  py sync_to_supabase.py --since 2026-08-19T00:00:00 --emit-dir sync_sql
  py sync_to_supabase.py --events 15944,15945 --emit-dir sync_sql
  py sync_to_supabase.py --deleted-events 15200,15201 --emit-dir sync_sql
  py sync_to_supabase.py --since <last-sync-watermark> --record-watermark

Exactly like migrate_to_supabase.py, this EMITS SQL FILES - it does not open a
network connection itself (no Postgres driver/credential is available in this
repo's environment; see the Phase 1.5 report for what that requires to change).
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import database
from migrate_to_supabase import (
    _event_row, _outlet_rows, _batches, _write,
    build_events_sql, build_articles_sql, build_outlets_sql,
    build_topics_sql, build_storylines_sql,
)

try:
    from storylines import build_storylines
except ImportError:
    build_storylines = None

WATERMARK_FILE = Path(__file__).with_name(".supabase_sync_watermark")


def _build_deletes(ids, table):
    if not ids:
        return []
    ph = ", ".join(str(int(i)) for i in ids)
    return [f"DELETE FROM public.{table} WHERE id IN ({ph});"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="ISO timestamp; sync events with updated_at >= this")
    ap.add_argument("--events", help="comma-separated explicit event ids to sync")
    ap.add_argument("--deleted-events", help="comma-separated event ids to DELETE from Supabase "
                     "(pass ids consolidate.py itself reported deleting - never auto-discovered)")
    ap.add_argument("--emit-dir", default="sync_sql")
    ap.add_argument("--record-watermark", action="store_true",
                     help="on success, write 'now' to .supabase_sync_watermark for the next --since run")
    ap.add_argument("--batch-events", type=int, default=10)
    ap.add_argument("--batch-articles", type=int, default=200)
    args = ap.parse_args()

    if not (args.since or args.events or args.deleted_events):
        ap.error("pass at least one of --since, --events, --deleted-events")

    emit_dir = Path(args.emit_dir)
    emit_dir.mkdir(parents=True, exist_ok=True)
    database.init_db()

    sync_started_at = datetime.utcnow().isoformat()

    # ---- deletions: 100% explicit, never inferred ----
    if args.deleted_events:
        del_ids = [int(x) for x in args.deleted_events.split(",") if x.strip()]
        print(f"=== deletions: {len(del_ids)} explicit event id(s) ===")
        _write(emit_dir, "00_deletes_events.sql", _build_deletes(del_ids, "events"))
        _write(emit_dir, "00_deletes_articles.sql", _build_deletes(del_ids, "articles"))
        # events.id ON DELETE has no cascade defined for articles (event_id references
        # events(id) ON DELETE SET NULL - see the schema), so a deleted event's articles
        # become orphaned (event_id NULL) rather than vanishing; deleting them explicitly
        # here keeps the article table from accumulating orphans from real deletions.

    # ---- find what changed ----
    ids = set()
    if args.events:
        ids |= {int(x) for x in args.events.split(",") if x.strip()}
    if args.since:
        since_ids = database.get_event_ids_updated_since(args.since)
        print(f"=== --since {args.since}: {len(since_ids)} event(s) with updated_at >= that ===")
        ids |= set(since_ids)

    if not ids:
        print("Nothing to sync (no matching events).")
        if args.record_watermark:
            WATERMARK_FILE.write_text(sync_started_at, encoding="utf-8")
        return

    conn = database.get_connection()
    q = ",".join(str(i) for i in ids)
    event_sql_rows = conn.execute(
        f"SELECT id, title, analysis_json, is_demo, created_at FROM events WHERE id IN ({q})"
    ).fetchall()
    print(f"=== syncing {len(event_sql_rows)} of {len(ids)} requested event id(s) "
          f"({len(ids) - len(event_sql_rows)} not found - already deleted?) ===")
    event_rows = [_event_row(r) for r in event_sql_rows]
    synced_ids = {r["id"] for r in event_rows}

    # storylines: recomputed over the FULL corpus (cheap - reuses cached embeddings, no
    # new LLM/embedding calls), same as migrate_to_supabase.py, so a synced event's
    # storyline_id is never stale even if its saga grew from events outside this batch.
    storyline_map = {}
    storylines_out, touched = [], set()
    if build_storylines is not None:
        try:
            all_events = database.get_all_events()
            storylines_out, storyline_map = build_storylines(all_events)
            for r in event_rows:
                r["storyline_id"] = storyline_map.get(r["id"])
            touched = {sid for eid, sid in storyline_map.items() if eid in synced_ids}
        except Exception as e:
            print(f"  storylines: skipped ({e})")

    topic_names = {r["topic"] for r in event_rows} | {s.get("topic") for s in storylines_out if s.get("topic")}
    topic_names.discard(None)
    _write(emit_dir, "01_topics.sql", build_topics_sql(topic_names))
    for i, batch in enumerate(_batches(storylines_out, 500)):
        _write(emit_dir, f"02_storylines_{i:03d}.sql", build_storylines_sql(batch, touched))

    referenced = set()
    for r in event_rows:
        for s in r["sources"]:
            referenced.add(s["source"])
    outlet_rows = _outlet_rows(referenced)
    for i, batch in enumerate(_batches(outlet_rows, 1500)):
        _write(emit_dir, f"03_outlets_{i:03d}.sql", build_outlets_sql(batch))

    for i, batch in enumerate(_batches(event_rows, args.batch_events)):
        _write(emit_dir, f"04_events_{i:03d}.sql", build_events_sql(batch))

    art_rows = conn.execute(
        f"SELECT id, event_id, source, language, title, url, summary, image_url, published, fetched_at "
        f"FROM articles WHERE event_id IN ({q})"
    ).fetchall()
    conn.close()
    print(f"  {len(art_rows)} article(s) for the synced events")
    for i, batch in enumerate(_batches([dict(r) for r in art_rows], args.batch_articles)):
        _write(emit_dir, f"05_articles_{i:03d}.sql", build_articles_sql(batch))

    print(f"\nDone. SQL written to {emit_dir}/ - apply with a privileged Postgres connection, "
          f"in file-prefix order (00 deletes, 01 topics, 02 storylines, 03 outlets, 04 events, 05 articles).")
    if args.record_watermark:
        WATERMARK_FILE.write_text(sync_started_at, encoding="utf-8")
        print(f"Watermark recorded: {sync_started_at} (next run: --since {sync_started_at})")


if __name__ == "__main__":
    main()
