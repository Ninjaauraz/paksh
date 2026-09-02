"""
test_story_memory.py - Phase 21 (overnight): deterministic tests for
story_memory.py's schema, write path, and read contract.

Runs entirely against an in-memory SQLite database built fresh per test -
never touches paksh.db, never calls an LLM. A minimal `events` table (id,
updated_at only - the two columns get_verified_context actually reads) is
created locally so this suite has no dependency on database.py's own schema
changing.

Follows the test_phase21e_relationship_judgment.py convention: check(label,
cond) + a FAILURES list.

Run:  py test_story_memory.py
"""
import sqlite3

import story_memory as sm

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, updated_at TEXT)")
    sm.init_story_memory_schema(conn)
    return conn


def add_event(conn, eid, updated_at="2026-01-01T00:00:00"):
    conn.execute("INSERT INTO events (id, updated_at) VALUES (?, ?)", (eid, updated_at))
    conn.commit()


def rel(conn, prev, cur, rtype="R1", conf="high", jv="v1", decided="2026-01-02T00:00:00",
        fp="2026-01-01T00:00:00", title="prev title", summary="prev summary"):
    return sm.record_relationship(
        conn, previous_event_id=prev, current_event_id=cur, relationship_type=rtype,
        confidence=conf, evidence=["e1", "e2"], judge_version=jv, decided_at=decided,
        prev_snapshot_fingerprint=fp, prev_snapshot_title=title, prev_snapshot_summary=summary,
        prev_snapshot_topic="Politics", prev_snapshot_region="India",
    )


print("TEST 1: schema creation is idempotent")
conn = fresh_conn()
sm.init_story_memory_schema(conn)  # second call must not error
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
check("T1: event_relationships and event_deltas tables exist",
      {"event_relationships", "event_deltas"} <= tables)

print("\nTEST 2: record_relationship writes a real, readable row")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rid = rel(conn, 1, 2)
row = conn.execute("SELECT * FROM event_relationships WHERE id=?", (rid,)).fetchone()
check("T2: row exists with status=accepted", row is not None and row["status"] == "accepted")
check("T2: snapshot fields correctly stored", row["prev_snapshot_title"] == "prev title")

print("\nTEST 3: partial unique index enforces at most one accepted row per pair "
      "(direct INSERT bypassing record_relationship's own supersession must fail)")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2)
raised = False
try:
    conn.execute(
        "INSERT INTO event_relationships (previous_event_id, current_event_id, relationship_type,"
        " confidence, evidence_json, judge_version, decided_at, status, prev_snapshot_fingerprint,"
        " prev_snapshot_title, prev_snapshot_summary) VALUES (1,2,'R1','high','[]','v2','2026-01-03',"
        " 'accepted','fp','t','s')")
    conn.commit()
except sqlite3.IntegrityError:
    raised = True
check("T3: DB-level partial unique index rejects a second directly-inserted accepted row",
      raised)

print("\nTEST 4: record_relationship's own supersession correctly demotes the old row and "
      "leaves exactly one accepted row for the pair")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rid1 = rel(conn, 1, 2, jv="v1")
rid2 = rel(conn, 1, 2, jv="v2")
r1 = conn.execute("SELECT status, superseded_by_id FROM event_relationships WHERE id=?", (rid1,)).fetchone()
r2 = conn.execute("SELECT status FROM event_relationships WHERE id=?", (rid2,)).fetchone()
check("T4: old row transitioned to superseded", r1["status"] == "superseded")
check("T4: old row records who superseded it", r1["superseded_by_id"] == rid2)
check("T4: new row is the sole accepted row", r2["status"] == "accepted")
accepted_count = conn.execute(
    "SELECT COUNT(*) FROM event_relationships WHERE previous_event_id=1 AND current_event_id=2 "
    "AND status='accepted'").fetchone()[0]
check("T4: exactly one accepted row for the pair after supersession", accepted_count == 1)

print("\nTEST 5: invalidate_relationship flips status, preserves the row, cascades to delta")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rid = rel(conn, 1, 2)
conn.execute(
    "INSERT INTO event_deltas (relationship_id, delta_text, current_event_fingerprint_at_generation,"
    " generated_at, generator_version) VALUES (?, 'some delta', 'fp1', '2026-01-03', 'v1')", (rid,))
conn.commit()
sm.invalidate_relationship(conn, rid, "corrected: actually unrelated")
r = conn.execute("SELECT * FROM event_relationships WHERE id=?", (rid,)).fetchone()
d = conn.execute("SELECT * FROM event_deltas WHERE relationship_id=?", (rid,)).fetchone()
check("T5: relationship row preserved, not deleted", r is not None)
check("T5: status flipped to invalidated", r["status"] == "invalidated")
check("T5: invalidated_reason recorded", r["invalidated_reason"] == "corrected: actually unrelated")
check("T5: cascaded delta invalidated too", d["status"] == "invalidated")

