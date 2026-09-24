"""
test_phase30ce_groq_rate_limit.py - Phase 30C-E: regression tests for the
Groq-specific rate limiter in ai_providers.py (_RateLimiter, _limiter_for(),
_parse_retry_after(), and their wiring into _chat_once()/pool_generate()).

All network calls are mocked (monkeypatched urllib.request.urlopen) - this
suite never touches the real Groq/Gemini APIs and consumes zero quota. The
small real-Groq smoke test is a separate, explicitly bounded manual step
(see the Phase 30C-E report), not part of this file.

Run:  py test_phase30ce_groq_rate_limit.py
"""
import io
import json
import threading
import time
import urllib.error

import ai_providers as ap

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# ---------------------------------------------------------------- fixtures --
def fake_groq_provider(**overrides):
    p = {"name": "test-groq", "enabled": True, "base_url": "https://example.invalid/v1",
         "model": "test-model", "tpm_budget": 2000, "max_concurrent": 2}
    p.update(overrides)
    return p


def fake_unlimited_provider():
    return {"name": "test-unlimited", "enabled": True, "base_url": "https://example.invalid/v1",
            "model": "test-model"}


class _FakeHTTPResponse:
    def __init__(self, body):
        self._body = body.encode("utf-8")
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _ok_body(text="hello"):
    return json.dumps({"choices": [{"message": {"content": text}}]})


def make_429(headers=None, body="Rate limit reached. please try again in 50ms."):
    return urllib.error.HTTPError(
        "https://example.invalid", 429, "Too Many Requests",
        headers or {}, io.BytesIO(body.encode("utf-8")))


print("=== _parse_retry_after() ===")
check("1: header takes priority over body", ap._parse_retry_after({"Retry-After": "2"}, "try again in 999ms") == 2.0)
check("2: body ms hint parsed", ap._parse_retry_after({}, "please try again in 250ms.") == 0.25)
check("3: body seconds hint parsed", ap._parse_retry_after({}, "try again in 3s") == 3.0)
check("4: no hint -> None", ap._parse_retry_after({}, "generic error, no timing info") is None)
check("5: malformed header falls back to body", ap._parse_retry_after({"Retry-After": "not-a-number"}, "try again in 10ms") == 0.01)

print("\n=== _limiter_for() - opt-in per provider ===")
check("6: a provider with tpm_budget/max_concurrent gets a limiter",
      ap._limiter_for(fake_groq_provider()) is not None)
check("7: a provider with NEITHER key gets None (zero overhead, e.g. Gemini/Cerebras today)",
      ap._limiter_for(fake_unlimited_provider()) is None)
check("8: real PROVIDERS registry - only groq is configured for limiting",
      {p["name"] for p in ap.PROVIDERS if ap._limiter_for(p) is not None} == {"groq"})
check("9: Cerebras remains disabled in the real registry (untouched by this phase)",
      next(p for p in ap.PROVIDERS if p["name"] == "cerebras")["enabled"] is False)
check("10: Gemini's real provider entry is unmodified by this phase (no tpm_budget/max_concurrent)",
      "tpm_budget" not in next(p for p in ap.PROVIDERS if p["name"] == "gemini")
      and "max_concurrent" not in next(p for p in ap.PROVIDERS if p["name"] == "gemini"))

print("\n=== _RateLimiter: concurrency cap ===")
lim = ap._RateLimiter(max_concurrent=2, tpm_budget=1_000_000)  # budget irrelevant here
in_flight = []
max_seen = [0]
lock = threading.Lock()

def worker():
    lim.acquire(10)
    with lock:
        in_flight.append(1)
        max_seen[0] = max(max_seen[0], len(in_flight))
    time.sleep(0.15)
    with lock:
        in_flight.pop()
    lim.release()

threads = [threading.Thread(target=worker) for _ in range(6)]
for t in threads: t.start()
for t in threads: t.join()
check("11: never more than max_concurrent=2 requests in flight at once (observed max: "
      f"{max_seen[0]})", max_seen[0] <= 2)

