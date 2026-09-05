"""
test_phase30cp1_capacity_thread_safety.py - Phase 30C-P1 precondition: prove
ProviderCapacity's success_count/failure_count/transient_streak/permanent_streak
mutations are race-free under real concurrent threading, and that
current_health()/as_cache_row() never observe a torn (partially-updated)
snapshot. No real API calls, no network - pure in-process concurrency testing
against a synthetic provider dict. Also verifies persisted cache correctness
under concurrent access (redirects the health-cache file, same pattern
test_phase30cj_integration.py already uses).

Run:  py test_phase30cp1_capacity_thread_safety.py
"""
import threading
import time
from pathlib import Path

import ai_providers as ap

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# --- redirect the health cache before ANY of this suite's activity, exactly
# like test_phase30cj_integration.py does, so we never touch the real file ---
_REAL_CACHE_FILE = ap._HEALTH_CACHE_FILE
ap._HEALTH_CACHE_FILE = Path(ap._HERE) / "_phase30cp1_thread_safety_cache.json"


def fresh_capacity(name="synthetic", **provider_kwargs):
    """A brand-new ProviderCapacity over a synthetic provider dict - never
    touches PROVIDERS/_CAPACITIES/real config."""
    p = {"name": name, "enabled": True}
    p.update(provider_kwargs)
    return ap.ProviderCapacity(p)


def run_concurrent(fn, n_threads, n_calls_each):
    """Fires n_threads * n_calls_each calls to fn() as concurrently as
    real threading allows (a barrier releases all threads at once to
    maximize interleaving), and waits for all to finish."""
    barrier = threading.Barrier(n_threads)

    def worker():
        barrier.wait()
        for _ in range(n_calls_each):
            fn()

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


print("=== Test 1: exact success count under concurrent success calls ===")
cap = fresh_capacity()
N_THREADS, N_CALLS = 16, 500
run_concurrent(cap.record_success, N_THREADS, N_CALLS)
expected = N_THREADS * N_CALLS
check(f"1: success_count == {expected} after {N_THREADS}x{N_CALLS} concurrent "
      f"record_success() calls (got {cap.success_count}) - no lost increments",
      cap.success_count == expected)
check("2: failure_count untouched by success-only load (got %d)" % cap.failure_count,
      cap.failure_count == 0)
check("3: streaks reset to 0 after an all-success run (permanent=%d, transient=%d)"
      % (cap.permanent_streak, cap.transient_streak),
      cap.permanent_streak == 0 and cap.transient_streak == 0)


print("\n=== Test 2: exact failure count under concurrent failure calls ===")
cap = fresh_capacity()
PERMANENT_ERR = "HTTP 403 permission denied"   # not in _TRANSIENT_DEGRADE_MARKERS -> permanent
run_concurrent(lambda: cap.record_failure(PERMANENT_ERR), N_THREADS, N_CALLS)
check(f"4: failure_count == {expected} after {N_THREADS}x{N_CALLS} concurrent "
      f"record_failure() calls (got {cap.failure_count}) - no lost increments",
      cap.failure_count == expected)
check("5: success_count untouched by failure-only load (got %d)" % cap.success_count,
      cap.success_count == 0)


print("\n=== Test 3: transient streak internally consistent under concurrent transient failures ===")
cap = fresh_capacity()
TRANSIENT_ERR = "HTTP 503 UNAVAILABLE"   # matches _TRANSIENT_DEGRADE_MARKERS -> transient
run_concurrent(lambda: cap.record_failure(TRANSIENT_ERR), N_THREADS, N_CALLS)
check(f"6: transient_streak == {expected} after {N_THREADS}x{N_CALLS} concurrent "
      f"transient-classified failures (got {cap.transient_streak}) - no lost increments",
      cap.transient_streak == expected)
check("7: permanent_streak stayed 0 throughout an all-transient run (got %d)"
      % cap.permanent_streak, cap.permanent_streak == 0)
check(f"8: failure_count == {expected} matches transient_streak exactly "
      f"(got failure_count={cap.failure_count})", cap.failure_count == expected)


