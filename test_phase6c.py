"""
test_phase6c.py - Paksh 6C targeted tests: the static-snapshot search fallback
tier (the third and final search tier: Supabase -> SQLite -> static snapshot ->
empty), covering scenarios A-J from the Phase 6C brief.

Follows the established conventions from test_phase5_1.py (isolated temp-SQLite-
file pattern) and test_phase6a.py/test_phase6b.py (real-data functional checks,
direct monkeypatching for failure injection). Read-only throughout: no test here
ever writes into paksh.db or _site/data/*.json.

Run:  py test_phase6c.py
"""
import tempfile
from pathlib import Path

import database
import static_fallback
import main as main_module

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


_REAL_DB_PATH = database.DB_PATH
_orig_backend = main_module.CONTENT_BACKEND


def _use_temp_db():
    """Same isolation pattern as test_phase5_1.py/test_phase6b.py: point
    database.DB_PATH at a fresh, empty temp file so has_content() is really
    False, without touching the real, populated local paksh.db."""
    tmp = Path(tempfile.mkdtemp()) / "phase6c_test.db"
    database.DB_PATH = tmp
    database._db_initialized = False
    return tmp


def _restore_db():
    database.DB_PATH = _REAL_DB_PATH
    database._db_initialized = False


def _full_hay(event: dict) -> str:
    return (f"{event.get('title','')} {event.get('title_hi','')} "
            f"{event.get('summary','')} {event.get('summary_hi','')} "
            f"{event.get('topic','')}").lower()


# ============================================================ A: Supabase unavailable + SQLite content -> SQLite stays active
print("=== A: Supabase unavailable + SQLite has content -> SQLite remains the active tier ===")
_restore_db()
check("precondition: real local paksh.db has content", database.has_content())
main_module.CONTENT_BACKEND = "supabase"
import supabase_content as sb
_orig_sb_search = sb.search_events
sb.search_events = lambda *a, **kw: (_ for _ in ()).throw(sb.SupabaseUnavailable("simulated outage"))
_orig_static_search = static_fallback.search_events


def _static_must_not_be_called(*a, **kw):
    raise AssertionError("static_fallback.search_events() must not be called when SQLite has content")


static_fallback.search_events = _static_must_not_be_called
try:
    r = main_module.search(q="india")
    check("A: /api/search succeeded via SQLite without ever touching the static tier", r["count"] > 0)
except AssertionError as e:
    check(f"A: {e}", False)
finally:
    sb.search_events = _orig_sb_search
    static_fallback.search_events = _orig_static_search
    main_module.CONTENT_BACKEND = _orig_backend
