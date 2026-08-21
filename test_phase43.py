"""
test_phase43.py - Paksh 4.3 focused tests: /api/stats backend-toggle correctness
and the /api/sources axes/subscores contract parity between SQLite and Supabase.

Does NOT touch production Supabase data or SQLite writes. Follows the same
"NOT a recreation of the historical suite" convention as test_phase22.py /
test_phase27.py.

Run:  py test_phase43.py
"""
import sys

import sources
import supabase_content as sb
import main as main_module

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# ============================================================ 1: /api/stats, SQLite mode (default)
print("=== 1: /api/stats in SQLite mode (main.CONTENT_BACKEND default) ===")
check("main.CONTENT_BACKEND is 'sqlite' by default (unchanged)", main_module.CONTENT_BACKEND == "sqlite")
r = main_module.stats()
check("SQLite stats has all 4 expected keys", set(r.keys()) == {"events", "articles", "sources", "blindspots"})
check("SQLite stats: events > 0 (real count, not hardcoded)", r["events"] > 0)
check("SQLite stats: articles > 0", r["articles"] > 0)
check("SQLite stats: sources == len(sources.SOURCES) (not hardcoded)", r["sources"] == len(sources.SOURCES))
check("SQLite stats: blindspots > 0", r["blindspots"] > 0)


# ============================================================ 2: get_stats() against real Supabase
print("\n=== 2: supabase_content.get_stats() against real Supabase (network) ===")
try:
    s = sb.get_stats()
    check("Supabase stats has all 4 expected keys (same shape as SQLite)",
          set(s.keys()) == {"events", "articles", "sources", "blindspots"})
    check("Supabase stats: events > 0 (real count_exact, not hardcoded/zero)", s["events"] > 0)
    check("Supabase stats: articles > 0", s["articles"] > 0)
    check("Supabase stats: sources == 124 curated outlets (matches SQLite registry size)",
          s["sources"] == len(sources.SOURCES))
    check("Supabase stats: blindspots > 0", s["blindspots"] > 0)
    # the exact bug this phase fixes: SQLite-only /api/stats returned zeros
    # for events/articles/blindspots when CONTENT_BACKEND=supabase (Phase 3.6/4.0
    # finding), because paksh.db doesn't exist on the Supabase-backed deployment.
    check("Supabase stats are NOT the old all-zero misleading response",
          not (s["events"] == 0 and s["articles"] == 0 and s["blindspots"] == 0))
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED (Supabase unreachable: {e})")


# ============================================================ 3: /api/stats, Supabase mode end-to-end via main.py
print("\n=== 3: /api/stats end-to-end with CONTENT_BACKEND=supabase ===")
_orig_backend = main_module.CONTENT_BACKEND
main_module.CONTENT_BACKEND = "supabase"
try:
    r = main_module.stats()
    check("main.stats() in supabase mode returns the Supabase-backed values",
          r["events"] > 0 and r["articles"] > 0 and r["blindspots"] > 0)
    check("main.stats() response shape unchanged (backwards compatible)",
          set(r.keys()) == {"events", "articles", "sources", "blindspots"})
finally:
    main_module.CONTENT_BACKEND = _orig_backend
check("CONTENT_BACKEND restored to its original value after the test", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ 4: /api/stats falls back to SQLite on Supabase failure
print("\n=== 4: /api/stats fail-safe fallback (Supabase unreachable -> SQLite) ===")
_orig_get_stats = sb.get_stats


def _broken_get_stats():
    raise sb.SupabaseUnavailable("simulated outage for test 4")


main_module.CONTENT_BACKEND = "supabase"
sb.get_stats = _broken_get_stats
try:
    r = main_module.stats()
    check("stats() falls back to real SQLite data on SupabaseUnavailable (not a 500, not zeros)",
          r["events"] > 0 and r["sources"] == len(sources.SOURCES))
finally:
    sb.get_stats = _orig_get_stats
    main_module.CONTENT_BACKEND = _orig_backend
check("get_stats and CONTENT_BACKEND restored after the fallback test",
      sb.get_stats is _orig_get_stats and main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ 5: /api/sources contract parity (SQLite vs Supabase)
print("\n=== 5: /api/sources - SQLite and Supabase expose the SAME public contract ===")
main_module.CONTENT_BACKEND = "sqlite"
sqlite_sources = main_module.list_sources()
check("SQLite /api/sources: 124 sources", len(sqlite_sources["sources"]) == 124)
check("SQLite /api/sources: rationale present on every source",
      all(s.get("rationale") for s in sqlite_sources["sources"]))
check("SQLite /api/sources: axes present on every source",
      all(s.get("axes") for s in sqlite_sources["sources"]))
check("SQLite /api/sources: subscores is NOT in the response (fixed by this phase)",
      not any("subscores" in s for s in sqlite_sources["sources"]))
AXIS_KEYS = {"secular_authoritative", "market_orientation", "incumbent_stance"}
check("SQLite /api/sources: every axes dict has exactly the 3 known keys",
      all(set(s["axes"].keys()) == AXIS_KEYS for s in sqlite_sources["sources"]))
check("SQLite /api/sources: all axis values are 0-100",
      all(0 <= v <= 100 for s in sqlite_sources["sources"] for v in s["axes"].values()))

try:
    main_module.CONTENT_BACKEND = "supabase"
    supabase_sources = main_module.list_sources()
    check("Supabase /api/sources: 124 sources", len(supabase_sources["sources"]) == 124)
    check("Supabase /api/sources: subscores is NOT in the response (unchanged, already correct)",
          not any("subscores" in s for s in supabase_sources["sources"]))
    sqlite_by_name = {s["name"]: s for s in sqlite_sources["sources"]}
    mismatches = [
        s["name"] for s in supabase_sources["sources"]
        if s["name"] in sqlite_by_name and s["axes"] != sqlite_by_name[s["name"]]["axes"]
    ]
    check("SQLite and Supabase report IDENTICAL axes values per source (same canonical sources.py origin)",
          len(mismatches) == 0)
    rationale_mismatches = [
        s["name"] for s in supabase_sources["sources"]
        if s["name"] in sqlite_by_name and s["rationale"] != sqlite_by_name[s["name"]]["rationale"]
    ]
    check("SQLite and Supabase report IDENTICAL rationale text per source",
          len(rationale_mismatches) == 0)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED Supabase half of contract-parity check (Supabase unreachable: {e})")
finally:
    main_module.CONTENT_BACKEND = _orig_backend


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL ASSERTIONS PASSED")
