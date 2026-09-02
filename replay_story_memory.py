"""
replay_story_memory.py - Phase 21 (overnight): SHADOW replay of the full
Stage 1 (context_retrieval) -> Stage 2 (relationship_judgment, hardened) ->
Story Memory (story_memory) pipeline against a bounded, real, recent sample
of paksh.db events.

SHADOW BY DEFAULT: writes proposed relationships to a SEPARATE scratch
SQLite file (story_memory_shadow.db, gitignored via *.db), never to the real
paksh.db. Only with --persist does it write the SAME validated batch to the
real paksh.db's event_relationships/event_deltas tables (already migrated,
currently empty) - "controlled persistence of a small, reviewed batch", not
a full-corpus backfill, per the directive's explicit caution.

Read-only with respect to paksh.db unless --persist is passed. Makes real,
billed Gemini calls (bounded: --sample events x up to 3 Stage-1 candidates
each, with 2x for any candidate that clears pass 1 - see
judge_relationships_confirmed).

Run:  py replay_story_memory.py --sample 20              (shadow only)
      py replay_story_memory.py --sample 20 --persist     (writes to paksh.db)
"""
import argparse
import json
import sqlite3
import time
from datetime import datetime, timedelta

import ai_providers                      # side effect: loads GEMINI_API_KEY
import database
import context_retrieval as cr
import relationship_judgment as rj
import story_memory as sm

JUDGE_VERSION = "phase21-overnight-2026-09-03"
GENERATOR_VERSION = "phase21-overnight-2026-09-03"


def build_events_by_id(pool_days: int):
    conn = database.get_connection()
    since = (datetime.utcnow() - timedelta(days=pool_days)).isoformat()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at, analysis_json FROM events "
        "WHERE created_at >= ? ORDER BY created_at DESC", (since,)
    ).fetchall()
    conn.close()
    out = {}
    for r in rows:
        d = json.loads(r["analysis_json"])
        out[r["id"]] = {
            "id": r["id"], "title": d.get("title") or r["title"], "summary": d.get("summary") or "",
            "topic": d.get("topic"), "region": d.get("region"),
            "published_at": d.get("published_at"), "created_at": r["created_at"],
            "updated_at": r["updated_at"], "lean_counts": d.get("coverage", {}),
        }
    return out


def snapshot_lean_counts(e):
    cov = e.get("lean_counts") or {}
    return {k: v.get("count", 0) if isinstance(v, dict) else v for k, v in cov.items()} or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=20, help="number of most-recent current events to judge")
    ap.add_argument("--pool-days", type=int, default=70, help="candidate-pool lookback window")
    ap.add_argument("--persist", action="store_true", help="also write the validated batch to real paksh.db")
    args = ap.parse_args()

    print(f"Building candidate pool (last {args.pool_days} days)...")
    events_by_id = build_events_by_id(args.pool_days)
    print(f"  pool size: {len(events_by_id)} events")

    print("Building embedding centroids (real cached embeddings, no new Ollama calls)...")
    centroids = cr.build_centroids(list(events_by_id.values()))
    print(f"  centroids available for: {len(centroids)}/{len(events_by_id)} events")

    sample_ids = sorted(events_by_id.keys(), key=lambda i: events_by_id[i]["created_at"], reverse=True)[:args.sample]
    print(f"\nSample: {len(sample_ids)} most recent events\n")

    shadow_conn = sqlite3.connect("story_memory_shadow.db")
    shadow_conn.row_factory = sqlite3.Row
    sm.init_story_memory_schema(shadow_conn)

    real_conn = database.get_connection() if args.persist else None

    stats = {"candidates_retrieved": 0, "judged": 0, "accepted": 0, "by_type": {}}
    proposals = []

    for cur_id in sample_ids:
        cur = events_by_id[cur_id]
        candidates = cr.retrieve_historical_candidates(cur_id, events_by_id, centroids)
        stats["candidates_retrieved"] += len(candidates)
        if not candidates:
            continue
        jcands = [rj.JudgeCandidate(
            previous_event_id=c.previous_event_id, previous_title=c.title, previous_summary=c.summary,
            previous_date=c.date, previous_topic=c.topic, previous_region=c.region,
            semantic_similarity=c.semantic_similarity, lexical_overlap_terms=c.lexical_overlap_terms,
            lexical_overlap_count=c.lexical_overlap_count, same_storyline=c.same_storyline,
            thin_source=c.thin_source, gap_days=c.gap_days,
        ) for c in candidates]
        current_event = {"title": cur["title"], "summary": cur["summary"],
                          "date": cur.get("published_at") or cur["created_at"],
                          "topic": cur["topic"], "region": cur["region"]}
        results = rj.judge_relationships_confirmed(current_event, jcands)
        stats["judged"] += len(results)

        cur_text = f"{cur['title']} {cur['summary']}"
        for c in jcands:
            r = results.get(c.previous_event_id)
            if r is None:
                continue
            cand_text = f"{c.previous_title} {c.previous_summary or ''}"
            accepted = rj.accept(r, current_text=cur_text, candidate_text=cand_text,
                                  current_topic=cur["topic"], candidate_topic=c.previous_topic,
                                  same_storyline=c.same_storyline)
            print(f"  #{c.previous_event_id} -> #{cur_id}  type={r.relationship_type:<3} "
                  f"conf={r.confidence:<6} accept={accepted}")
            if not accepted:
                continue
            stats["accepted"] += 1
            stats["by_type"][r.relationship_type] = stats["by_type"].get(r.relationship_type, 0) + 1
            prev = events_by_id[c.previous_event_id]
            kwargs = dict(
                previous_event_id=c.previous_event_id, current_event_id=cur_id,
                relationship_type=r.relationship_type, confidence=r.confidence,
                evidence=r.evidence, judge_version=JUDGE_VERSION,
                decided_at=datetime.utcnow().isoformat(),
                prev_snapshot_fingerprint=prev.get("updated_at") or prev["created_at"],
                prev_snapshot_title=prev["title"], prev_snapshot_summary=prev["summary"],
                prev_snapshot_topic=prev["topic"], prev_snapshot_region=prev["region"],
                prev_snapshot_lean_counts=snapshot_lean_counts(prev),
                stage1_similarity=c.semantic_similarity, stage1_lexical_count=c.lexical_overlap_count,
            )
            sm.record_relationship(shadow_conn, **kwargs)
            proposals.append((c.previous_event_id, cur_id, r.relationship_type, r.confidence))
            if args.persist:
                sm.record_relationship(real_conn, **kwargs)
            time.sleep(0.5)

    shadow_conn.close()
    if real_conn:
        real_conn.close()

    print("\n" + "=" * 70)
    print("SHADOW REPLAY SUMMARY")
    print(f"  sample events judged  : {len(sample_ids)}")
    print(f"  Stage-1 candidates    : {stats['candidates_retrieved']}")
    print(f"  Stage-2 judged        : {stats['judged']}")
    print(f"  accepted (verified)   : {stats['accepted']}")
    print(f"  by relationship type  : {stats['by_type']}")
    print(f"  proposals             : {proposals}")
    print(f"  written to            : story_memory_shadow.db"
          + (" AND real paksh.db (--persist)" if args.persist else " (shadow only, real paksh.db untouched)"))


if __name__ == "__main__":
    main()