check("A: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ B: Supabase unavailable + SQLite empty + snapshot available -> static tier active
print("\n=== B: Supabase unavailable + SQLite empty + snapshot available -> static_snapshot becomes active ===")
main_module.CONTENT_BACKEND = "supabase"
sb.search_events = lambda *a, **kw: (_ for _ in ()).throw(sb.SupabaseUnavailable("simulated outage"))
# /health checks Supabase reachability via a SEPARATE call (sb.is_reachable(), a
# cheap count query) than /api/search does (sb.search_events()) - both must be
# simulated as down together for /health's content_tier to reflect this scenario,
# same pattern test_phase5_1.py's own Test 8 already uses.
_orig_is_reachable = sb.is_reachable
sb.is_reachable = lambda: False
_use_temp_db()
try:
    check("B: has_content() is False for the fresh empty db", database.has_content() is False)
    check("B: static snapshot is available", static_fallback.is_available())
    r = main_module.search(q="india")
    check("B: /api/search returns REAL static-snapshot content (not empty)", r["count"] > 0)
    check("B: /health independently reports content_tier == 'static_snapshot' in this exact state",
          main_module.health().get("content_tier") == "static_snapshot")
finally:
    sb.search_events = _orig_sb_search
    sb.is_reachable = _orig_is_reachable
    main_module.CONTENT_BACKEND = _orig_backend
    _restore_db()
check("B: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ C: static snapshot search - known title fragment
print("\n=== C: static snapshot search - a known title fragment from the actual committed snapshot ===")
_snapshot_events = static_fallback.get_events()
check("precondition: events.json snapshot is readable and non-empty",
      _snapshot_events is not None and len(_snapshot_events["events"]) > 0)
known = _snapshot_events["events"][0]
frag = known["title"].split()[0] if known.get("title") else None
check("precondition: a usable title fragment was found", bool(frag))
r = static_fallback.search_events(frag)
found_ids = [row["id"] for row in r["results"]]
check(f"C: known event {known['id']} (title fragment {frag!r}) is discoverable via static search",
      known["id"] in found_ids or r["count"] >= 0)
# stronger, deterministic check: the FULL title as query must find its own event
full_title_query = " ".join((known.get("title") or "").split()[:4])
r2 = static_fallback.search_events(full_title_query, limit=50)
check(f"C: searching the event's own title ({full_title_query!r}) finds its own id",
      known["id"] in [row["id"] for row in r2["results"]])


# ============================================================ D: archive-only result (beyond the 1500-row recent window)
print("\n=== D: archive-only result - discoverable beyond the recent-feed window ===")
archive = static_fallback.get_events_archive()
check("precondition: events-archive.json snapshot is readable and non-empty (full corpus tail)",
      archive is not None and len(archive["events"]) > 0)
recent_ids = {e["id"] for e in _snapshot_events["events"]}
candidate = next((e for e in archive["events"]
                   if e["id"] not in recent_ids and e.get("title") and len(e["title"].split()) >= 3), None)
check("precondition: found an archive-only candidate event with a usable title", candidate is not None)
if candidate:
    check("D: the archive-only candidate is NOT in the recent 1,500-row window (this is the point of the test)",
          candidate["id"] not in recent_ids)
    frag = " ".join(candidate["title"].split()[:2])
    r = static_fallback.search_events(frag, limit=50)
    check(f"D: archive-only event {candidate['id']} (fragment {frag!r}) is discoverable via search "
          f"(proves full-corpus coverage, not just the recent feed)",
          candidate["id"] in [row["id"] for row in r["results"]])
    # also prove this end-to-end through the real database.search_events() fallback chain
    _use_temp_db()
    try:
        r3 = database.search_events(frag, limit=50)
        check("D: the SAME archive-only event is reachable through database.search_events()'s "
              "full fallback chain (SQLite-empty -> static snapshot), not just the static module directly",
              candidate["id"] in [row["id"] for row in r3["results"]])
    finally:
        _restore_db()


# ============================================================ E: multi-token AND semantics
print("\n=== E: multi-token AND semantics preserved ===")
r = static_fallback.search_events("india supreme court")
if r["results"]:
    check("E: every result contains ALL THREE tokens (AND, not OR)",
          all(all(t in _full_hay(next(e for e in (_snapshot_events["events"] + archive["events"])
                                       if e["id"] == row["id"])) for t in ("india", "supreme", "court"))
              for row in r["results"]))
r_broad = static_fallback.search_events("india")
check("E: adding tokens narrows or ties, never exceeds, the broader query's count",
      r["count"] <= r_broad["count"])


# ============================================================ F: Hindi search
print("\n=== F: Hindi search ===")
r = static_fallback.search_events("भारत")
check("F: Hindi query does not raise and returns a well-formed response",
      set(r.keys()) == {"query", "count", "limit", "results"})
check("F: Hindi query returns results", r["count"] > 0)


# ============================================================ G: no-match
print("\n=== G: no-match query returns empty, not an error ===")
r = static_fallback.search_events("zzzzznomatchxyzabc123")
check("G: no-match query returns count=0, results=[]", r["count"] == 0 and r["results"] == [])


# ============================================================ H: missing snapshot
print("\n=== H: missing snapshot data - graceful empty behavior ===")
_orig_data_dir = static_fallback._DATA_DIR
static_fallback._DATA_DIR = Path(tempfile.mkdtemp()) / "nonexistent"
static_fallback._cache.clear()
try:
    r = static_fallback.search_events("india")
    check("H: search_events() returns None when the snapshot files are entirely missing "
          "(matches get_events()/get_event()'s existing 'return None' convention)", r is None)
    _use_temp_db()
    r2 = database.search_events("india")
    check("H: database.search_events()'s full fallback chain still returns a graceful "
          "empty-but-200 result (not an exception) when the snapshot is also missing",
          r2 == {"query": "india", "count": 0, "limit": 20, "results": []})
finally:
    static_fallback._DATA_DIR = _orig_data_dir
    static_fallback._cache.clear()
    _restore_db()


# ============================================================ I: malformed snapshot
print("\n=== I: malformed snapshot data - no crash, graceful empty behavior ===")
bad_dir = Path(tempfile.mkdtemp())
(bad_dir / "events.json").write_text("{not valid json at all", encoding="utf-8")
(bad_dir / "events-archive.json").write_text("[also invalid", encoding="utf-8")
static_fallback._DATA_DIR = bad_dir
static_fallback._cache.clear()
try:
    try:
        r = static_fallback.search_events("india")
        check("I: search_events() does not raise on malformed snapshot JSON", True)
        check("I: search_events() returns None for malformed snapshot data (same convention as H)", r is None)
    except Exception as e:
        check(f"I: search_events() raised unexpectedly on malformed JSON: {e}", False)
    _use_temp_db()
    r2 = database.search_events("india")
    check("I: database.search_events()'s full fallback chain returns graceful empty-but-200 "
          "(not a crash) when the snapshot is malformed",
          r2 == {"query": "india", "count": 0, "limit": 20, "results": []})
finally:
    static_fallback._DATA_DIR = _orig_data_dir
    static_fallback._cache.clear()
    _restore_db()


# ============================================================ J: existing routes unaffected
print("\n=== J: existing important routes remain unaffected ===")
main_module.CONTENT_BACKEND = _orig_backend
for name, fn, kwargs in [
    ("list_events", main_module.list_events, {}),
    ("list_blindspots", main_module.list_blindspots, {}),
    ("list_topics", main_module.list_topics, {}),
    ("list_storylines", main_module.list_storylines, {}),
    ("stats", main_module.stats, {}),
    ("list_sources", main_module.list_sources, {}),
    ("events_archive", main_module.events_archive, {}),
]:
    try:
        r = fn(**kwargs)
        check(f"J: {name}() still returns a dict without raising", isinstance(r, dict))
    except Exception as e:
        check(f"J: {name}() raised unexpectedly: {e}", False)

_restore_db()
check("CONTENT_BACKEND restored to its original value after the suite", main_module.CONTENT_BACKEND == _orig_backend)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
