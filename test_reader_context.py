"""
test_reader_context.py - Phase 21G: deterministic tests for reader_context.py,
the canonical boundary between Story Memory and the reader-facing page.

Runs against an in-memory SQLite database (same pattern as
test_story_memory.py), never touches paksh.db, never calls an LLM.

Covers the directive's required data-contract test list: no context, valid
R1/R2/R3/R4, invalidated relationship, missing historical snapshot, stale
delta, malformed relationship, multiple relationship candidates, superseded
relationship, self-edge, orphan endpoint.

Run:  py test_reader_context.py
"""
import sqlite3

import story_memory as sm
import reader_context as rc

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, updated_at TEXT, created_at TEXT)")
    sm.init_story_memory_schema(conn)
    return conn


def add_event(conn, eid, updated_at="2026-01-01T00:00:00", created_at="2026-01-01T00:00:00"):
    conn.execute("INSERT INTO events (id, updated_at, created_at) VALUES (?, ?, ?)",
                 (eid, updated_at, created_at))
    conn.commit()


def rel(conn, prev, cur, rtype="R1", conf="high", jv="v1", decided="2026-01-02T00:00:00",
        fp="2026-01-01T00:00:00", title="Earlier Story Title", summary="earlier summary"):
    return sm.record_relationship(
        conn, previous_event_id=prev, current_event_id=cur, relationship_type=rtype,
        confidence=conf, evidence=["e1", "e2"], judge_version=jv, decided_at=decided,
        prev_snapshot_fingerprint=fp, prev_snapshot_title=title, prev_snapshot_summary=summary,
        prev_snapshot_topic="Politics", prev_snapshot_region="India",
    )


print("TEST 1: no verified relationship -> None (State 1: render nothing)")
conn = fresh_conn()
add_event(conn, 1)
check("T1: None for an event with no history", rc.build_story_context(conn, 1) is None)

print("\nTEST 2: valid R1 -> full context object, no internal fields leaked")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, rtype="R1")
out = rc.build_story_context(conn, 2)
check("T2a: context returned", out is not None)
check("T2b: relationship_label bilingual dict present", out["relationship_label"]["en"] and out["relationship_label"]["hi"])
check("T2c: historical_event has id/title/date", out["historical_event"]["id"] == 1
      and out["historical_event"]["title"] == "Earlier Story Title" and out["historical_event"]["date"])
check("T2d: no relationship_type code leaked", "relationship_type" not in out and "R1" not in str(out["relationship_label"]))
check("T2e: no confidence leaked", "confidence" not in out and "high" not in str(out))
check("T2f: no evidence/judge_version/Stage-1 fields leaked",
      not any(k in out for k in ("evidence", "judge_version", "stage1_similarity", "stage1_lexical_count")))
check("T2g: no delta_text key when no delta exists", "delta_text" not in out)

print("\nTEST 3: valid R2")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, rtype="R2")
out = rc.build_story_context(conn, 2)
check("T3: R2 produces a distinct label from R1", out["relationship_label"]["en"] != rc._RELATIONSHIP_LABEL["R1"]["en"])

print("\nTEST 4: valid R3")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, rtype="R3")
out = rc.build_story_context(conn, 2)
check("T4: R3 label present and distinct", out["relationship_label"] == rc._RELATIONSHIP_LABEL["R3"])

print("\nTEST 5: valid R4 - background, must not read as causal continuation")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, rtype="R4")
out = rc.build_story_context(conn, 2)
check("T5a: R4 label present", out["relationship_label"] == rc._RELATIONSHIP_LABEL["R4"])
check("T5b: R4 label reads as background, not causation ('caused'/'because' absent)",
      "caused" not in out["relationship_label"]["en"].lower() and "because" not in out["relationship_label"]["en"].lower())

print("\nTEST 6: invalidated relationship -> None (State 5: render nothing)")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rid = rel(conn, 1, 2)
sm.invalidate_relationship(conn, rid, "corrected: actually unrelated")
check("T6: invalidated relationship never reaches the reader", rc.build_story_context(conn, 2) is None)

print("\nTEST 7: missing historical snapshot title -> None (State 2: fail closed)")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, title="")  # empty title = nothing safe to show
check("T7: empty snapshot title fails closed", rc.build_story_context(conn, 2) is None)

print("\nTEST 8: stale delta is NOT surfaced (State 6: never present stale as current)")
conn = fresh_conn()
add_event(conn, 1)
add_event(conn, 2, updated_at="2026-01-05T00:00:00")
rid = rel(conn, 1, 2)
conn.execute(
    "INSERT INTO event_deltas (relationship_id, delta_text, current_event_fingerprint_at_generation,"
    " generated_at, generator_version) VALUES (?, 'old delta text', '2026-01-05T00:00:00', "
    "'2026-01-05T01:00:00', 'v1')", (rid,))