print("\n=== _RateLimiter: token budget (sliding window) ===")
lim2 = ap._RateLimiter(max_concurrent=10, tpm_budget=100, window_s=0.4)
t0 = time.monotonic()
lim2.acquire(60)     # 60/100 used
check("12: first acquire under budget returns immediately", time.monotonic() - t0 < 0.1)
t1 = time.monotonic()
lim2.acquire(60)     # would be 120/100 -> must wait for the window to age out
waited = time.monotonic() - t1
check("13: a call that would exceed the TPM budget waits for the window to clear "
      f"(waited {waited:.2f}s, window=0.4s)", waited >= 0.3)
lim2.release(); lim2.release()

print("\n=== _RateLimiter: bounded wait / TimeoutError ===")
lim3 = ap._RateLimiter(max_concurrent=1, tpm_budget=1_000_000)
lim3.MAX_WAIT_S = 0.3
lim3.acquire(1)   # hold the only slot
timed_out = False
t0 = time.monotonic()
try:
    lim3.acquire(1)
except TimeoutError as e:
    timed_out = True
    check("14: TimeoutError message contains 'timeout' (so pool_generate's existing "
          "_TRANSIENT check classifies it correctly with NO change to pool_generate())",
          "timeout" in str(e))
dt = time.monotonic() - t0
check("15: a saturated limiter raises TimeoutError instead of blocking forever", timed_out)
check("16: the wait was bounded near MAX_WAIT_S, not instant and not unbounded "
      f"(waited {dt:.2f}s)", 0.25 <= dt <= 1.0)
lim3.release()

print("\n=== _RateLimiter: an observed 429's Retry-After becomes a SHARED cooldown ===")
lim4 = ap._RateLimiter(max_concurrent=5, tpm_budget=1_000_000)
lim4.acquire(1)
lim4.note_error(retry_after_s=0.3)     # simulates what _chat_once() does on a real 429
t0 = time.monotonic()
lim4.acquire(1)                        # a DIFFERENT "thread" should also honor the cooldown
waited2 = time.monotonic() - t0
check("17: a cooldown set by one caller's 429 is honored by the next acquire() too "
      f"(waited {waited2:.2f}s for a 0.3s cooldown)", waited2 >= 0.25)
lim4.release()

print("\n=== end-to-end via _chat_once() / pool_generate() (network mocked) ===")


def _patch_urlopen(monkeypatch_fn):
    """Simple manual monkeypatch (no pytest) - swap ap.urllib.request.urlopen,
    return a restore function."""
    orig = ap.urllib.request.urlopen
    ap.urllib.request.urlopen = monkeypatch_fn
    return orig


# --- Case: Groq succeeds -> pool returns its content, no unnecessary delay ---
call_log = []


def urlopen_groq_ok(req, timeout=None):
    call_log.append(req.full_url)
    return _FakeHTTPResponse(_ok_body("GROQ_OK"))


orig_providers = ap.PROVIDERS
orig_env = dict(__import__("os").environ)
import os as _os
_os.environ["TEST_GROQ_API_KEY"] = "gsk_test_only_not_real"
_os.environ["TEST_GEMINI_API_KEY"] = "test_only_not_real"

test_groq = {"name": "test_groq", "enabled": True, "base_url": "https://example.invalid/v1",
             "model": "test-model", "key_env": "TEST_GROQ_API_KEY",
             "tpm_budget": 6000, "max_concurrent": 2}
test_gemini = {"name": "test_gemini", "enabled": True, "base_url": "https://example.invalid/v1",
               "model": "test-model", "key_env": "TEST_GEMINI_API_KEY"}
ap.PROVIDERS = [test_groq, test_gemini]

