"""
test_phase27.py - Paksh 2.7 focused tests: content_cache correctness,
single-flight behavior, fallback behavior, and API compatibility.

Does NOT touch production Supabase data or SQLite writes. Follows the same
"NOT a recreation of the historical suite" convention as test_phase22.py.

Run:  py test_phase27.py
"""
import json
import sys
import threading
import time

import content_cache
import main as main_module
import supabase_content as sb

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# ============================================================ 1: basic hit/build/TTL
print("=== 1: basic build, hit, TTL expiry (fake builder, no network) ===")
content_cache.invalidate()
calls = {"n": 0}


def fake_builder():
    calls["n"] += 1
    return {"events": [{"id": 1}, {"id": 2}]}


v1, s1 = content_cache.get_or_build("t1", fake_builder, ttl=0.3)
check("first call builds", s1 == "built" and calls["n"] == 1)
v2, s2 = content_cache.get_or_build("t1", fake_builder, ttl=0.3)
check("second call within TTL hits (no rebuild)", s2 == "hit" and calls["n"] == 1)
time.sleep(0.4)
v3, s3 = content_cache.get_or_build("t1", fake_builder, ttl=0.3)
check("call after TTL expiry rebuilds", s3 == "built" and calls["n"] == 2)


# ============================================================ 2: single-flight
print("\n=== 2: single-flight under concurrency (20 threads, 1 slow builder) ===")
content_cache.invalidate()
build_count = {"n": 0}
build_lock = threading.Lock()


def slow_builder():
    with build_lock:
        build_count["n"] += 1
    time.sleep(0.5)  # simulate a slow Supabase fetch
    return {"events": [{"id": i} for i in range(5)]}


results = []
results_lock = threading.Lock()


def worker():
    v, s = content_cache.get_or_build("t2", slow_builder, ttl=60)
    with results_lock:
        results.append(s)


