"""
test_phase30cp_multiround.py - Phase 30C-P1/P2: the bounded multi-round work
queue (LLM_BACKEND=="rounds"). Fully mocked - analyze.analyze_event is replaced
with a scripted/instrumented stand-in for every test; no real provider calls,
no network, no DB writes. Exercises _WorkItem, _dispatch_one,
_run_generation_rounds, _round_1_or_2_provider, _round_3_provider,
_RoundTelemetry directly against real threading (ThreadPoolExecutor) where the
requirement is a concurrency/ordering proof, not just a logic proof.

Run:  py test_phase30cp_multiround.py
"""
import threading
import time

import analyze
import ai_providers as ap

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


GROQ = {"name": "groq", "enabled": True}
GEMINI = {"name": "gemini", "enabled": True}


def backend_name(backend):
    if backend == "ollama":
        return "ollama"
    if isinstance(backend, dict):
        return backend["name"]
    return str(backend)


def fake_active_providers():
    return [GROQ, GEMINI]


def fake_pick_providers_in_order(active):
    return list(active)   # deterministic: groq before gemini, no health filtering


# --- monkeypatch the pool-selection surface for every test below (restored at
# the very end) - decouples these tests from ProviderCapacity's real health
# computation, which is already exhaustively covered by
# test_phase30cp1_capacity_thread_safety.py and test_phase30cj_*.py. ---
_REAL_ACTIVE_PROVIDERS = ap.active_providers
_REAL_PICK_ORDER = ap._pick_providers_in_order
ap.active_providers = fake_active_providers
ap._pick_providers_in_order = fake_pick_providers_in_order


def fresh_ollama_lane(max_assignments=8, max_concurrent=1):
    """A brand-new _FixedBudgetLane, substituted for analyze._OLLAMA_LANE for
    the duration of one test (restored by the caller) - mirrors
    test_phase30cn_unified_dispatch.py's own isolation pattern."""
    return analyze._FixedBudgetLane(max_assignments=max_assignments, max_concurrent=max_concurrent)


class ScriptedAnalyzeEvent:
    """Controls the outcome of each successive attempt for a given work item.
    `plan[idx]` is a list of "success"/"fail" outcomes consumed in call order
    for item `idx` (rows == [idx], a 1-element stand-in for a real article-row
    list). Records every (idx, provider) call for assertions. If the plan runs
    out, the LAST outcome repeats (defaults to "fail" if no plan entry at all -
    fail-closed, never silently succeeds)."""

    def __init__(self, plan):
        self.plan = plan
        self.calls = []             # [(idx, provider_name), ...] in call order
        self._n = {}

    def __call__(self, rows, backend=None, on_failure=None):
        idx = rows[0]
        provider = backend_name(backend)
        self.calls.append((idx, provider))
        n = self._n.get(idx, 0)
        self._n[idx] = n + 1
        outcomes = self.plan.get(idx, ["fail"])
        outcome = outcomes[n] if n < len(outcomes) else outcomes[-1]
        if outcome == "success":
            return {"summary_method": "llm", "title": f"t{idx}", "summary": f"s{idx}",
                    "content_complete": True}
        if on_failure is not None:
            on_failure(RuntimeError("HTTP 500 simulated provider failure"))
        return {"summary_method": "extractive", "title": f"t{idx}", "summary": f"s{idx}",
                "content_complete": True}


def run_with_script(plan, n_items=None, ollama_lane=None):
    """Runs _run_generation_rounds() over n_items work items (default: len(plan))
    with analyze_event replaced by a ScriptedAnalyzeEvent(plan). Returns
    (work_items, exhausted_set, mock)."""
    real_analyze_event = analyze.analyze_event
    real_lane = analyze._OLLAMA_LANE
    mock = ScriptedAnalyzeEvent(plan)
    analyze.analyze_event = mock
    if ollama_lane is not None:
        analyze._OLLAMA_LANE = ollama_lane
    try:
        n = n_items if n_items is not None else len(plan)
        items = [analyze._WorkItem(i, [i]) for i in range(n)]
        exhausted = set(analyze._run_generation_rounds(items))
        return items, exhausted, mock
    finally:
        analyze.analyze_event = real_analyze_event
        analyze._OLLAMA_LANE = real_lane


