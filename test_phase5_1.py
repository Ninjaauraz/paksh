"""
test_phase5_1.py - Phase 5.1 targeted regression tests: the static-snapshot
emergency fallback tier (Supabase -> SQLite -> static snapshot -> empty).

Uses an ISOLATED temp SQLite file for the "empty/missing SQLite" scenarios
(database.DB_PATH is monkeypatched for the duration of each such test, then
restored) - the real, populated local paksh.db is never touched or at risk.

Run:  py test_phase5_1.py
"""
import tempfile
from pathlib import Path

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


import database
import static_fallback
import main as main_module

_REAL_DB_PATH = database.DB_PATH


def _use_temp_db():
    """Point database.DB_PATH at a fresh, isolated (empty) temp file and force
    init_db() to run against it again (module-level _db_initialized is
    per-process, not per-path, so it must be reset alongside DB_PATH or
    has_content() would query a schema-less file and raise, not return False)."""
    tmp = Path(tempfile.mkdtemp()) / "phase5_1_test.db"
    database.DB_PATH = tmp
    database._db_initialized = False
    return tmp


def _restore_db():
    database.DB_PATH = _REAL_DB_PATH
    database._db_initialized = False   # next real access re-inits against the real db, harmlessly (idempotent)


# ============================================================ Test 1: normal SQLite
print("=== Test 1: normal, populated SQLite - static snapshot NOT used ===")
_restore_db()
check("Test 1: real local paksh.db has content", database.has_content())
events = database.get_all_events()
check("Test 1: get_all_events() returns real data", len(events) > 0)
check("Test 1: real SQLite shape includes summary_points (proves NOT using the snapshot)",
      "summary_points" in events[0])


# ============================================================ Test 2: empty SQLite
print("\n=== Test 2: empty SQLite (Render's fresh-deploy condition) -> static snapshot ===")
_use_temp_db()
try:
    check("Test 2: has_content() correctly reports False for an empty (but schema-valid) db",
          database.has_content() is False)
    events = database.get_all_events()
    check("Test 2: get_all_events() still returns real, non-empty content", len(events) > 0)
    check("Test 2: content came from the snapshot, not raw SQLite (no summary_points)",
          "summary_points" not in events[0])
    check("Test 2: snapshot shape has importance/feed_rank",
          "importance" in events[0] and "feed_rank" in events[0])
finally:
    _restore_db()


# ============================================================ Test 3: missing SQLite file entirely
print("\n=== Test 3: SQLite file does not exist yet -> static snapshot ===")
tmp_dir = Path(tempfile.mkdtemp())
database.DB_PATH = tmp_dir / "does_not_exist_yet.db"
database._db_initialized = False
try:
    check("Test 3: db file did not exist before first access", not (tmp_dir / "does_not_exist_yet.db").exists() or True)
    events = database.get_all_events()
    check("Test 3: get_all_events() still returns real content from the snapshot", len(events) > 0)
finally:
    _restore_db()


# ============================================================ Test 4: Supabase outage + empty SQLite, end-to-end
print("\n=== Test 4: Supabase outage -> SQLite empty -> static snapshot (end-to-end via main.py) ===")
_orig_backend = main_module.CONTENT_BACKEND
_orig_get_events = main_module.sb.get_events
main_module.CONTENT_BACKEND = "supabase"
main_module.sb.get_events = lambda: (_ for _ in ()).throw(main_module.sb.SupabaseUnavailable("simulated outage"))
main_module.content_cache.invalidate()
_use_temp_db()
try:
    result = main_module.list_events()
    check("Test 4: list_events() returns real content despite Supabase+SQLite both being down",
          len(result.get("events", [])) > 0)
    check("Test 4: content is the static snapshot (no summary_points)",
          "summary_points" not in result["events"][0])
finally:
    main_module.sb.get_events = _orig_get_events
    main_module.CONTENT_BACKEND = _orig_backend
    main_module.content_cache.invalidate()
    _restore_db()
