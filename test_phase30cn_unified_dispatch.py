"""
test_phase30cn_unified_dispatch.py - Phase 30C-N: regression tests for the
unified multi-provider dispatcher (_FixedBudgetLane, _dispatch_unified(),
_run_summaries()'s dispatch_fn extension). All provider calls are mocked via
a monkeypatched analyze.analyze_event() - no real Groq/Gemini/Ollama/Cerebras
call is ever made. hybrid/pool/gemini/ollama backends are never exercised by
this file and are proven untouched by the existing suites instead.

Run:  py test_phase30cn_unified_dispatch.py
"""
import threading
import time

import analyze

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def rows_for(i):
    return [{"_id": i, "source": "Test Outlet", "language": "en", "title": f"synthetic {i}",
             "summary": "synthetic", "url": "https://example.invalid", "image_url": ""}]


def llm_result(backend):
    return {"summary_method": "llm", "summary": "ok", "title": "ok", "backend_used": backend}


def extractive_result():
    return {"summary_method": "extractive", "summary": "fallback", "title": "fallback"}


print("=== Test 1: _FixedBudgetLane - assignment budget ===")
# max_concurrent=8 here so the concurrency dimension can never interfere -
# this test isolates the BUDGET dimension specifically (Test 2 below isolates
# concurrency on its own). Release immediately after each acquire, simulating
# sequential one-at-a-time processing.
lane = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=8)
acquired = []
for _ in range(8):
    ok = lane.try_acquire()
    acquired.append(ok)
    if ok:
        lane.release()
check("1: exactly 8 acquires succeed when budget=8", all(acquired) and len(acquired) == 8)
ninth = lane.try_acquire()
check("2: the 9th acquire fails once budget is exhausted", ninth is False)

print("\n=== Test 2: _FixedBudgetLane - concurrency cap (independent of budget) ===")
lane2 = analyze._FixedBudgetLane(max_assignments=1000, max_concurrent=1)
check("3: first acquire succeeds", lane2.try_acquire() is True)
check("4: a second acquire fails while the first is still held (concurrency=1)",
      lane2.try_acquire() is False)
lane2.release()
check("5: after release, acquire succeeds again", lane2.try_acquire() is True)
lane2.release()

print("\n=== Test 3: budget decrements on ACQUIRE, not on success (conservative) ===")
lane3 = analyze._FixedBudgetLane(max_assignments=3, max_concurrent=3)
lane3.try_acquire(); lane3.try_acquire(); lane3.try_acquire()
check("6: budget is exhausted after 3 acquires even with none released/failed",
      lane3.try_acquire() is False)

print("\n=== Test 4: _dispatch_unified() - Ollama success means pool is NEVER called ===")
calls = []
orig_analyze_event = analyze.analyze_event
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)


def mock_always_ollama_ok(rows, backend=None):
    calls.append(backend)
    if backend == "ollama":
        return llm_result("ollama")
    raise AssertionError("pool should not have been called - Ollama already succeeded")


analyze.analyze_event = mock_always_ollama_ok
result = analyze._dispatch_unified(rows_for(0))
check("7: dispatch returns the Ollama result directly", result["backend_used"] == "ollama")
check("8: pool was never attempted", calls == ["ollama"])

print("\n=== Test 5: _dispatch_unified() - Ollama failure -> exactly ONE pool retry ===")
calls.clear()
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)


def mock_ollama_fails_pool_ok(rows, backend=None):
    calls.append(backend)
    if backend == "ollama":
        return extractive_result()   # Ollama's own internal fallback already fired
    return llm_result("pool")


analyze.analyze_event = mock_ollama_fails_pool_ok
result = analyze._dispatch_unified(rows_for(0))
check("9: dispatch falls through to the pool and returns its result",
      result["backend_used"] == "pool")
check("10: exactly one Ollama attempt + one pool attempt - no third call",
      calls == ["ollama", "pool"])

print("\n=== Test 6: Ollama budget exhaustion -> subsequent events skip Ollama entirely ===")
calls.clear()
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=2, max_concurrent=1)


def mock_track_backend(rows, backend=None):
    calls.append(backend)
    return llm_result(backend)


analyze.analyze_event = mock_track_backend
for i in range(5):
    analyze._dispatch_unified(rows_for(i))
check("11: only the first 2 events (the budget) were offered to Ollama at all "
      f"(observed: {calls})", calls.count("ollama") == 2)
check("12: the remaining 3 events went straight to the pool, never attempting "
      "a now-exhausted Ollama", calls.count("pool") == 3)

print("\n=== Test 7: global concurrency ceiling (LLM_CONCURRENCY=8) is never exceeded ===")
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)
active = {"n": 0}
max_seen = {"n": 0}
ollama_active = {"n": 0}
ollama_max_seen = {"n": 0}
lock = threading.Lock()


def mock_concurrency_tracking(rows, backend=None):
    with lock:
        active["n"] += 1
        max_seen["n"] = max(max_seen["n"], active["n"])
        if backend == "ollama":
            ollama_active["n"] += 1
            ollama_max_seen["n"] = max(ollama_max_seen["n"], ollama_active["n"])
    time.sleep(0.05)   # small, deliberate overlap window
    with lock:
        active["n"] -= 1
        if backend == "ollama":
            ollama_active["n"] -= 1
    return llm_result(backend)


analyze.analyze_event = mock_concurrency_tracking
results = analyze._run_summaries([rows_for(i) for i in range(30)], 8, dispatch_fn=analyze._dispatch_unified)
check(f"13: global concurrent active calls never exceeded LLM_CONCURRENCY=8 "
      f"(observed max: {max_seen['n']})", max_seen["n"] <= 8)