orig_urlopen = _patch_urlopen(urlopen_groq_ok)
t0 = time.monotonic()
result = ap.pool_generate("hello", as_json=False)
dt = time.monotonic() - t0
check("18: a healthy Groq call succeeds through the real pool_generate() path", result == "GROQ_OK")
check("19: no artificial delay when under budget/concurrency "
      f"(elapsed {dt:.3f}s)", dt < 1.0)
ap.urllib.request.urlopen = orig_urlopen

# --- Case: Groq always 429s -> pool falls through to Gemini (fallback preserved) ---
calls = {"groq": 0, "gemini": 0}


def urlopen_groq_429_gemini_ok(req, timeout=None):
    # distinguish by which key is in the Authorization header (both providers
    # share the same fake base_url, so this is the only reliable signal)
    auth = req.get_header("Authorization") or ""
    if "gsk_test_only_not_real" in auth:
        calls["groq"] += 1
        raise make_429()
    calls["gemini"] += 1
    return _FakeHTTPResponse(_ok_body("GEMINI_OK"))


orig_urlopen = _patch_urlopen(urlopen_groq_429_gemini_ok)
ap._rr_i = 0   # deterministic: force this call to start at test_groq (index 0), not wherever
               # the round-robin cursor happened to land after earlier calls in this test file
result2 = ap.pool_generate("hello again", as_json=False)
check("20: Groq 429 correctly falls through to Gemini (pool fallback preserved)",
      result2 == "GEMINI_OK")
check("21: Groq was actually attempted before falling through", calls["groq"] >= 1)
ap.urllib.request.urlopen = orig_urlopen

# --- Case: thread safety under real concurrent pool_generate() calls ---
calls2 = {"groq": 0, "gemini": 0}
lock2 = threading.Lock()


def urlopen_concurrent(req, timeout=None):
    auth = req.get_header("Authorization") or req.headers.get("Authorization", "")
    with lock2:
        if "gsk_test_only_not_real" in auth:
            calls2["groq"] += 1
        else:
            calls2["gemini"] += 1
    if "gsk_test_only_not_real" in auth:
        raise make_429(body="try again in 5ms.")
    return _FakeHTTPResponse(_ok_body("GEMINI_OK"))


orig_urlopen = _patch_urlopen(urlopen_concurrent)
errors = []


def run_one():
    try:
        r = ap.pool_generate("concurrent test", as_json=False)
        if r != "GEMINI_OK":
            errors.append(f"unexpected result: {r!r}")
    except Exception as e:
        errors.append(str(e))


