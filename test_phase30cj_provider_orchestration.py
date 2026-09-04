"""
test_phase30cj_provider_orchestration.py - Phase 30C-J: regression tests for
the ProviderCapacity health/selection layer built on top of the (unmodified)
Phase 30C-E _RateLimiter, plus the bounded local health cache.

All network calls are mocked - this suite never touches the real Groq/Gemini
APIs and consumes zero quota. Uses a throwaway cache file path so the real
.provider_health.json is never touched.

Run:  py test_phase30cj_provider_orchestration.py
"""
import io
import json
import os
import threading
import urllib.error
from pathlib import Path

import ai_providers as ap

# Redirect the health cache to a throwaway path for the ENTIRE suite, before
# any test runs a single record_success()/record_failure() (which can trigger
# a save) - the real .provider_health.json must never be touched by this file.
_TEST_CACHE_FILE = Path(ap._HERE) / "_phase30cj_test_cache.json"
_REAL_CACHE_FILE = ap._HEALTH_CACHE_FILE
ap._HEALTH_CACHE_FILE = _TEST_CACHE_FILE

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


class _FakeHTTPResponse:
    def __init__(self, body):
        self._body = body.encode("utf-8")
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _ok_body(text="ok"):
    return json.dumps({"choices": [{"message": {"content": text}}]})


def http_error(code, body="", reason="err"):
    return urllib.error.HTTPError("https://example.invalid", code, reason, {}, io.BytesIO(body.encode("utf-8")))


def prov(name, **kw):
    p = {"name": name, "enabled": True, "base_url": "https://example.invalid/v1",
         "model": "test-model", "key_env": f"{name.upper()}_KEY"}
    p.update(kw)
    os.environ[p["key_env"]] = "test-not-a-real-key"
    return p


def reset_state(providers):
    """Fresh ProviderCapacity/limiter/round-robin state for each test block,
    isolated from whatever earlier tests in this file did."""
    ap.PROVIDERS = providers
    ap._CAPACITIES = {}
    ap._LIMITERS = {}
    ap._rr_i = 0
    ap._dirty_providers = set()
    ap._HEALTH_CACHE = {}


print("=== Test 1: provider health transitions ===")
p = prov("t1")
reset_state([p])
cap = ap._capacity_for(p)
check("1a: starts HEALTHY", cap.current_health() == ap.HEALTHY)
for _ in range(ap._DEGRADE_THRESHOLD):
    cap.record_failure("HTTP 503 service unavailable")
check("1b: HEALTHY -> DEGRADED after consecutive transient (5xx) failures",
      cap.current_health() == ap.DEGRADED)
cap.record_success()
check("1c: DEGRADED -> HEALTHY on a single success (no permanent poisoning "
      "from a transient run)", cap.current_health() == ap.HEALTHY)

p2 = prov("t1b")
reset_state([p2])
cap2 = ap._capacity_for(p2)
for _ in range(ap._UNAVAILABLE_THRESHOLD):
    cap2.record_failure("HTTP 403 PERMISSION_DENIED")
check("1d: HEALTHY -> UNAVAILABLE after consecutive non-transient (403) failures",
      cap2.current_health() == ap.UNAVAILABLE)
cap2.record_success()
check("1e: UNAVAILABLE -> HEALTHY immediately on a successful recovery call",
      cap2.current_health() == ap.HEALTHY)

print("\n=== Test 2: 429 cooldown uses the EXISTING limiter, not a duplicate ===")
p3 = prov("t2", tpm_budget=1000, max_concurrent=2)
reset_state([p3])
cap3 = ap._capacity_for(p3)
check("2a: starts eligible", cap3.eligible_for_dispatch())
cap3.limiter.note_error(retry_after_s=0.4)
check("2b: after an observed 429 cooldown, health reads RATE_LIMITED "
      "(derived live from _RateLimiter.in_cooldown(), no second cooldown system)",
      cap3.current_health() == ap.RATE_LIMITED)
check("2c: RATE_LIMITED does NOT hard-exclude - still eligible_for_dispatch() "
      "(the limiter's own bounded acquire()/cooldown still gets to decide)",
      cap3.eligible_for_dispatch() is True)
import time as _time
_time.sleep(0.45)
check("2d: once the SAME cooldown clears, health reads HEALTHY again with "
      "zero extra transition logic", cap3.current_health() == ap.HEALTHY)