print("\nTEST 6: get_verified_context returns nothing for an event with no relationships "
      "(valid, not an error)")
conn = fresh_conn()
add_event(conn, 1)
ctx = sm.get_verified_context(conn, 1)
check("T6: empty list for no history", ctx == [])

print("\nTEST 7: get_verified_context returns a 1-hop relationship correctly")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, rtype="R3")
ctx = sm.get_verified_context(conn, 2)
check("T7: exactly one context item", len(ctx) == 1)
check("T7: correct previous_event_id", ctx[0].previous_event_id == 1)
check("T7: correct relationship_type", ctx[0].relationship_type == "R3")
check("T7: hop_distance is 1", ctx[0].hop_distance == 1)
check("T7: historical_observation carries the frozen snapshot", ctx[0].historical_observation["title"] == "prev title")

print("\nTEST 8: get_verified_context OMITS a relationship whose previous_event no longer "
      "exists (the 21E.3S consolidation fail-closed contract) - never served from the "
      "snapshot alone")
conn = fresh_conn()
add_event(conn, 2)  # event 1 deliberately NOT added - simulates consolidate.py's real delete
rel(conn, 1, 2)
ctx = sm.get_verified_context(conn, 2)
check("T8: dangling reference to a deleted event is omitted, not served", ctx == [])

print("\nTEST 9: get_verified_context respects max_hops and walks a real chain")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2); add_event(conn, 3); add_event(conn, 4)
rel(conn, 1, 2)
rel(conn, 2, 3)
rel(conn, 3, 4)
ctx2 = sm.get_verified_context(conn, 4, max_hops=2)
ctx1 = sm.get_verified_context(conn, 4, max_hops=1)
check("T9: max_hops=2 returns exactly 2 items (event3->event4, event2->event3)", len(ctx2) == 2)
check("T9: max_hops=1 returns exactly 1 item", len(ctx1) == 1)
check("T9: hop distances are correct under max_hops=2",
      sorted(c.hop_distance for c in ctx2) == [1, 2])

print("\nTEST 10: get_verified_context's cycle guard - a manually-inserted cyclic edge set "
      "does not infinite-loop and does not revisit a node")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2)          # 1 -> 2
rel(conn, 2, 1, jv="v1")  # 2 -> 1 (a cycle, should be structurally impossible under normal
                          # Stage-1 operation, but the read contract must not loop anyway)
ctx = sm.get_verified_context(conn, 2, max_hops=5)
check("T10: cycle guard terminates and does not revisit event 2", len(ctx) <= 2)
visited_ids = [c.previous_event_id for c in ctx]
check("T10: no previous_event_id repeats", len(visited_ids) == len(set(visited_ids)))

print("\nTEST 11: invalidated/superseded relationships never appear in read contract output")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rid1 = rel(conn, 1, 2, jv="v1")
rel(conn, 1, 2, jv="v2")  # supersedes rid1
ctx = sm.get_verified_context(conn, 2)
check("T11: only the surviving accepted row is returned", len(ctx) == 1 and ctx[0].relationship_id != rid1)

print("\nTEST 12: an active delta is attached and correctly flagged fresh vs stale - the")
print("  delta's fingerprint tracks the CURRENT event (the one being generated), not the")
print("  previous event (whose state is already frozen in the snapshot) - see Section 16")
conn = fresh_conn()
add_event(conn, 1)
add_event(conn, 2, updated_at="2026-01-05T00:00:00")  # CURRENT event's live fingerprint
rid = rel(conn, 1, 2)
conn.execute(
    "INSERT INTO event_deltas (relationship_id, delta_text, current_event_fingerprint_at_generation,"
    " generated_at, generator_version) VALUES (?, 'fresh delta', '2026-01-05T00:00:00', "
    "'2026-01-05T01:00:00', 'v1')", (rid,))
conn.commit()
ctx = sm.get_verified_context(conn, 2)
check("T12: delta attached", ctx[0].delta is not None)
check("T12: delta not stale when its captured fingerprint matches the current event's live updated_at",
      ctx[0].delta["stale"] is False)

# now mutate event 2's (the CURRENT event's) updated_at (simulating a reprocess of the
# current event itself, e.g. reframe.py filling a gap) without touching the delta
conn.execute("UPDATE events SET updated_at=? WHERE id=2", ("2026-02-01T00:00:00",))
conn.commit()
ctx2 = sm.get_verified_context(conn, 2)
check("T12: delta correctly flagged stale after the CURRENT event's fingerprint moved",
      ctx2[0].delta["stale"] is True)

print("\nTEST 13: get_verified_context never mutates anything (static source-level guarantee, "
      "same convention as context_retrieval.py's own Test 15)")
import inspect
src = inspect.getsource(sm.get_verified_context)
check("T13: get_verified_context contains no INSERT/UPDATE/DELETE/commit",
      not any(kw in src for kw in ("INSERT", "UPDATE ", "DELETE ", ".commit(")))

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