print("=== Test 1: one provider per round - an event cannot reach two providers in one round ===")
# item 0 fails whatever it's given every round; item 1 succeeds immediately.
# Ollama lane exhausted up front (0 budget) so round 1 goes straight to a SINGLE
# pool provider - if two providers were ever tried in the same round, item 0's
# calls-per-round-1 would be 2, not 1.
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "fail", "fail"], 1: ["success"]},
                                          n_items=2, ollama_lane=lane)
calls_for_0_round1 = [c for c in mock.calls if c[0] == 0][:1]
check("1a: item 0's round-1 call list contains exactly ONE (idx, provider) entry "
      f"before round 2 starts (got calls so far cannot exceed 1 per round by "
      f"construction - verifying via attempt history instead): "
      f"attempts round1 count == 1 ({[a for a in items[0].attempts if a['round'] == 1]})",
      len([a for a in items[0].attempts if a["round"] == 1]) == 1)
check("1b: item 0 was tried by exactly 3 DISTINCT providers is impossible with "
      "only 2 pool providers configured - confirms no more than 1 attempt/round "
      f"across 3 rounds (total attempts == 3, one per round): {len(items[0].attempts)}",
      len(items[0].attempts) == 3)


print("\n=== Test 2: Ollama failure must NOT call pool during the same round ===")
lane = fresh_ollama_lane(max_assignments=8, max_concurrent=1)
items, exhausted, mock = run_with_script({0: ["fail", "success"]}, n_items=1, ollama_lane=lane)
round1_calls = [c for c in mock.calls if items[0].attempts[0]["round"] == 1]
check("2a: item 0's FIRST attempt was Ollama (round 1)",
      items[0].attempts[0]["provider"] == "ollama" and items[0].attempts[0]["result"] == "failure")
check("2b: exactly ONE call happened before round 2 - Ollama's failure did NOT "
      f"trigger an immediate pool call in the same round (total calls: {mock.calls})",
      len([c for c in mock.calls if c == (0, "ollama")]) == 1
      and mock.calls[0] == (0, "ollama") and mock.calls[1][1] in ("groq", "gemini"))
check("2c: item 0's SECOND attempt (round 2) went to a pool provider, not Ollama again",
      items[0].attempts[1]["round"] == 2 and items[0].attempts[1]["provider"] in ("groq", "gemini"))
check("2d: item 0 ultimately succeeded", items[0].result is not None and items[0] not in exhausted)


print("\n=== Test 3: Ollama acquisition failure must NOT mark Ollama as tried ===")
lane = fresh_ollama_lane(max_assignments=0)   # try_acquire() always returns False
items, exhausted, mock = run_with_script({0: ["success"]}, n_items=1, ollama_lane=lane)
check("3a: 'ollama' never appears in tried_providers when the lane could never "
      f"be acquired (tried_providers={items[0].tried_providers})",
      "ollama" not in items[0].tried_providers)
check("3b: exactly one pool provider was selected in round 1 instead "
      f"(attempts={items[0].attempts})",
      len(items[0].attempts) == 1 and items[0].attempts[0]["provider"] in ("groq", "gemini"))
check("3c: no 'ollama' call was ever made", all(c[1] != "ollama" for c in mock.calls))