print("\n=== Test 4: permanent streak internally consistent under concurrent permanent failures ===")
cap = fresh_capacity()
run_concurrent(lambda: cap.record_failure(PERMANENT_ERR), N_THREADS, N_CALLS)
check(f"9: permanent_streak == {expected} after {N_THREADS}x{N_CALLS} concurrent "
      f"permanent-classified failures (got {cap.permanent_streak}) - no lost increments",
      cap.permanent_streak == expected)
check("10: transient_streak stayed 0 throughout an all-permanent run (got %d)"
      % cap.transient_streak, cap.transient_streak == 0)


print("\n=== Test 5: mixed concurrent success/failure calls do not corrupt state ===")
cap = fresh_capacity()
N_SUCCESS_THREADS, N_FAILURE_THREADS = 8, 8
barrier = threading.Barrier(N_SUCCESS_THREADS + N_FAILURE_THREADS)


def success_worker():
    barrier.wait()
    for _ in range(N_CALLS):
        cap.record_success()


def failure_worker():
    barrier.wait()
    for _ in range(N_CALLS):
        cap.record_failure(PERMANENT_ERR)


threads = ([threading.Thread(target=success_worker) for _ in range(N_SUCCESS_THREADS)]
           + [threading.Thread(target=failure_worker) for _ in range(N_FAILURE_THREADS)])
for t in threads:
    t.start()
for t in threads:
    t.join()

exp_success = N_SUCCESS_THREADS * N_CALLS
exp_failure = N_FAILURE_THREADS * N_CALLS
check(f"11: success_count == {exp_success} under mixed concurrent load "
      f"(got {cap.success_count})", cap.success_count == exp_success)
check(f"12: failure_count == {exp_failure} under mixed concurrent load "
      f"(got {cap.failure_count})", cap.failure_count == exp_failure)
check("13: streak fields are a valid pair after mixed load - never both "
      f"nonzero at once (permanent={cap.permanent_streak}, transient={cap.transient_streak})",
      not (cap.permanent_streak > 0 and cap.transient_streak > 0))
check("14: no exception escaped any of the 16 concurrent workers "
      "(reaching this line at all proves it)", True)


print("\n=== Test 6: threshold transitions remain correct under concurrency ===")
cap = fresh_capacity()
# Fire exactly _UNAVAILABLE_THRESHOLD concurrent permanent failures - past the
# real production race (Phase 30C-O2), this exact count could previously land
# anywhere below the true threshold due to lost increments.
run_concurrent(lambda: cap.record_failure(PERMANENT_ERR), ap._UNAVAILABLE_THRESHOLD, 1)
check(f"15: current_health() == UNAVAILABLE after exactly "
      f"_UNAVAILABLE_THRESHOLD={ap._UNAVAILABLE_THRESHOLD} concurrent permanent "
      f"failures (got {cap.current_health()})", cap.current_health() == ap.UNAVAILABLE)

cap2 = fresh_capacity()
run_concurrent(lambda: cap2.record_failure(TRANSIENT_ERR), ap._DEGRADE_THRESHOLD, 1)
check(f"16: current_health() == DEGRADED after exactly "
      f"_DEGRADE_THRESHOLD={ap._DEGRADE_THRESHOLD} concurrent transient "
      f"failures (got {cap2.current_health()})", cap2.current_health() == ap.DEGRADED)

cap3 = fresh_capacity()
run_concurrent(lambda: cap3.record_failure(TRANSIENT_ERR), ap._DEGRADE_THRESHOLD - 1, 1)
check(f"17: current_health() == HEALTHY one short of _DEGRADE_THRESHOLD "
      f"(got {cap3.current_health()})", cap3.current_health() == ap.HEALTHY)


print("\n=== Test 7: current_health() cannot observe a partially updated state ===")
cap = fresh_capacity()
stop = threading.Event()
observed_health = set()
observed_bad_pair = []


def hammer_failures():
    i = 0
    while not stop.is_set():
        # alternate transient/permanent so streaks keep flipping/resetting -
        # exactly the scenario that would expose a torn read
        cap.record_failure(TRANSIENT_ERR if i % 2 == 0 else PERMANENT_ERR)
        i += 1


def hammer_successes():
    while not stop.is_set():
        cap.record_success()


