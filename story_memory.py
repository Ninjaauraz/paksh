"""
story_memory.py - Phase 21 (overnight): ISOLATED persistence + read contract
for verified historical relationships between Paksh Events.

NOT IMPORTED BY ANY PRODUCTION CODE PATH. database.py, analyze.py, reframe.py,
cluster.py, export_static.py, main.py, consolidate.py are all unmodified and
do not import this file. init_story_memory_schema() is never called from
database.py's own init_db() - it is a separate, explicit, additive migration
this module owns entirely, so a bug here cannot affect any existing
production schema path. Reuses database.get_connection() (read-only reuse of
the connection helper, never calls INTO database.py's own table-owning code).

Reconciles Phase 21E.3 / 21E.3R / 21E.3S (this session, same conversation):
  - Event stays Paksh's sole canonical identity (21E.3's own conclusion,
    reaffirmed by 21E.3R): no competing Story table, no new ID space.
  - "Story" is a computed traversal over event_relationships edges, never a
    stored identity (21E.3).
  - A relationship's historical_observation is a FROZEN SNAPSHOT of the
    previous event's state at decision time, embedded directly in the
    relationship row - never a live re-read of the (routinely mutable, see
    21E.3R's Event mutability findings) current event content. This is the
    single correction 21E.3R made to 21E.3's original "read the linked
    event's summary live" design, which would have silently presented a
    later-mutated summary as if it were the original historical observation.
  - Consolidation contract (21E.3S, this session): event_relationships rows
    are NEVER rewritten by consolidate.py (unmodified, untouched). A
    relationship whose previous_event_id or current_event_id has since been
    deleted (consolidate.py --apply's real, destructive merge behavior) is
    detected at READ time and OMITTED - never silently served, never
    redirected. This requires zero changes to consolidate.py, at the cost of
    some relationships silently "decaying" into permanently-omitted rows
    over time as consolidation runs - an accepted, documented limitation,
    not a corruption risk (the core invariant - consolidation must never
    make a relationship silently point at a semantically different event -
    holds trivially because the pointer is simply never rewritten).
  - Judge-version supersession: at most one status='accepted' row per
    (previous_event_id, current_event_id) pair, enforced by a SQLite PARTIAL
    UNIQUE INDEX (WHERE status='accepted') - a structural, DB-level
    guarantee, not a query-time convention. A newer judge_version's decision
    must explicitly supersede (never just outnumber) an older accepted row
    for the same pair in the same transaction, or the insert fails.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import database   # read-only reuse: get_connection() only - never calls INTO database.py's tables
import analyze as _analyze   # Phase 24B/F4: reuses _event_created_at()'s article-date parsing
                              # only (a pure date utility, not the generation/prompt path) to
                              # date a Context block's historical event - see get_verified_context


# --------------------------------------------------------------------------
# Schema (additive only, never touches events/articles/embeddings).
# --------------------------------------------------------------------------

def init_story_memory_schema(conn=None):
    """Idempotent. Creates event_relationships and event_deltas if missing.
    Never called from database.init_db() - callers (replay/persistence
    scripts, tests) call this explicitly. Accepts an existing connection
    (for tests against an in-memory DB) or opens/closes its own."""
    owns_conn = conn is None
    if owns_conn:
        conn = database.get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_relationships (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            previous_event_id   INTEGER NOT NULL,
            current_event_id    INTEGER NOT NULL,
            relationship_type   TEXT NOT NULL,   -- R1|R2|R3|R4
            confidence          TEXT NOT NULL,   -- 'high' under today's accept() policy
            evidence_json       TEXT NOT NULL,   -- json list of evidence strings
            judge_version       TEXT NOT NULL,
            stage1_similarity   REAL,
            stage1_lexical_count INTEGER,
            decided_at          TEXT NOT NULL,
            status              TEXT NOT NULL DEFAULT 'accepted',  -- accepted|superseded|invalidated
            superseded_by_id    INTEGER,
            invalidated_at      TEXT,
            invalidated_reason  TEXT,
            -- Historical observation: FROZEN snapshot of previous_event_id's state
            -- AS OF decided_at. Embedded here (not a separate table) because it is
            -- 1:1 with this exact decision, never reused across relationships,
            -- never queried independently of its relationship (21E.3R Section 15).
            prev_snapshot_fingerprint TEXT NOT NULL,   -- previous event's updated_at at decided_at
            prev_snapshot_title        TEXT NOT NULL,
            prev_snapshot_summary       TEXT NOT NULL,
            prev_snapshot_summary_points_json TEXT,
            prev_snapshot_topic          TEXT,
            prev_snapshot_region          TEXT,
            prev_snapshot_lean_counts_json TEXT,
            UNIQUE(previous_event_id, current_event_id, judge_version)
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_accepted_per_pair
        ON event_relationships(previous_event_id, current_event_id)
        WHERE status = 'accepted'
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_event_relationships_current "
                "ON event_relationships(current_event_id, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_event_relationships_previous "
                "ON event_relationships(previous_event_id, status)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_deltas (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            relationship_id           INTEGER NOT NULL,
            delta_text                 TEXT NOT NULL,
            current_event_fingerprint_at_generation TEXT NOT NULL,
            generated_at                TEXT NOT NULL,
            generator_version             TEXT NOT NULL,
            status                        TEXT NOT NULL DEFAULT 'active',  -- active|invalidated
            invalidated_at                 TEXT,
            UNIQUE(relationship_id)
        )
    """)

    conn.commit()
    if owns_conn:
        conn.close()