threads = [threading.Thread(target=worker) for _ in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()

check("exactly 1 build occurred despite 20 concurrent callers", build_count["n"] == 1)
check("all 20 callers got a result", len(results) == 20)
check("exactly one caller saw status='built', the rest saw hit/hit-after-wait",
      results.count("built") == 1 and all(s in ("built", "hit-after-wait", "hit") for s in results))


# ============================================================ 3: atomicity / failure fallback
print("\n=== 3: failed refresh preserves previous valid cache (never serves partial/corrupt) ===")
content_cache.invalidate()
content_cache.get_or_build("t3", lambda: {"events": [{"id": 99}]}, ttl=0.2)


def failing_builder():
    raise RuntimeError("simulated Supabase outage")


time.sleep(0.3)  # let the entry go stale
v, s = content_cache.get_or_build("t3", failing_builder, ttl=0.2)
check("a failing refresh serves the previous valid entry, not an error", s == "hit-stale-refresh-failed")
check("the served value is the ORIGINAL valid data, unchanged", v == {"events": [{"id": 99}]})


def incomplete_builder():
    return {"events": []}  # fails _default_is_complete


time.sleep(0.3)
v2, s2 = content_cache.get_or_build("t3", incomplete_builder, ttl=0.2)
check("an incomplete refresh also preserves the previous valid entry", s2 == "hit-stale-incomplete")
check("incomplete refresh does not corrupt the served value", v2 == {"events": [{"id": 99}]})


# ============================================================ 4: no-prior-cache exception propagation
print("\n=== 4: no prior cache + builder fails -> original exception propagates ===")
content_cache.invalidate()


class _CustomUnavailable(Exception):
    pass


def raises_custom():
    raise _CustomUnavailable("simulated")


try:
    content_cache.get_or_build("t4", raises_custom, ttl=60)
    check("exception propagates when there's no fallback", False)
except _CustomUnavailable:
    check("exception propagates when there's no fallback", True)

content_cache.invalidate()
try:
    content_cache.get_or_build("t4b", lambda: {"events": []}, ttl=60,
                                unavailable_exc=_CustomUnavailable)
    check("incomplete + no fallback raises unavailable_exc (fallback-compatible)", False)
except _CustomUnavailable:
    check("incomplete + no fallback raises unavailable_exc (fallback-compatible)", True)


# ============================================================ 5: real Supabase - shape/ordering/zero-calls-on-hit
print("\n=== 5: real Supabase - shape, ordering, and PROOF of zero Supabase calls on a cache hit ===")
content_cache.invalidate()
try:
    before = sb.request_count
    r1, s1 = content_cache.get_or_build("events", sb.get_events, unavailable_exc=sb.SupabaseUnavailable)
    after_build = sb.request_count
    check("first call actually hit Supabase (request_count increased)", after_build > before)
    check("first call status is 'built'", s1 == "built")

    r2, s2 = content_cache.get_or_build("events", sb.get_events, unavailable_exc=sb.SupabaseUnavailable)
    after_hit = sb.request_count
    check("SUCCESS CRITERION A: cache-hit call makes ZERO additional Supabase requests",
          after_hit == after_build)
    check("cache hit returns byte-identical payload to the build", r1 == r2)

    ids = [e["id"] for e in r1["events"]]
    check("no duplicate ids in cached events", len(ids) == len(set(ids)))
    created = [e["created_at"] for e in r1["events"]]
    check("ordering: created_at remains non-increasing (DESC)",
          all(created[i] >= created[i + 1] for i in range(len(created) - 1)))
    # Paksh phase 5E: this assertion predates Phase 2's payload trim and still
    # asserted the OLD, pre-_lighten() field set (summary_points/summary_points_hi
    # included) - stale, not a real regression, since get_events() now intentionally
    # applies _lighten() (see supabase_content.get_events()). Updated to the CURRENT
    # intended contract: the field set Phase 2 shipped and phase 4's production
    # deploy verified live (summary_points/summary_points_hi absent, summary/
    # summary_hi truncated to a snippet). The test's real purpose - proving caching
    # itself never silently alters the row shape - is unchanged and still enforced.
    expected_keys = {"id", "title", "summary", "title_hi", "summary_hi",
                      "topic", "region", "lang", "image_url", "is_demo",
                      "source_count", "summary_method", "lean_counts", "international",
                      "dominant", "blindspot", "created_at", "published_at", "storyline_id",
                      "importance", "feed_rank"}
    check("SUCCESS CRITERION F: cached event row has the same field set as before caching",
          set(r1["events"][0].keys()) == expected_keys)
    check("SUCCESS CRITERION G: summary_points/summary_points_hi do not silently "
          "return (Phase 2 contract)",
          "summary_points" not in r1["events"][0] and "summary_points_hi" not in r1["events"][0])
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED (Supabase unreachable from this environment: {e})")

content_cache.invalidate()
try:
    before = sb.request_count
    r1, s1 = content_cache.get_or_build("blindspots", sb.get_blindspots, unavailable_exc=sb.SupabaseUnavailable)
    after_build = sb.request_count
    r2, s2 = content_cache.get_or_build("blindspots", sb.get_blindspots, unavailable_exc=sb.SupabaseUnavailable)
    after_hit = sb.request_count
    check("SUCCESS CRITERION B: blindspots cache-hit makes ZERO additional Supabase requests",
          after_hit == after_build)
    check("blindspots cache hit returns identical payload", r1 == r2)
    ids = [e["id"] for e in r1["events"]]
    check("no duplicate blindspot ids", len(ids) == len(set(ids)))
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED (Supabase unreachable: {e})")

content_cache.invalidate()


# ============================================================ 6: main.py routes still work (SQLite mode unaffected)
print("\n=== 6: main.py routes unaffected outside Supabase mode ===")
check("main.CONTENT_BACKEND is 'sqlite' by default (unchanged)", main_module.CONTENT_BACKEND == "sqlite")
r = main_module.list_events()
check("SQLite-mode /api/events still works (cache module not invoked)", len(r["events"]) > 0)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL ASSERTIONS PASSED")