print("\n=== Test 3: mixed provider selection - healthy/degraded/unavailable/rate-limited/disabled ===")
A = prov("A")
B = prov("B")
C = prov("C")
D = prov("D", tpm_budget=1000, max_concurrent=2)
E = prov("E", enabled=False)
reset_state([A, B, C, D, E])
capB = ap._capacity_for(B)
for _ in range(ap._DEGRADE_THRESHOLD):
    capB.record_failure("HTTP 500")
capC = ap._capacity_for(C)
for _ in range(ap._UNAVAILABLE_THRESHOLD):
    capC.record_failure("HTTP 403")
capD = ap._capacity_for(D)
capD.limiter.note_error(retry_after_s=30)
check("3a: A is HEALTHY, B is DEGRADED, C is UNAVAILABLE, D is RATE_LIMITED, E is DISABLED",
      ap._capacity_for(A).current_health() == ap.HEALTHY and
      capB.current_health() == ap.DEGRADED and
      capC.current_health() == ap.UNAVAILABLE and
      capD.current_health() == ap.RATE_LIMITED and
      ap._capacity_for(E).current_health() == ap.DISABLED)
ordered = ap._pick_providers_in_order(ap.active_providers())
names = [p["name"] for p in ordered]
check("3b: selection PREFERS A (healthy, no threshold breaches)", names[0] == "A")
check("3c: C (unavailable) is NEVER selected", "C" not in names)
check("3d: E (disabled) is NEVER selected", "E" not in names)
check("3e: D (rate-limited) is still present in the candidate list (not hard-excluded) "
      f"but ranked after healthy/degraded: {names}", "D" in names and names.index("D") > names.index("A"))
check("3f: B (degraded) is present, ranked after A", "B" in names and names.index("B") > names.index("A"))

print("\n=== Test 4: capacity-aware selection prefers greater safe headroom ===")
F = prov("F", tpm_budget=1000, max_concurrent=4)
G = prov("G", tpm_budget=1000, max_concurrent=4)
reset_state([F, G])
capF = ap._capacity_for(F)
capG = ap._capacity_for(G)
capF.limiter.acquire(950)   # F now has almost no headroom left
ordered4 = ap._pick_providers_in_order(ap.active_providers())
names4 = [p["name"] for p in ordered4]
check("4: the provider with meaningfully more safe headroom (G) is preferred "
      f"over the nearly-exhausted one (F): {names4}", names4[0] == "G")
capF.limiter.release()

print("\n=== Test 5: mid-run degradation shifts subsequent selections away ===")
H = prov("H")
I_ = prov("I")
reset_state([H, I_])
o1 = [p["name"] for p in ap._pick_providers_in_order(ap.active_providers())]
check("5a: both healthy initially - H and I are both present", set(o1) == {"H", "I"})
capH = ap._capacity_for(H)
for _ in range(ap._UNAVAILABLE_THRESHOLD):
    capH.record_failure("HTTP 401 invalid api key")
o2 = [p["name"] for p in ap._pick_providers_in_order(ap.active_providers())]
check("5b: after H fails repeatedly (permanent-looking), subsequent selection "
      f"excludes H entirely: {o2}", o2 == ["I"])

print("\n=== Test 6: recovery via the conservative one-trial rejoin ===")
J = prov("J")
reset_state([J])
capJ = ap._capacity_for(J)
capJ.load_persisted({"health": ap.UNAVAILABLE, "success": 3, "failure": 5})
check("6a: a provider loaded from a cache row marking it UNAVAILABLE is NOT "
      "hard-excluded this run - it's eligible for one trial",
      capJ.eligible_for_dispatch() is True and capJ.current_health() != ap.UNAVAILABLE)
capJ.record_failure("HTTP 403 still denied")
check("6b: if the SAME permanent failure recurs immediately, it goes back to "
      "UNAVAILABLE fast (only needed one more, per the conservative trial)",
      capJ.current_health() == ap.UNAVAILABLE)

K = prov("K")
reset_state([K])
capK = ap._capacity_for(K)
capK.load_persisted({"health": ap.UNAVAILABLE, "success": 1, "failure": 5})
capK.record_success()
check("6c: if the trial call SUCCEEDS instead, the provider is fully restored "
      "to HEALTHY", capK.current_health() == ap.HEALTHY)

print("\n=== Test 7: persistent cache round-trip (save -> reload -> same bounded state) ===")
tmp_cache = _TEST_CACHE_FILE   # already redirected at import time, before Test 1
L = prov("L")
reset_state([L])
capL = ap._capacity_for(L)
for _ in range(ap._UNAVAILABLE_THRESHOLD):
    capL.record_failure("HTTP 403 denied")   # triggers _mark_dirty -> _save_health_cache