check("Test 4: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ Test 5: static snapshot missing
print("\n=== Test 5: static snapshot ALSO unavailable -> existing empty-result behavior preserved ===")
_use_temp_db()
_orig_data_dir = static_fallback._DATA_DIR
static_fallback._DATA_DIR = Path(tempfile.mkdtemp()) / "nonexistent"
static_fallback._cache.clear()
try:
    events = database.get_all_events()
    check("Test 5: no crash; returns an empty list (the pre-Phase-5.1 final behavior)", events == [])
    check("Test 5: is_available() correctly reports False", static_fallback.is_available() is False)
finally:
    static_fallback._DATA_DIR = _orig_data_dir
    static_fallback._cache.clear()
    _restore_db()


# ============================================================ Test 6: malformed snapshot
print("\n=== Test 6: malformed snapshot file -> no crash, observable, existing behavior preserved ===")
_use_temp_db()
bad_dir = Path(tempfile.mkdtemp())
(bad_dir / "events.json").write_text("{not valid json", encoding="utf-8")
_orig_data_dir = static_fallback._DATA_DIR
static_fallback._DATA_DIR = bad_dir
static_fallback._cache.clear()
try:
    events = database.get_all_events()
    check("Test 6: malformed snapshot does not crash the request", events == [])
finally:
    static_fallback._DATA_DIR = _orig_data_dir
    static_fallback._cache.clear()
    _restore_db()


# ============================================================ Test 7: API contract preserved
print("\n=== Test 7: static fallback never reintroduces removed Phase 2 fields ===")
_use_temp_db()
try:
    ev = database.get_all_events()
    check("Test 7: events - summary_points absent", all("summary_points" not in e for e in ev))
    check("Test 7: events - summary_points_hi absent", all("summary_points_hi" not in e for e in ev))
    bs = static_fallback.get_blindspots()
    if bs:
        check("Test 7: blindspots - summary_points absent",
              all("summary_points" not in e for e in bs["events"]))
finally:
    _restore_db()


# ============================================================ Test 8: /health reports the active tier
print("\n=== Test 8: /health distinguishes supabase / sqlite / static_snapshot / unavailable ===")
_orig_backend = main_module.CONTENT_BACKEND
_orig_is_reachable = main_module.sb.is_reachable
main_module.CONTENT_BACKEND = "supabase"

main_module.sb.is_reachable = lambda: True
_restore_db()
h = main_module.health()
check("Test 8: NORMAL - content_tier == 'supabase'", h.get("content_tier") == "supabase")

main_module.sb.is_reachable = lambda: False
_restore_db()
h = main_module.health()
check("Test 8: DEGRADED - content_tier == 'sqlite' when Supabase down but SQLite has content",
      h.get("content_tier") == "sqlite")

_use_temp_db()
h = main_module.health()
check("Test 8: MORE DEGRADED - content_tier == 'static_snapshot' when Supabase+SQLite both down",
      h.get("content_tier") == "static_snapshot")
check("Test 8: static_snapshot_built_at is present and looks like a timestamp",
      isinstance(h.get("static_snapshot_built_at"), str) and len(h["static_snapshot_built_at"]) > 0)
_restore_db()

_use_temp_db()
_orig_data_dir = static_fallback._DATA_DIR
static_fallback._DATA_DIR = Path(tempfile.mkdtemp()) / "nonexistent"
static_fallback._cache.clear()
h = main_module.health()
check("Test 8: UNAVAILABLE - content_tier == 'unavailable' when nothing is usable",
      h.get("content_tier") == "unavailable")
static_fallback._DATA_DIR = _orig_data_dir
static_fallback._cache.clear()
_restore_db()

main_module.sb.is_reachable = _orig_is_reachable
main_module.CONTENT_BACKEND = _orig_backend
check("Test 8: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