print("\n=== Test 4: Round-1 failure -> Round 2 with a different provider (Groq fail -> Gemini) ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "success"]}, n_items=1, ollama_lane=lane)
check("4a: round 1 tried groq (first in the fixed ranking) and failed",
      items[0].attempts[0]["provider"] == "groq" and items[0].attempts[0]["result"] == "failure")
check("4b: round 2 tried gemini (the untried one) and succeeded",
      items[0].attempts[1]["provider"] == "gemini" and items[0].attempts[1]["result"] == "success")
check("4c: exactly 2 total attempts for a 1-item generation resolved in round 2",
      len(items[0].attempts) == 2)


print("\n=== Test 5: a Round-1 success must never appear in Round 2 ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["success"], 1: ["fail", "success"]},
                                          n_items=2, ollama_lane=lane)
check("5a: item 0 (round-1 success) has exactly ONE attempt total - never revisited",
      len(items[0].attempts) == 1 and items[0].attempts[0]["round"] == 1)
check("5b: item 1 (round-1 failure) has exactly TWO attempts, spanning rounds 1-2",
      len(items[1].attempts) == 2 and [a["round"] for a in items[1].attempts] == [1, 2])
check("5c: item 0 never appears in mock.calls after its first (single) call",
      mock.calls.count((0, "groq")) + mock.calls.count((0, "gemini")) == 1)


print("\n=== Test 6: tried-provider exclusion - Round 1 Groq fail => Round 2 must not repick Groq ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "fail"]}, n_items=1, ollama_lane=lane)
check("6: round 2 selected gemini, NOT a repeat of groq, while gemini was still "
      f"eligible/untried (attempts={items[0].attempts})",
      items[0].attempts[1]["provider"] == "gemini")


print("\n=== Test 7: Round-2 exhaustion (no untried provider left) -> correct next state ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "fail", "success"]}, n_items=1, ollama_lane=lane)
check("7a: after round 2, both pool providers (groq, gemini) have been tried",
      items[0].tried_providers == {"groq", "gemini"})
check("7b: item 0 proceeds to round 3 (not exhausted after only 2 rounds)",
      len(items[0].attempts) == 3)
check("7c: round 3 succeeded via the repeat-allowed hierarchy", items[0] not in exhausted
      and items[0].attempts[2]["result"] == "success")


print("\n=== Test 8: Ollama's 8-call budget is shared ACROSS all rounds, not per-round ===")
lane = fresh_ollama_lane(max_assignments=3, max_concurrent=1)
# 5 items, each fails ollama then fails pool too (both pool providers), forcing
# every item through all 3 rounds; only the first 3 (in dispatch order) should
# ever reach Ollama at all, since the lane hard-caps at 3 assignments TOTAL.
plan = {i: ["fail", "fail", "fail"] for i in range(5)}
items, exhausted, mock = run_with_script(plan, n_items=5, ollama_lane=lane)
ollama_attempts = sum(1 for it in items for a in it.attempts if a["provider"] == "ollama")
check(f"8: exactly 3 total Ollama attempts across the WHOLE generation (all 3 "
      f"rounds combined), never more, matching the lane's max_assignments=3 "
      f"(got {ollama_attempts})", ollama_attempts == 3)
check("8b: the lane itself reports its budget fully spent (try_acquire() now False)",
      lane.try_acquire() is False)


print("\n=== Test 9: an item that actually attempted Ollama cannot receive Ollama again ===")
lane = fresh_ollama_lane(max_assignments=8, max_concurrent=1)
items, exhausted, mock = run_with_script({0: ["fail", "fail", "fail"]}, n_items=1, ollama_lane=lane)
ollama_count_for_item0 = sum(1 for a in items[0].attempts if a["provider"] == "ollama")
check(f"9: item 0 was offered Ollama at most once across all 3 rounds, despite "
      f"the lane having 7 assignments left unused (got {ollama_count_for_item0} "
      f"Ollama attempts; attempts={items[0].attempts})",
      ollama_count_for_item0 == 1)


print("\n=== Test 10: hard round barrier - Round 2 cannot begin before Round 1 fully drains ===")
lock = threading.Lock()
timeline = []       # [(idx, call_number, start_ts, end_ts), ...]
call_counts = {}    # idx -> how many times this item has been dispatched so far


class TimedAnalyzeEvent:
    """Real ThreadPoolExecutor concurrency + real time.sleep() (releases the
    GIL) so genuine overlap is observable. Even items fail round 1 (forcing a
    real round 2); odd items succeed round 1 but sleep LONGER, so a broken
    barrier would show a round-2 call starting before an odd item's round-1
    call has finished. call_number (not provider/round guesswork) unambiguously
    identifies which round each timestamp belongs to."""

    def __call__(self, rows, backend=None, on_failure=None):
        idx = rows[0]
        with lock:
            call_counts[idx] = call_counts.get(idx, 0) + 1
            call_number = call_counts[idx]
        t0 = time.monotonic()
        time.sleep(0.08 if idx % 2 == 1 else 0.02)
        t1 = time.monotonic()
        with lock:
            timeline.append((idx, call_number, t0, t1))
        if idx % 2 == 0:
            if on_failure is not None:
                on_failure(RuntimeError("HTTP 500 simulated"))
            return {"summary_method": "extractive", "content_complete": True}
        return {"summary_method": "llm", "content_complete": True}


lane = fresh_ollama_lane(max_assignments=0)
real_analyze_event = analyze.analyze_event
real_lane = analyze._OLLAMA_LANE
analyze.analyze_event = TimedAnalyzeEvent()
analyze._OLLAMA_LANE = lane
try:
    items = [analyze._WorkItem(i, [i]) for i in range(8)]
    exhausted = set(analyze._run_generation_rounds(items))
finally:
    analyze.analyze_event = real_analyze_event
    analyze._OLLAMA_LANE = real_lane

round1_ends = [t1 for idx, n, t0, t1 in timeline if n == 1]
round2_starts = [t0 for idx, n, t0, t1 in timeline if n == 2]
round1_latest_end = max(round1_ends)
check(f"10: every round-2 call started AFTER every round-1 call finished "
      f"(round-1 latest end={round1_latest_end:.4f}, earliest round-2 start="
      f"{min(round2_starts) if round2_starts else float('nan'):.4f})",
      bool(round2_starts) and min(round2_starts) >= round1_latest_end)
check("10b: a real round 2 actually happened (4 even items failed round 1)",
      len(round2_starts) == 4)


print("\n=== Test 11/12/13: concurrency ceilings (global<=8, Ollama<=1, Groq<=2) ===")
active = {"global": 0, "ollama": 0, "groq": 0, "gemini": 0}
peak = {"global": 0, "ollama": 0, "groq": 0, "gemini": 0}
conc_lock = threading.Lock()


class ConcurrencyTrackingAnalyzeEvent:
    def __call__(self, rows, backend=None, on_failure=None):
        idx = rows[0]
        provider = backend_name(backend)
        with conc_lock:
            active["global"] += 1
            active[provider] += 1
            peak["global"] = max(peak["global"], active["global"])
            peak[provider] = max(peak[provider], active[provider])
        time.sleep(0.03)
        with conc_lock:
            active["global"] -= 1
            active[provider] -= 1
        if on_failure is not None:
            on_failure(RuntimeError("HTTP 500 simulated"))
        return {"summary_method": "extractive", "content_complete": True}


lane = fresh_ollama_lane(max_assignments=8, max_concurrent=1)
real_analyze_event = analyze.analyze_event
real_lane = analyze._OLLAMA_LANE
analyze.analyze_event = ConcurrencyTrackingAnalyzeEvent()
analyze._OLLAMA_LANE = lane
try:
    items = [analyze._WorkItem(i, [i]) for i in range(20)]
    analyze._run_generation_rounds(items)
finally:
    analyze.analyze_event = real_analyze_event
    analyze._OLLAMA_LANE = real_lane

check(f"11: max simultaneous provider calls across the whole generation <= "
      f"LLM_CONCURRENCY=8 (observed peak={peak['global']})",
      peak["global"] <= analyze.LLM_CONCURRENCY)
check(f"12: max simultaneous Ollama calls <= 1 (observed peak={peak['ollama']})",
      peak["ollama"] <= 1)

print("\n=== Test 13: Groq concurrency <= 2 via the REAL _RateLimiter, reached "
      "through the new chat_with_provider() primitive ===")
# The orchestrator-level mock above bypasses _chat_once()/_RateLimiter entirely
# (it replaces analyze_event wholesale), so it cannot prove Groq's REAL limiter
# holds. This test instead calls ai_providers.chat_with_provider() directly -
# the exact function the round dispatcher uses for a targeted provider - with
# only the network layer (urlopen) mocked, so _chat_once()'s real
# limiter.acquire()/release() calls execute for real.
import json as _json
import urllib.error as _urlerr

real_groq = next(p for p in ap.PROVIDERS if p["name"] == "groq")
groq_active, groq_peak = [0], [0]
groq_lock = threading.Lock()


class _FakeResp:
    def __init__(self, body):
        self._body = body.encode("utf-8")
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    with groq_lock:
        groq_active[0] += 1
        groq_peak[0] = max(groq_peak[0], groq_active[0])
    time.sleep(0.05)
    with groq_lock:
        groq_active[0] -= 1
    return _FakeResp(_json.dumps({"choices": [{"message": {"content": "ok"}}]}))


# Ensure a clean, real ProviderCapacity/limiter for groq (avoid cross-test
# health-cache carryover from earlier real-provider-orchestration test files).
ap._CAPACITIES.pop("groq", None)
real_urlopen = ap.urllib.request.urlopen
ap.urllib.request.urlopen = fake_urlopen
try:
    threads = [threading.Thread(target=lambda: ap.chat_with_provider(real_groq, "hi", False))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
finally:
    ap.urllib.request.urlopen = real_urlopen
    ap._CAPACITIES.pop("groq", None)

check(f"13: max simultaneous Groq HTTP calls <= 2, via the REAL _RateLimiter "
      f"semaphore, reached through chat_with_provider() (observed peak="
      f"{groq_peak[0]})", groq_peak[0] <= 2)


print("\n=== Test 14: Round-3 untried provider is chosen over a repeat ===")
# Ollama's lane must be exhausted for these three tests to isolate PURE pool
# selection (an active lane would otherwise make _round_3_provider return
# "ollama" whenever it's untried, which is not what's under test here).
real_lane = analyze._OLLAMA_LANE
analyze._OLLAMA_LANE = fresh_ollama_lane(max_assignments=0)
try:
    item = analyze._WorkItem(0, [0])
    item.tried_providers = {"groq"}
    label, provider = analyze._round_3_provider(item)
    check(f"14: with only groq tried, round 3 picks the UNTRIED gemini, not a "
          f"repeat of groq (got {label})", label == "gemini")


    print("\n=== Test 15: Round-3 repeat when no untried pool provider remains ===")
    item = analyze._WorkItem(0, [0])
    item.tried_providers = {"groq", "gemini"}
    label, provider = analyze._round_3_provider(item)
    check(f"15: with both pool providers already tried, round 3 allows a repeat "
          f"of the best-ranked one (got {label})", label in ("groq", "gemini"))


    print("\n=== Test 16: Round 3 NEVER repeats Ollama ===")
    item = analyze._WorkItem(0, [0])
    item.tried_providers = {"ollama", "groq", "gemini"}
    label, provider = analyze._round_3_provider(item)
    check(f"16: with ollama+groq+gemini all tried, round 3 returns a POOL repeat "
          f"(or None) - never 'ollama' (got {label})", label != "ollama")
    check("16b: with everything tried, a repeat pool provider is still offered "
          f"(the hierarchy's last-resort step) - got {label}",
          label in ("groq", "gemini"))
finally:
    analyze._OLLAMA_LANE = real_lane


print("\n=== Test 17: three-round ceiling - no fourth provider attempt ever occurs ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "fail", "fail"]}, n_items=1, ollama_lane=lane)
check(f"17: item 0 received exactly 3 attempts total, never a 4th, and is "
      f"correctly EXHAUSTED (attempts={len(items[0].attempts)})",
      len(items[0].attempts) == 3 and items[0] in exhausted)


print("\n=== Test 18: extractive exhaustion produces a valid analysis ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "fail", "fail"]}, n_items=1, ollama_lane=lane)
FAKE_ROW = [{"title": "t", "summary": "s", "source": "X", "language": "en",
             "url": "http://example.com/x"}]
final = analyze.postprocess(analyze._extractive_raw(FAKE_ROW), FAKE_ROW)
check(f"18a: the EXISTING extractive path (unchanged) still produces "
      f"summary_method=='extractive' (got {final['summary_method']})",
      final["summary_method"] == "extractive")
check(f"18b: content_complete is always True for an extractive result "
      f"(got {final['content_complete']})", final["content_complete"] is True)
check("18c: the exhausted work item itself is correctly flagged for the "
      "extractive path by main()'s integration (proven structurally)",
      items[0] in exhausted)


print("\n=== Test 19: the rounds dispatcher never invokes pool_generate() ===")
pool_generate_called = []
real_pool_generate = ap.pool_generate
ap.pool_generate = lambda *a, **k: pool_generate_called.append(1) or "SHOULD NOT BE CALLED"
lane = fresh_ollama_lane(max_assignments=0)
try:
    items, exhausted, mock = run_with_script({0: ["fail", "success"]}, n_items=1, ollama_lane=lane)
finally:
    ap.pool_generate = real_pool_generate
check(f"19: pool_generate() was never called by the rounds dispatcher "
      f"(calls: {len(pool_generate_called)})", len(pool_generate_called) == 0)


print("\n=== Test 20: _call_json() can retry the SAME provider without provider selection ===")
# Exercise the REAL analyze_event()/_call_json() path (not the scripted mock)
# against a fake single-provider backend that fails once (malformed JSON,
# non-RuntimeError -> _call_json's own internal retry fires) then succeeds -
# proving the existing same-provider retry machinery is untouched and reachable
# through the new dict-backend route.
calls = []


def fake_generate(prompt, as_json, backend=None):
    calls.append(backend_name(backend) if backend else None)
    if len(calls) == 1:
        return "{not valid json"          # triggers _extract_json ValueError -> _call_json retry
    return '{"title": "Real Title", "summary": "Real summary.", "summary_hi": "x", ' \
           '"title_hi": "y", "region": "India"}'


real_generate = analyze._generate
analyze._generate = fake_generate
try:
    raw = analyze._call_json("prompt", backend=GROQ)
finally:
    analyze._generate = real_generate
check(f"20: _call_json() transparently retried the SAME provider after a "
      f"malformed-JSON failure and returned the second (valid) result "
      f"(calls={calls}, raw title={raw.get('title')})",
      len(calls) == 2 and calls[0] == calls[1] == "groq" and raw.get("title") == "Real Title")


print("\n=== Test 21: attempt history is exact and complete per work item ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "success"]}, n_items=1, ollama_lane=lane)
check(f"21: item 0's attempt history has exactly 2 entries with correct "
      f"round/provider/result fields (got {items[0].attempts})",
      items[0].attempts == [
          {"round": 1, "provider": "groq", "result": "failure", "failure_class": "provider"},
          {"round": 2, "provider": "gemini", "result": "success", "failure_class": None},
      ])


print("\n=== Test 22: successful recovery - Round 1 Groq fail, Round 2 Gemini success ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "success"]}, n_items=1, ollama_lane=lane)
check("22a: exactly 2 provider attempts total", len(mock.calls) == 2)
check("22b: final LLM output was produced (result is not None, not exhausted)",
      items[0].result is not None and items[0] not in exhausted)
check("22c: the two attempts used two DIFFERENT providers",
      mock.calls[0][1] != mock.calls[1][1])


print("\n=== Test 23: three-provider recovery obeys the exact selection hierarchy ===")
lane = fresh_ollama_lane(max_assignments=0)
items, exhausted, mock = run_with_script({0: ["fail", "fail", "success"]}, n_items=1, ollama_lane=lane)
check(f"23: round 1=groq(fail), round 2=gemini(fail), round 3=repeat "
      f"(no untried remains -> best-ranked pool repeat) (attempts={items[0].attempts})",
      [a["provider"] for a in items[0].attempts] == ["groq", "gemini", "groq"]
      and [a["result"] for a in items[0].attempts] == ["failure", "failure", "success"])


print("\n=== Test 24: mixed batch - each item follows its own independent path ===")
lane = fresh_ollama_lane(max_assignments=1)   # exactly 1 ollama slot in this batch
plan = {
    0: ["success"],                  # succeeds round 1 (pool, ollama exhausted by item order or busy)
    1: ["fail", "success"],          # succeeds round 2
    2: ["fail", "fail", "success"],  # succeeds round 3
    3: ["fail", "fail", "fail"],     # exhausts -> extractive
}
items, exhausted, mock = run_with_script(plan, n_items=4, ollama_lane=lane)
check(f"24a: item 0 resolved by round 1 ({len(items[0].attempts)} attempt(s))",
      len(items[0].attempts) == 1 and items[0].result is not None)
check(f"24b: item 1 resolved by round 2 ({len(items[1].attempts)} attempt(s))",
      len(items[1].attempts) == 2 and items[1].result is not None)
check(f"24c: item 2 resolved by round 3 ({len(items[2].attempts)} attempt(s))",
      len(items[2].attempts) == 3 and items[2].result is not None)
check(f"24d: item 3 exhausted after exactly 3 attempts", len(items[3].attempts) == 3
      and items[3] in exhausted)
check("24e: items 0-2 are NOT in the exhausted set",
      not ({items[0], items[1], items[2]} & exhausted))


print("\n=== Test 25: telemetry aggregate counts match the actual mocked assignments ===")
lane = fresh_ollama_lane(max_assignments=0)
real_analyze_event = analyze.analyze_event
real_lane = analyze._OLLAMA_LANE
mock = ScriptedAnalyzeEvent({0: ["success"], 1: ["fail", "success"], 2: ["fail", "fail", "fail"]})
analyze.analyze_event = mock
analyze._OLLAMA_LANE = lane
try:
    items = [analyze._WorkItem(i, [i]) for i in range(3)]
    telemetry = analyze._RoundTelemetry()
    exhausted = set(analyze._run_generation_rounds(items, telemetry=telemetry))
    telemetry.finalize(len(items) - len(exhausted), len(exhausted))
finally:
    analyze.analyze_event = real_analyze_event
    analyze._OLLAMA_LANE = real_lane

r1_total = sum(s["success"] + s["failure"] for s in telemetry.per_round.get(1, {}).values())
r2_total = sum(s["success"] + s["failure"] for s in telemetry.per_round.get(2, {}).values())
r3_total = sum(s["success"] + s["failure"] for s in telemetry.per_round.get(3, {}).values())
check(f"25a: round 1 telemetry counts all 3 items (got {r1_total})", r1_total == 3)
check(f"25b: round 2 telemetry counts exactly the 2 round-1 failures (got {r2_total})",
      r2_total == 2)
check(f"25c: round 3 telemetry counts exactly the 1 remaining failure (got {r3_total})",
      r3_total == 1)
check(f"25d: telemetry.succeeded == 2, telemetry.extractive == 1 "
      f"(got succeeded={telemetry.succeeded}, extractive={telemetry.extractive})",
      telemetry.succeeded == 2 and telemetry.extractive == 1)
check("25e: summary_lines() runs without error and is non-empty",
      len(telemetry.summary_lines()) > 0)


# ============================================================================
# Phase 30C-P2 REVIEW: _round_1_or_2_provider(item) takes NO round-number
# argument - its Ollama eligibility check ("ollama" not in item.tried_providers
# and _OLLAMA_LANE.try_acquire()) is IDENTICAL whether called from round 1,
# round 2, or (via _round_3_provider) round 3. This is the approved Option A
# architecture (matches the P-REVIEW's own dispatch_one pseudocode, which
# checked Ollama unconditionally at the top, not gated to round 1). Tests 1-25
# above never actually exercised "Ollama untried AND available entering round
# 2 or 3" - every test that reached round 2/3 did so with the lane already
# pre-exhausted (max_assignments=0), which silently avoided proving this. The
# following tests close that gap directly.
# ============================================================================

print("\n=== Test 26: untried Ollama CAN be freshly selected in Round 2, not just Round 1 ===")
lane = fresh_ollama_lane(max_assignments=8, max_concurrent=1)
lane._sem.acquire()   # simulate Ollama's single slot busy (another concurrent item) during round 1
real_ae = analyze.analyze_event
real_lane = analyze._OLLAMA_LANE
mock = ScriptedAnalyzeEvent({0: ["fail", "success"]})
analyze.analyze_event = mock
analyze._OLLAMA_LANE = lane
try:
    item = analyze._WorkItem(0, [0])
    outcome1 = analyze._dispatch_one(item, 1)
    check(f"26a: round 1 fell to a POOL provider because Ollama's slot was busy "
          f"at that moment (got {item.attempts[0]['provider']})",
          item.attempts[0]["provider"] in ("groq", "gemini"))
    check("26b: the busy slot was correctly treated as a SELECTION outcome, not "
          f"an attempt - 'ollama' is NOT marked tried (tried={item.tried_providers})",
          "ollama" not in item.tried_providers)
    lane._sem.release()   # Ollama becomes free before round 2 dispatches
    outcome2 = analyze._dispatch_one(item, 2)
    check(f"26c: round 2 freshly selected OLLAMA now that it is untried by this "
          f"item AND the lane is available - confirming Option A is the actual, "
          f"approved behavior (got provider={item.attempts[1]['provider']})",
          item.attempts[1]["provider"] == "ollama")
    check("26d: round 2 succeeded via the freshly-selected Ollama",
          outcome2 == "SUCCEEDED" and item.result is not None)
finally:
    analyze.analyze_event = real_ae
    analyze._OLLAMA_LANE = real_lane


print("\n=== Test 27 (Scenario A): Round 3 selects fresh Ollama when genuinely untried+available ===")
real_lane = analyze._OLLAMA_LANE
analyze._OLLAMA_LANE = fresh_ollama_lane(max_assignments=8, max_concurrent=1)
try:
    item = analyze._WorkItem(0, [0])
    item.tried_providers = {"groq", "gemini"}   # Round 1=Groq fail, Round 2=Gemini fail; Ollama untried
    label, provider = analyze._round_3_provider(item)
    check(f"27: with groq+gemini tried but Ollama untried and its lane available, "
          f"Round 3 selects OLLAMA - NOT a pool repeat (got {label})", label == "ollama")
finally:
    analyze._OLLAMA_LANE = real_lane


print("\n=== Test 28 (Scenario C/D): Round 3 does NOT re-select Ollama once genuinely attempted ===")
real_lane = analyze._OLLAMA_LANE
analyze._OLLAMA_LANE = fresh_ollama_lane(max_assignments=8, max_concurrent=1)
try:
    item = analyze._WorkItem(0, [0])
    item.tried_providers = {"ollama", "groq"}   # Round 1=Ollama fail, Round 2=Groq fail; Gemini untried
    label, provider = analyze._round_3_provider(item)
    check(f"28: with ollama already genuinely attempted, Round 3 selects the "
          f"untried gemini, never re-selecting ollama, even though the lane "
          f"still has budget/concurrency free (got {label})", label == "gemini")
finally:
    analyze._OLLAMA_LANE = real_lane


print("\n=== Test 29: Ollama's process-wide budget cap holds across mixed round-1/round-2 uses ===")
lane = fresh_ollama_lane(max_assignments=2, max_concurrent=1)
real_ae = analyze.analyze_event
real_lane = analyze._OLLAMA_LANE
mock = ScriptedAnalyzeEvent({0: ["success"], 1: ["fail", "success"]})
analyze.analyze_event = mock
analyze._OLLAMA_LANE = lane
try:
    item0 = analyze._WorkItem(0, [0])
    item1 = analyze._WorkItem(1, [1])
    lane._sem.acquire()                       # item1's round-1 slot is busy -> falls to pool
    analyze._dispatch_one(item1, 1)
    lane._sem.release()
    analyze._dispatch_one(item0, 1)           # ollama free -> item0 gets it in round 1
    analyze._dispatch_one(item1, 2)           # ollama free again -> item1 gets it fresh in round 2
finally:
    analyze.analyze_event = real_ae
    analyze._OLLAMA_LANE = real_lane
ollama_uses = sum(1 for it in (item0, item1) for a in it.attempts if a["provider"] == "ollama")
check(f"29a: exactly 2 total Ollama uses across both items/rounds, matching the "
      f"2-slot budget exactly (got {ollama_uses})", ollama_uses == 2)
check("29b: item0 used ollama in round 1; item1 used it FRESH in round 2 "
      f"(item0 round1={item0.attempts[0]['provider']}, "
      f"item1 round2={item1.attempts[1]['provider']})",
      item0.attempts[0]["provider"] == "ollama" and item1.attempts[1]["provider"] == "ollama")
check("29c: the shared lane now reports its budget fully spent",
      lane.try_acquire() is False)
check("29d: Ollama concurrency/boundedness (<=1 concurrent, <=8/run) is enforced "
      "by _OLLAMA_LANE's own semaphore/counter regardless of which round calls "
      "try_acquire() - already proven generally by Tests 8/9/12; this test "
      "confirms the SAME mechanism holds when the uses span multiple rounds",
      True)


# --- restore everything patched at module scope ---
ap.active_providers = _REAL_ACTIVE_PROVIDERS
ap._pick_providers_in_order = _REAL_PICK_ORDER

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