check("7a: a cache file was actually written", tmp_cache.exists())
reloaded = json.loads(tmp_cache.read_text(encoding="utf-8"))
check("7b: the saved row reflects the UNAVAILABLE state", reloaded.get("L", {}).get("health") == ap.UNAVAILABLE)
# simulate a fresh process boundary: reload from disk into a NEW capacity object
ap._HEALTH_CACHE = ap._load_health_cache()
ap._CAPACITIES = {}
capL2 = ap._capacity_for(L)
check("7c: a freshly 'restarted' capacity picks up the persisted state as its "
      "starting point (one-trial, not hard-excluded, not full-trust either)",
      capL2.eligible_for_dispatch() is True)

print("\n=== Test 8: corrupt cache never crashes ===")
tmp_cache.write_text("{not valid json!!", encoding="utf-8")
loaded = ap._load_health_cache()
check("8: malformed JSON on disk -> loader returns a fresh empty dict, no exception", loaded == {})
tmp_cache.write_text('["a", "list", "not", "a", "dict"]', encoding="utf-8")
loaded2 = ap._load_health_cache()
check("8b: valid JSON but wrong shape (a list) -> also treated as fresh/empty", loaded2 == {})
tmp_cache.unlink(missing_ok=True)
loaded3 = ap._load_health_cache()
check("8c: missing file entirely -> fresh/empty, no exception", loaded3 == {})

print("\n=== Test 9: unknown/removed provider in cache is ignored safely ===")
M = prov("M")
reset_state([M])
ap._HEALTH_CACHE = {"M": {"health": "HEALTHY", "success": 1, "failure": 0},
                     "ghost_provider_no_longer_configured": {"health": "UNAVAILABLE", "success": 0, "failure": 99}}
capM = ap._capacity_for(M)
check("9a: a real, still-configured provider loads its cache row normally",
      capM.current_health() == ap.HEALTHY)
# force a save and confirm the ghost entry does not resurrect/crash anything
capM.record_failure("HTTP 500")
check("9b: saving after this does not raise despite the unknown cache entry present", True)
reloaded9 = json.loads(tmp_cache.read_text(encoding="utf-8"))
check("9c: the ghost provider (no longer in PROVIDERS) is dropped from the "
      "saved cache, not carried forward forever", "ghost_provider_no_longer_configured" not in reloaded9)
tmp_cache.unlink(missing_ok=True)

print("\n=== Test 10: total pool exhaustion still reaches extractive fallback (no crash) ===")
N = prov("N")
O = prov("O", tpm_budget=1000, max_concurrent=2)
reset_state([N, O])
capN = ap._capacity_for(N)
for _ in range(ap._UNAVAILABLE_THRESHOLD):
    capN.record_failure("HTTP 403 denied")
capO = ap._capacity_for(O)
capO.limiter.note_error(retry_after_s=30)   # rate-limited, long cooldown

def urlopen_always_429(req, timeout=None):
    raise http_error(429, "still limited")


orig_urlopen = ap.urllib.request.urlopen
ap.urllib.request.urlopen = urlopen_always_429
raised = None
try:
    ap.pool_generate("anything", as_json=False)
except ValueError as e:
    raised = e
except Exception as e:
    raised = e
ap.urllib.request.urlopen = orig_urlopen
check("10a: pool_generate() raises (ValueError, matching the pre-existing "
      f"'all providers failed' exception type) rather than crashing: {type(raised).__name__ if raised else None}",
      isinstance(raised, ValueError))
check("10b: this is EXACTLY the same exception type analyze.py's existing "
      "except-and-fall-back-to-extractive call site already handles - no "
      "interface change required there", isinstance(raised, ValueError))

ap._HEALTH_CACHE_FILE = _REAL_CACHE_FILE   # restore BEFORE any further module activity

# cleanup any stray files this suite may have left
for f in [tmp_cache]:
    try:
        f.unlink(missing_ok=True)
    except Exception:
        pass

# restore real module state (this file mutates ap.PROVIDERS/_CAPACITIES/etc. throughout;
# harmless in isolation since every test_*.py runs as its own process, but restored
# for hygiene consistency with the other test files in this repo)
import importlib
importlib.reload(ap)
check("11: real module state reloads cleanly after this suite's mutations "
      f"({len(ap.PROVIDERS)} real provider(s) restored)", len(ap.PROVIDERS) >= 1)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