conn.commit()
out = rc.build_story_context(conn, 2)
check("T8a: fresh delta IS surfaced when fingerprint matches", out.get("delta_text") == "old delta text")
# now mutate the CURRENT event's updated_at (simulating a reprocess) without regenerating the delta
conn.execute("UPDATE events SET updated_at=? WHERE id=2", ("2026-02-01T00:00:00",))
conn.commit()
out2 = rc.build_story_context(conn, 2)
check("T8b: context still renders (relationship itself is unaffected)", out2 is not None)
check("T8c: stale delta_text is omitted, not shown as current", "delta_text" not in out2)

print("\nTEST 9: malformed relationship_type fails closed rather than crashing")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
# directly insert a row with an out-of-vocabulary relationship_type, bypassing record_relationship's
# own validation (relationship_judgment.py's parser would never allow this in practice, but the
# reader-facing boundary must not trust that upstream invariant blindly)
conn.execute(
    "INSERT INTO event_relationships (previous_event_id, current_event_id, relationship_type,"
    " confidence, evidence_json, judge_version, decided_at, status, prev_snapshot_fingerprint,"
    " prev_snapshot_title, prev_snapshot_summary) VALUES (1,2,'R9','high','[]','v1','2026-01-02',"
    " 'accepted','fp','Earlier Story Title','summary')")
conn.commit()
check("T9: unknown relationship_type fails closed, does not raise", rc.build_story_context(conn, 2) is None)

print("\nTEST 10: multiple relationship candidates -> exactly ONE surfaced (no chain/list)")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2); add_event(conn, 3)
rel(conn, 1, 3, decided="2026-01-01T00:00:00", title="Older Candidate")
rel(conn, 2, 3, decided="2026-01-05T00:00:00", title="Newer Candidate")
out = rc.build_story_context(conn, 3)
check("T10a: exactly one historical_event in the result (not a list)",
      isinstance(out["historical_event"], dict) and "id" in out["historical_event"])
check("T10b: the more recently-decided candidate is the one surfaced",
      out["historical_event"]["title"] == "Newer Candidate")

print("\nTEST 10c: real-data-motivated case (#17464, this session) - when multiple candidates "
      "exist, one carrying a valid delta is preferred over a more-recently-decided one without "
      "a delta, so a validated 'what changed' is never silently hidden by a thinner candidate")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2); add_event(conn, 3, updated_at="2026-01-05T00:00:00")
rel(conn, 1, 3, decided="2026-01-01T00:00:00", title="Has A Delta")
rid_with_delta = conn.execute(
    "SELECT id FROM event_relationships WHERE previous_event_id=1 AND current_event_id=3"
).fetchone()["id"]
conn.execute(
    "INSERT INTO event_deltas (relationship_id, delta_text, current_event_fingerprint_at_generation,"
    " generated_at, generator_version) VALUES (?, 'a real delta', '2026-01-05T00:00:00', "
    "'2026-01-05T01:00:00', 'v1')", (rid_with_delta,))
conn.commit()
rel(conn, 2, 3, decided="2026-01-09T00:00:00", title="More Recent But No Delta")  # decided LATER
out = rc.build_story_context(conn, 3)
check("T10c: the delta-bearing candidate is surfaced despite being decided earlier",
      out["historical_event"]["title"] == "Has A Delta" and out.get("delta_text") == "a real delta")

print("\nTEST 11: superseded relationship never reaches the reader")
conn = fresh_conn()
add_event(conn, 1); add_event(conn, 2)
rel(conn, 1, 2, jv="v1", title="Old Judgment")
rel(conn, 1, 2, jv="v2", title="New Judgment")  # supersedes v1
out = rc.build_story_context(conn, 2)
check("T11: only the superseding (accepted) row's snapshot is shown",
      out["historical_event"]["title"] == "New Judgment")

print("\nTEST 12: self-edge (defensive - cannot occur via record_relationship's own contract, "
      "but the boundary must not break if the underlying data ever contained one)")
conn = fresh_conn()
add_event(conn, 1)
conn.execute(
    "INSERT INTO event_relationships (previous_event_id, current_event_id, relationship_type,"
    " confidence, evidence_json, judge_version, decided_at, status, prev_snapshot_fingerprint,"
    " prev_snapshot_title, prev_snapshot_summary) VALUES (1,1,'R1','high','[]','v1','2026-01-02',"
    " 'accepted','fp','Self Title','summary')")
conn.commit()
out = rc.build_story_context(conn, 1)
check("T12: a self-edge does not crash the boundary (may render or omit, must not raise)", True)

print("\nTEST 13: orphan endpoint (previous_event deleted) -> None, never served from snapshot alone")
conn = fresh_conn()
add_event(conn, 2)  # event 1 deliberately never added - simulates consolidate.py's real delete
rel(conn, 1, 2)
check("T13: dangling reference to a deleted event fails closed", rc.build_story_context(conn, 2) is None)

print("\nTEST 14: build_story_context never raises even if story_memory itself errors")
class _BoomConn:
    def cursor(self):
        raise RuntimeError("simulated DB failure")
check("T14: an internal exception is swallowed, returns None, does not propagate",
      rc.build_story_context(_BoomConn(), 999) is None)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