# --------------------------------------------------------------------------
# Write path (used by replay/persistence, never by generation).
# --------------------------------------------------------------------------

def record_relationship(conn, *, previous_event_id, current_event_id, relationship_type,
                         confidence, evidence, judge_version, decided_at,
                         prev_snapshot_fingerprint, prev_snapshot_title, prev_snapshot_summary,
                         prev_snapshot_summary_points=None, prev_snapshot_topic=None,
                         prev_snapshot_region=None, prev_snapshot_lean_counts=None,
                         stage1_similarity=None, stage1_lexical_count=None):
    """Inserts one accepted relationship, superseding any existing accepted
    row for the same (previous_event_id, current_event_id) pair FIRST, in the
    same transaction the partial unique index would otherwise reject. Never
    called with a non-accepted result - callers filter with accept() first.
    Returns the new row's id."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE event_relationships SET status='superseded' "
        "WHERE previous_event_id=? AND current_event_id=? AND status='accepted'",
        (previous_event_id, current_event_id),
    )
    superseded_id = cur.lastrowid if cur.rowcount else None
    cur.execute(
        """INSERT INTO event_relationships
           (previous_event_id, current_event_id, relationship_type, confidence,
            evidence_json, judge_version, stage1_similarity, stage1_lexical_count,
            decided_at, status, prev_snapshot_fingerprint, prev_snapshot_title,
            prev_snapshot_summary, prev_snapshot_summary_points_json,
            prev_snapshot_topic, prev_snapshot_region, prev_snapshot_lean_counts_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?, ?, ?, ?)""",
        (previous_event_id, current_event_id, relationship_type, confidence,
         json.dumps(evidence), judge_version, stage1_similarity, stage1_lexical_count,
         decided_at, prev_snapshot_fingerprint, prev_snapshot_title, prev_snapshot_summary,
         json.dumps(prev_snapshot_summary_points) if prev_snapshot_summary_points else None,
         prev_snapshot_topic, prev_snapshot_region,
         json.dumps(prev_snapshot_lean_counts) if prev_snapshot_lean_counts else None),
    )
    new_id = cur.lastrowid
    if superseded_id:
        # supersede-by-pair may have flipped more than one prior row only if
        # data were already corrupt (the partial index prevents >1 accepted);
        # this covers the single expected case cleanly and cheaply.
        cur.execute("UPDATE event_relationships SET superseded_by_id=? "
                    "WHERE previous_event_id=? AND current_event_id=? "
                    "AND status='superseded' AND superseded_by_id IS NULL",
                    (new_id, previous_event_id, current_event_id))
    conn.commit()
    return new_id


def invalidate_relationship(conn, relationship_id, reason):
    """Status flip only - never deletes. Cascades to any active delta."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute(
        "UPDATE event_relationships SET status='invalidated', invalidated_at=?, "
        "invalidated_reason=? WHERE id=? AND status='accepted'",
        (now, reason, relationship_id),
    )
    cur.execute("UPDATE event_deltas SET status='invalidated', invalidated_at=? "
                "WHERE relationship_id=? AND status='active'",
                (now, relationship_id))
    conn.commit()


# --------------------------------------------------------------------------
# Read contract (Gate: deterministic, read-only, bounded, fail-closed).
# --------------------------------------------------------------------------

@dataclass
class VerifiedContext:
    relationship_id: int
    previous_event_id: int
    relationship_type: str
    confidence: str
    evidence: list
    decided_at: str
    judge_version: str
    hop_distance: int
    historical_observation: dict = field(default_factory=dict)
    delta: Optional[dict] = None
    historical_event_date: Optional[str] = None  # Phase 24B/F4: earliest member-article
                                                    # publish date - display only, see
                                                    # get_verified_context's own comment