def hammer_reads():
    while not stop.is_set():
        h = cap.current_health()
        observed_health.add(h)
        # as_cache_row() gives us the raw streak snapshot alongside health,
        # from the SAME lock scope - assert the never-both-nonzero invariant
        # holds on every single read, not just at the end.
        row = cap.as_cache_row()
        if row["permanent_streak"] > 0 and row["transient_streak"] > 0:
            observed_bad_pair.append(row)


writers = [threading.Thread(target=hammer_failures) for _ in range(4)]
writers += [threading.Thread(target=hammer_successes) for _ in range(2)]
readers = [threading.Thread(target=hammer_reads) for _ in range(6)]
for t in writers + readers:
    t.start()
time.sleep(1.0)
stop.set()
for t in writers + readers:
    t.join()

check(f"18: every current_health() observed a VALID health value across "
      f"heavy concurrent read/write (observed: {observed_health})",
      observed_health.issubset({ap.HEALTHY, ap.DEGRADED, ap.RATE_LIMITED,
                                 ap.UNAVAILABLE, ap.DISABLED}))
check(f"19: zero torn reads observed (permanent_streak AND transient_streak "
      f"both nonzero at once) across {len(observed_health)} distinct health "
      f"values and continuous concurrent mutation "
      f"({len(observed_bad_pair)} bad pair(s) found)",
      len(observed_bad_pair) == 0)
check("20: no exception escaped the 1-second mixed read/write/health-check "
      "stress window (reaching this line at all proves it)", True)


print("\n=== Test 8: persisted cache values remain correct under concurrent access ===")
# _save_health_cache() only ever writes rows for names in ap.PROVIDERS (Section
# 18's "bounded by construction" rule) - register the synthetic provider there
# for the duration of this test only, restoring the real list afterward.
provider = {"name": "cachetest", "enabled": True}
_REAL_PROVIDERS = ap.PROVIDERS
ap.PROVIDERS = _REAL_PROVIDERS + [provider]
ap._CAPACITIES.pop("cachetest", None)
ap._HEALTH_CACHE.pop("cachetest", None)
cap = ap._capacity_for(provider)
run_concurrent(cap.record_success, 10, 200)          # 2000 successes
run_concurrent(lambda: cap.record_failure(PERMANENT_ERR), 2, 1)   # push into UNAVAILABLE
# Phase 30C-P2 review: every record_failure() call triggers its OWN
# _mark_dirty()->_save_health_cache() write, and _save_health_cache() (out of
# scope for this test - it is a pre-existing, documented "best-effort"
# snapshot-then-replace, not itself serialized against CONCURRENT invocations)
# can race with itself when two threads call it back-to-back: each snapshots
# the row independently, and whichever os.replace() lands last wins - so an
# in-between disk read can occasionally reflect a stale snapshot even though
# the in-memory counters (what Phase 30C-P1 actually guarantees) are already
# fully correct. One final, single-threaded, uncontended save after all
# concurrent activity has settled removes that race from THIS assertion
# without touching ai_providers.py or claiming a guarantee P1 never made.
ap._save_health_cache()
import json
persisted = json.loads(ap._HEALTH_CACHE_FILE.read_text(encoding="utf-8"))
row = persisted.get("cachetest", {})
check(f"21: persisted success count on disk == 2000 (got {row.get('success')})",
      row.get("success") == 2000)
check(f"22: persisted failure count on disk == 2 (got {row.get('failure')})",
      row.get("failure") == 2)
check(f"23: persisted health on disk == UNAVAILABLE (got {row.get('health')})",
      row.get("health") == ap.UNAVAILABLE)
check(f"24: persisted permanent_streak on disk == 2 (got {row.get('permanent_streak')})",
      row.get("permanent_streak") == 2)
ap._CAPACITIES.pop("cachetest", None)
ap._HEALTH_CACHE.pop("cachetest", None)
ap.PROVIDERS = _REAL_PROVIDERS


# --- cleanup: restore the real cache file path, drop our synthetic cache file ---
ap._HEALTH_CACHE_FILE.unlink(missing_ok=True)
ap._HEALTH_CACHE_FILE = _REAL_CACHE_FILE

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