threads = [threading.Thread(target=run_one) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()
check("22: 10 concurrent pool_generate() calls under a saturated Groq all complete "
      f"without raising or corrupting state (errors: {errors[:3]})", not errors)
ap.urllib.request.urlopen = orig_urlopen

# --- 2026-09-25 LLM cost campaign incident recovery: max_billed_attempts must
# actually cap attempts against "billed": True providers, while leaving a FREE
# provider's own fallback completely unrestricted (the whole point of trying the
# free tier first must survive this). Reproduces the exact gap found in
# analyze.py's _call_json_cached(): retries=0 there only bounded _call_json's own
# loop, not pool_generate()'s internal cross-provider fanout.
#
# The proof needs TWO billed providers: with only one, a transient failure
# already limits it to exactly 1 attempt via the pre-existing "break to next
# provider" rule, which would make the budget look like it's working even if it
# were silently ignored. With two billed providers, only the BUDGET (not the
# transient-break rule) can explain the second one never being called at all. ---
test_gemini_a = {"name": "test_gemini_a", "enabled": True, "base_url": "https://example.invalid/v1",
                  "model": "test-model", "key_env": "TEST_GEMINI_API_KEY", "billed": True}
test_gemini_b = {"name": "test_gemini_b", "enabled": True, "base_url": "https://example.invalid/v1",
                  "model": "test-model", "key_env": "TEST_GEMINI_API_KEY", "billed": True}
calls3 = {"a": 0, "b": 0}


def urlopen_both_billed_fail(req, timeout=None):
    # both share the same fake key/base_url; distinguish by provider name is not
    # possible from the request alone, so count total calls instead.
    calls3["a" if calls3["a"] <= calls3["b"] else "b"] += 1
    raise urllib.error.HTTPError("https://example.invalid", 500, "Server Error", {},
                                  io.BytesIO(b"internal error"))


ap.PROVIDERS = [test_gemini_a, test_gemini_b]
orig_urlopen = _patch_urlopen(urlopen_both_billed_fail)
ap._rr_i = 0
total_calls_with_budget = {"n": 0}
_orig_chat_once = ap._chat_once
def _counting_chat_once(provider, prompt, as_json, timeout=120):
    total_calls_with_budget["n"] += 1
    return _orig_chat_once(provider, prompt, as_json, timeout)
ap._chat_once = _counting_chat_once
raised = False
try:
    ap.pool_generate("budget test", as_json=False, max_billed_attempts=1)
except ValueError:
    raised = True
ap._chat_once = _orig_chat_once
check("23: both billed providers failing still raises ValueError (unchanged exception type)", raised)
check(f"24: with max_billed_attempts=1, only ONE billed provider was ever attempted "
      f"(the second was SKIPPED entirely, not called) - got {total_calls_with_budget['n']} total call(s)",
      total_calls_with_budget["n"] == 1)

# Control: the SAME two-billed-provider setup with NO budget attempts BOTH -
# proves the skip above really is caused by the budget, not some other limit.
total_calls_no_budget = {"n": 0}
def _counting_chat_once2(provider, prompt, as_json, timeout=120):
    total_calls_no_budget["n"] += 1
    return _orig_chat_once(provider, prompt, as_json, timeout)
ap._chat_once = _counting_chat_once2
ap._rr_i = 0
try:
    ap.pool_generate("no budget control", as_json=False)   # max_billed_attempts=None (default)
except ValueError:
    pass
ap._chat_once = _orig_chat_once
check(f"25: the SAME setup with NO budget (default) attempts BOTH billed providers "
      f"- got {total_calls_no_budget['n']} total call(s) (control, proves 24 isn't accidental)",
      total_calls_no_budget["n"] == 2)
ap.urllib.request.urlopen = orig_urlopen
test_gemini_billed = test_gemini_a   # reused by the next case below

# Case B: with NO budget (default, None) the pre-existing behavior is unchanged -
# a non-transient failure on the billed provider CAN still be retried per
# retries_per_provider (proves this is an opt-in cap, not a silent behavior change
# for every existing caller that doesn't pass max_billed_attempts).
calls4 = {"gemini": 0}


def urlopen_gemini_only_fails_then_ok(req, timeout=None):
    # 401 (not one of the _TRANSIENT markers) so pool_generate's loop does NOT
    # break to "next provider" - it falls through to retries_per_provider's
    # own same-provider retry, which is exactly the pre-existing behavior this
    # case is proving stays intact when no budget is passed.
    calls4["gemini"] += 1
    if calls4["gemini"] == 1:
        raise urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {},
                                      io.BytesIO(b"bad key (simulated, not a real failure)"))
    return _FakeHTTPResponse(_ok_body("GEMINI_OK_2ND_TRY"))


ap.PROVIDERS = [test_gemini_billed]
orig_urlopen = _patch_urlopen(urlopen_gemini_only_fails_then_ok)
result3 = ap.pool_generate("no budget test", as_json=False)   # max_billed_attempts=None (default)
check("26: with NO budget passed (default None), unchanged pre-existing same-provider "
      "retry-on-transient-failure behavior still works", result3 == "GEMINI_OK_2ND_TRY")
ap.urllib.request.urlopen = orig_urlopen

# restore
ap.PROVIDERS = orig_providers
_os.environ.clear()
_os.environ.update(orig_env)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
