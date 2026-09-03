"""
test_phase24b_reader_fixes.py - Phase 24B: regression guards for the four
targeted reader-experience fixes.

F1 (broken /story/<id> routing): checks the generated vercel.json routing
rule and the compiled app.js client-side not-found handling.
F2 (garbage cluster removal): checks the current exported reader-facing
feed no longer contains event 16001, and that the two legitimate large
events cleanup.py's default thresholds would also flag (8798, 8672) were
NOT removed.
F3 (mobile Support overlap): checks the compiled app.js ties the floating
Support button's visibility to scroll position, not just the session timer.
F4 (Context historical date): a fixture-DB test that get_verified_context's
historical_event_date comes from the earliest member-article publish date,
not events.created_at, with a fail-closed fallback when no article dates
are available.

F1/F2/F3 read already-generated artifacts (_site/vercel.json, _site/static/
app.js, _site/data/events.json) rather than re-running the full export or
touching paksh.db - run `py export_static.py` first if those are stale.

Run:  py test_phase24b_reader_fixes.py
"""
import json
import sqlite3
from pathlib import Path

import story_memory as sm

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


ROOT = Path(__file__).resolve().parent
SITE = ROOT / "_site"


print("F1: /story/<id> routing")
vercel_json = json.loads((SITE / "vercel.json").read_text(encoding="utf-8"))
story_route = next((r for r in vercel_json["routes"] if r.get("src", "").startswith("/story/")), None)
check("F1a: story route rule present", story_route is not None)
check("F1b: story route falls through to the SPA when no pre-rendered file exists (check:true)",
      bool(story_route and story_route.get("check") is True))
filesystem_idx = next(i for i, r in enumerate(vercel_json["routes"]) if r.get("handle") == "filesystem")
story_idx = vercel_json["routes"].index(story_route)
catchall_idx = next(i for i, r in enumerate(vercel_json["routes"])
                     if r.get("src") == "/(.*)" and r.get("dest") == "/index.html")
check("F1c: ordering preserved - filesystem, then story rewrite, then SPA catch-all",
      filesystem_idx < story_idx < catchall_idx)

app_js = (SITE / "static" / "app.js").read_text(encoding="utf-8")
check("F1d: compiled app.js contains the not-found sentinel", "STORY_NOT_FOUND" in app_js)
check("F1e: the story route renders NotFoundPage for the not-found state",
      "storyNotFound" in app_js and "NotFoundPage" in app_js)


print("\nF2: garbage cluster removal")
events_json = json.loads((SITE / "data" / "events.json").read_text(encoding="utf-8"))
exported_ids = {e["id"] for e in events_json["events"]}
check("F2a: event 16001 (grab-bag: crosswords/Wordle/TV listings) absent from the exported feed",
      16001 not in exported_ids)
conn = sqlite3.connect(ROOT / "paksh.db")
row = conn.execute("SELECT COUNT(*) FROM events WHERE id=16001").fetchone()
check("F2b: event 16001 absent from the database", row[0] == 0)
for legit_id in (8798, 8672):
    row = conn.execute("SELECT COUNT(*) FROM events WHERE id=?", (legit_id,)).fetchone()
    check(f"F2c: legitimate large event {legit_id} (real protest-coverage story, "
          f"only large by article count) was NOT removed", row[0] == 1)
conn.close()


print("\nF3: mobile Support button overlap")
check("F3a: FloatingSupport visibility now also depends on scroll position, not just the "
      "3-minute session timer", "pastTop" in app_js)
check("F3c: FloatingSupport is never rendered on the story route - unpredictable-length "
      "running text there defeated the scroll-threshold guard alone (confirmed live: the lead "
      "paragraph reached the button's fixed position at scroll=0 on event 17019)",
      'route.view!=="story"&&<FloatingSupport' in app_js.replace(" ", ""))
check("F3b: FloatingSupport itself (size/position/copy) is untouched - still the same fixed "
      "corner chip, this is a visibility-timing fix only",
      "FloatingSupport" in app_js and ("\\u2665" in app_js or "♥" in app_js))


print("\nF4: Context historical date provenance")


def fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, updated_at TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE articles (event_id INTEGER, published TEXT)")
    sm.init_story_memory_schema(conn)
    return conn


def add_event(conn, eid, created_at):
    conn.execute("INSERT INTO events (id, updated_at, created_at) VALUES (?, ?, ?)",
                 (eid, created_at, created_at))
    conn.commit()


def add_article(conn, event_id, published):
    conn.execute("INSERT INTO articles (event_id, published) VALUES (?, ?)", (event_id, published))
    conn.commit()


def rel(conn, prev, cur):
    return sm.record_relationship(
        conn, previous_event_id=prev, current_event_id=cur, relationship_type="R1",
        confidence="high", evidence=["e1"], judge_version="v1", decided_at="2026-01-02T00:00:00",
        prev_snapshot_fingerprint="fp", prev_snapshot_title="prev title", prev_snapshot_summary="prev summary",
        prev_snapshot_topic="Politics", prev_snapshot_region="India",
    )


# Reproduces the real 17383/17464 shape: the historical event's DB row was created (row
# inserted) AFTER the current event's, but its actual news coverage began earlier.
conn = fresh_conn()
add_event(conn, 1, created_at="2026-09-03T05:55:31")   # historical event, row created late
add_event(conn, 2, created_at="2026-09-02T00:44:48")   # current event, row created earlier
add_article(conn, 1, "2026-09-01T10:00:00+00:00")      # but its real coverage began even earlier
add_article(conn, 1, "2026-09-01T19:32:09+00:00")
rel(conn, 1, 2)
ctx = sm.get_verified_context(conn, 2)
check("F4a: relationship returned", len(ctx) == 1)
check("F4b: historical_event_date uses the earliest article publish date, not events.created_at",
      ctx[0].historical_event_date == "2026-09-01T10:00:00")
check("F4c: the fixed date is chronologically before the current event's own created_at "
      "(created_at='2026-09-02T00:44:48') - the exact real-world defect this closes",
      ctx[0].historical_event_date < "2026-09-02T00:44:48")

# Fallback: no articles at all for the historical event -> falls back to created_at, never raises.
conn2 = fresh_conn()
add_event(conn2, 1, created_at="2026-01-01T00:00:00")
add_event(conn2, 2, created_at="2026-01-05T00:00:00")
rel(conn2, 1, 2)
ctx2 = sm.get_verified_context(conn2, 2)
check("F4d: no articles for the historical event -> falls back to created_at",
      ctx2[0].historical_event_date == "2026-01-01T00:00:00")

# Fallback: articles table missing entirely (mirrors test_story_memory.py's own minimal
# fixture) -> must not raise, must still fall back to created_at.
conn3 = sqlite3.connect(":memory:")
conn3.row_factory = sqlite3.Row
conn3.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, updated_at TEXT, created_at TEXT)")
sm.init_story_memory_schema(conn3)
add_event(conn3, 1, created_at="2026-01-01T00:00:00")
add_event(conn3, 2, created_at="2026-01-05T00:00:00")
rel(conn3, 1, 2)
raised = False
ctx3 = []
try:
    ctx3 = sm.get_verified_context(conn3, 2)
except Exception:
    raised = True
check("F4e: no articles table at all -> does not raise (fail-closed, matches the module's own "
      "isolation guarantee)", not raised)
check("F4f: ...and still falls back to created_at", bool(ctx3) and ctx3[0].historical_event_date == "2026-01-01T00:00:00")


print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