def get_verified_context(conn, current_event_id: int, max_hops: int = 2) -> list[VerifiedContext]:
    """Deterministic, read-only, bounded, fail-closed. Never calls Stage 1,
    Stage 2, or any LLM. Never mutates anything.

    Walks backward from current_event_id through accepted relationships,
    most-recent-first, up to max_hops. At each hop:
      - only status='accepted' relationships are considered (supersession/
        invalidation already resolved at write time - Gate: 12);
      - the referenced previous_event_id (and, for hop>1, the intermediate
        current_event_id) must still exist in `events` - a row surviving
        consolidate.py's real delete_event() - or that edge is OMITTED,
        never served from the frozen snapshot alone (21E.3S's fail-closed
        consolidation policy: never trust a dangling reference);
      - a visited-set prevents any cycle (structurally near-impossible given
        Stage 1 only retrieves strictly-older candidates, but guarded
        anyway, defensively, per the read contract's own requirement);
      - any active event_deltas row for the relationship is attached, tagged
        with whether its captured fingerprint still matches the CURRENT
        event's live updated_at (staleness is surfaced, never hidden).
    """
    out: list[VerifiedContext] = []
    visited = {current_event_id}
    frontier = [current_event_id]
    cur = conn.cursor()

    for hop in range(1, max_hops + 1):
        if not frontier:
            break
        next_frontier = []
        for eid in frontier:
            rows = cur.execute(
                "SELECT * FROM event_relationships WHERE current_event_id=? AND status='accepted' "
                "ORDER BY decided_at DESC", (eid,),
            ).fetchall()
            for row in rows:
                prev_id = row["previous_event_id"]
                if prev_id in visited:
                    continue  # cycle guard
                # fail-closed existence check (21E.3S consolidation contract). created_at is
                # read live here (not from the frozen snapshot) because it is a stable,
                # effectively-immutable field (see 21E.3R's mutability findings: created_at
                # is preserved across reframe.py/recount_migrate.py's in-place edits, unlike
                # title/summary/region) - display-only, never a substitute for snapshot content.
                prev_row = cur.execute("SELECT created_at FROM events WHERE id=?", (prev_id,)).fetchone()
                if not prev_row:
                    continue
                visited.add(prev_id)
                # Phase 24B/F4: events.created_at is when Paksh's OWN pipeline inserted this
                # row, not when the underlying news happened - a later backfill/re-cluster
                # can legitimately postdate an earlier real story (confirmed cause of a
                # reader-visible backwards Context date on event 17464: its predecessor
                # 17383 was row-created 2026-09-03 even though its coverage began
                # 2026-09-01, a day before 17464's own). articles.published is set once at
                # ingest and never rewritten by reframe/recount/consolidate, so the earliest
                # one is the grounded, stable answer to "when did this history begin" - the
                # same article-date parsing analyze.py already uses for an event's own
                # displayed date, just taking the oldest instead of the newest. Best-effort:
                # this module stays deliberately isolated (see module docstring), so any
                # failure here (no articles table in a minimal test fixture, a locked DB,
                # anything) falls back to the original created_at behavior rather than ever
                # raising out of get_verified_context.
                historical_date = prev_row["created_at"]
                try:
                    prev_articles = cur.execute(
                        "SELECT published FROM articles WHERE event_id=?", (prev_id,)).fetchall()
                    historical_date = (
                        _analyze._event_created_at([dict(a) for a in prev_articles], oldest=True)
                        or historical_date
                    )
                except Exception:
                    pass
                evidence = json.loads(row["evidence_json"] or "[]")
                snapshot = {
                    "title": row["prev_snapshot_title"],
                    "summary": row["prev_snapshot_summary"],
                    "summary_points": json.loads(row["prev_snapshot_summary_points_json"] or "null"),
                    "topic": row["prev_snapshot_topic"],
                    "region": row["prev_snapshot_region"],
                    "lean_counts": json.loads(row["prev_snapshot_lean_counts_json"] or "null"),
                    "fingerprint": row["prev_snapshot_fingerprint"],
                }
                delta = None
                drow = cur.execute(
                    "SELECT * FROM event_deltas WHERE relationship_id=? AND status='active'",
                    (row["id"],),
                ).fetchone()
                if drow:
                    live = cur.execute("SELECT updated_at FROM events WHERE id=?", (eid,)).fetchone()
                    live_fp = live["updated_at"] if live else None
                    delta = {
                        "delta_text": drow["delta_text"],
                        "generated_at": drow["generated_at"],
                        "generator_version": drow["generator_version"],
                        "stale": live_fp != drow["current_event_fingerprint_at_generation"],
                    }
                out.append(VerifiedContext(
                    relationship_id=row["id"], previous_event_id=prev_id,
                    relationship_type=row["relationship_type"], confidence=row["confidence"],
                    evidence=evidence, decided_at=row["decided_at"],
                    judge_version=row["judge_version"], hop_distance=hop,
                    historical_observation=snapshot, delta=delta,
                    historical_event_date=historical_date,
                ))
                next_frontier.append(prev_id)
        frontier = next_frontier

    return out