check(f"14: Ollama's own concurrency never exceeded 1 (observed max: {ollama_max_seen['n']})",
      ollama_max_seen["n"] <= 1)
check("15: all 30 events produced a result, in order, none lost",
      len(results) == 30 and all(r["summary_method"] == "llm" for r in results))
ollama_calls_this_run = sum(1 for r in results if r["backend_used"] == "ollama")
check(f"16: Ollama handled AT MOST 8 of the 30 events (observed: {ollama_calls_this_run})",
      ollama_calls_this_run <= 8)

print("\n=== Failure Scenarios (A-H) ===")

# Scenario A: all providers healthy
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)
analyze.analyze_event = lambda rows, backend=None: llm_result(backend)
resA = analyze._run_summaries([rows_for(i) for i in range(10)], 8, dispatch_fn=analyze._dispatch_unified)
check("17 (Scenario A, all healthy): 10/10 events succeed as llm, 0 extractive",
      all(r["summary_method"] == "llm" for r in resA))

# Scenario B/C: pool (Groq/Gemini) unavailable, Ollama healthy
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)


def mock_pool_down(rows, backend=None):
    if backend == "ollama":
        return llm_result("ollama")
    return extractive_result()   # simulates pool's own internal Groq+Gemini exhaustion


analyze.analyze_event = mock_pool_down
resBC = analyze._run_summaries([rows_for(i) for i in range(10)], 8, dispatch_fn=analyze._dispatch_unified)
n_llm_bc = sum(1 for r in resBC if r["summary_method"] == "llm")
check(f"18 (Scenario B/C, pool down): exactly the Ollama-budget's worth (8) "
      f"succeed as llm, the rest extractive - no crash (observed llm: {n_llm_bc})",
      n_llm_bc == 8 and len(resBC) == 10)

# Scenario D: Ollama fixed budget exhausted mid-run (same mechanism as Test 6, at scale)
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)
ollama_attempts = {"n": 0}


def mock_count_ollama(rows, backend=None):
    if backend == "ollama":
        ollama_attempts["n"] += 1
        return llm_result("ollama")
    return llm_result("pool")


analyze.analyze_event = mock_count_ollama
resD = analyze._run_summaries([rows_for(i) for i in range(25)], 8, dispatch_fn=analyze._dispatch_unified)
check(f"19 (Scenario D, budget exhaustion at scale): Ollama attempted at most 8 "
      f"times across 25 events (observed: {ollama_attempts['n']})", ollama_attempts["n"] <= 8)
check("20: all 25 events still resolved successfully via the pool overflow",
      all(r["summary_method"] == "llm" for r in resD))

# Scenario E: Ollama unavailable entirely, pool healthy
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)


def mock_ollama_down(rows, backend=None):
    if backend == "ollama":
        return extractive_result()
    return llm_result("pool")


analyze.analyze_event = mock_ollama_down
resE = analyze._run_summaries([rows_for(i) for i in range(10)], 8, dispatch_fn=analyze._dispatch_unified)
check("21 (Scenario E, Ollama down): every event still succeeds via the bounded "
      "pool fallback - no crash, no starvation", all(r["summary_method"] == "llm" for r in resE))

# Scenario F: Groq+Gemini AND Ollama unavailable for events beyond the budget
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)


def mock_only_ollama_budget_works(rows, backend=None):
    if backend == "ollama":
        return llm_result("ollama")
    return extractive_result()


analyze.analyze_event = mock_only_ollama_budget_works
resF = analyze._run_summaries([rows_for(i) for i in range(15)], 8, dispatch_fn=analyze._dispatch_unified)
n_llm_f = sum(1 for r in resF if r["summary_method"] == "llm")
n_ext_f = sum(1 for r in resF if r["summary_method"] == "extractive")
check(f"22 (Scenario F): exactly 8 succeed (Ollama budget), 7 extractive - no crash "
      f"(llm={n_llm_f}, extractive={n_ext_f})", n_llm_f == 8 and n_ext_f == 7)

# Scenario G: all providers unavailable -> extractive fallback only, no crash
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=8, max_concurrent=1)
analyze.analyze_event = lambda rows, backend=None: extractive_result()
resG = analyze._run_summaries([rows_for(i) for i in range(10)], 8, dispatch_fn=analyze._dispatch_unified)
check("23 (Scenario G, all unavailable): all 10 events resolve to extractive, "
      "zero exceptions escape", all(r["summary_method"] == "extractive" for r in resG)
      and len(resG) == 10)

# Scenario H: a provider recovers mid-run (pool fails for the first half, succeeds after)
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=0, max_concurrent=1)  # force straight to pool
state = {"n": 0}
state_lock = threading.Lock()


def mock_recovery(rows, backend=None):
    with state_lock:
        state["n"] += 1
        n = state["n"]
    if n <= 5:
        return extractive_result()
    return llm_result("pool")


analyze.analyze_event = mock_recovery
resH = analyze._run_summaries([rows_for(i) for i in range(10)], 1, dispatch_fn=analyze._dispatch_unified)
check("24 (Scenario H, recovery mid-run): later events succeed once the "
      "simulated provider recovers - dispatch makes a fresh decision every "
      "time, nothing is cached/locked in from earlier failures",
      any(r["summary_method"] == "llm" for r in resH[5:]))

# restore real analyze_event and a fresh module-level lane
analyze.analyze_event = orig_analyze_event
analyze._OLLAMA_LANE = analyze._FixedBudgetLane(max_assignments=analyze.LLM_LOCAL_BUDGET,
                                                 max_concurrent=analyze.OLLAMA_MAX_CONCURRENT)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
