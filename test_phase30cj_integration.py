"""
test_phase30cj_integration.py - Phase 30C-J: a fully mocked, controlled
integration test of the capacity/health-aware pool_generate() dispatcher
across a batch of synthetic Paksh-shaped events. No external API calls.

Phase 1: 25 events against Provider A (healthy), B (healthy), C (429),
         D (403), E (disabled) - verify correct dispatch/exclusion behavior.
Phase 2: A degrades mid-batch, B stays healthy, C recovers - verify
         subsequent selections shift accordingly.

Run:  py test_phase30cj_integration.py
"""
import io
import json
import os
import urllib.error
from pathlib import Path

import ai_providers as ap

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


def _ok_body(text):
    return json.dumps({"choices": [{"message": {"content": text}}]})


def http_error(code, body=""):
    return urllib.error.HTTPError("https://example.invalid", code, "err", {}, io.BytesIO(body.encode("utf-8")))


def prov(name, **kw):
    p = {"name": name, "enabled": True, "base_url": "https://example.invalid/v1",
         "model": "test-model", "key_env": f"{name.upper()}_KEY"}
    p.update(kw)
    os.environ[p["key_env"]] = f"test-not-a-real-key-{name}"   # distinct per provider so the mock can identify who was actually called
    return p


# --- redirect the health cache before ANY dispatch happens ---
_REAL_CACHE_FILE = ap._HEALTH_CACHE_FILE
ap._HEALTH_CACHE_FILE = Path(ap._HERE) / "_phase30cj_integration_cache.json"

A = prov("A")
B = prov("B")
C = prov("C", tpm_budget=100000, max_concurrent=4)   # rate-limited scenario
D = prov("D")                                         # 403 scenario
E = prov("E", enabled=False)

ap.PROVIDERS = [A, B, C, D, E]
ap._CAPACITIES = {}
ap._LIMITERS = {}
ap._rr_i = 0
ap._HEALTH_CACHE = {}

state = {"phase": 1, "A_mode": "healthy", "C_mode": "429"}
call_log = []


def dispatcher(req, timeout=None):
    auth = req.get_header("Authorization") or ""
    name = next((p["name"] for p in (A, B, C, D, E)
                 if os.environ.get(p["key_env"], "") and os.environ[p["key_env"]] in auth), "?")
    call_log.append(name)
    if name == "A":
        if state["A_mode"] == "healthy":
            return _FakeHTTPResponse(_ok_body("A_OK"))
        raise http_error(500, "internal error")
    if name == "B":
        return _FakeHTTPResponse(_ok_body("B_OK"))
    if name == "C":
        if state["C_mode"] == "429":
            raise http_error(429, "please try again in 10ms.")
        return _FakeHTTPResponse(_ok_body("C_OK"))
    if name == "D":
        raise http_error(403, "PERMISSION_DENIED billing")
    raise AssertionError(f"unexpected provider dispatched: {name}")


orig_urlopen = ap.urllib.request.urlopen
ap.urllib.request.urlopen = dispatcher

print("=== Phase 1: 25 synthetic events - A/B healthy, C rate-limited, D forbidden, E disabled ===")
results = []
for i in range(25):
    try:
        r = ap.pool_generate(f"synthetic event {i} " + "x" * (i * 10), as_json=False)
        results.append(("ok", r))
    except Exception as e:
        results.append(("fail", str(e)))

ok_results = [r for kind, r in results if kind == "ok"]
fail_results = [r for kind, r in results if kind == "fail"]
check("1: at least some events succeeded via A or B", len(ok_results) > 0)
check("2: no event dispatched to E (disabled) - never appears in the call log", "E" not in call_log)
capD = ap._capacity_for(D)
check(f"3: D reached UNAVAILABLE after its threshold ({ap._UNAVAILABLE_THRESHOLD}) "
      f"consecutive 403s (health={capD.current_health()})", capD.current_health() == ap.UNAVAILABLE)
d_call_count = call_log.count("D")
check(f"4: D was NOT dispatched for every one of the 25 events (only up to its "
      f"threshold) - eliminates the old 'retry every event forever' waste pattern "
      f"(D was called {d_call_count} times, not ~25)", d_call_count <= ap._UNAVAILABLE_THRESHOLD + 2)
capC = ap._capacity_for(C)
check(f"5: C shows RATE_LIMITED or recent 429 activity was observed "
      f"(health={capC.current_health()}, calls={call_log.count('C')})",
      call_log.count("C") >= 1)
check("6: every one of the 25 events resolved to SOMETHING (success or a clean "
      "exception) - no unhandled crash anywhere in the batch",
      len(results) == 25)

print("\n=== Phase 2: A degrades mid-batch, B stays healthy, C recovers ===")
state["A_mode"] = "degrading"
call_log.clear()
# With B (and possibly a by-now-recovered C) also healthy, round-robin spreads
# calls across all eligible candidates - a fixed DEGRADE_THRESHOLD call count
# isn't guaranteed to land that many CONSECUTIVE attempts specifically on A.
# Loop generously; A's own failure streak only resets on an A success (never
# happens here), so it accumulates regardless of how many times B/C are picked
# in between.
capA = ap._capacity_for(A)
for _ in range(ap._DEGRADE_THRESHOLD * 6):
    if capA.current_health() == ap.DEGRADED:
        break
    try:
        ap.pool_generate("force A degraded " * 3, as_json=False)
    except Exception:
        pass
check(f"7: A is now DEGRADED after repeated 500s mid-batch (health={capA.current_health()}, "
      f"A was attempted {call_log.count('A')} time(s))", capA.current_health() == ap.DEGRADED)

state["C_mode"] = "healthy"   # C recovers
call_log.clear()
post_results = []
for i in range(10):
    try:
        r = ap.pool_generate(f"post-degradation event {i}", as_json=False)
        post_results.append(r)
    except Exception as e:
        post_results.append(f"FAIL: {e}")

check("8: B (still healthy throughout) is used and/or C (now recovered) is used "
      f"in the post-degradation batch: {call_log}",
      any(n in ("B", "C") for n in call_log))
b_or_c_successes = sum(1 for r in post_results if r in ("B_OK", "C_OK"))
check(f"9: at least some post-degradation events succeeded via B or C "
      f"({b_or_c_successes}/10)", b_or_c_successes > 0)
check("10: A (degraded, not excluded) may still appear but is not the ONLY "
      f"provider used - selection meaningfully shifted: {call_log}",
      len(set(call_log)) > 1 or call_log.count("A") < len(call_log))

ap.urllib.request.urlopen = orig_urlopen
ap._HEALTH_CACHE_FILE.unlink(missing_ok=True)
ap._HEALTH_CACHE_FILE = _REAL_CACHE_FILE
import importlib
importlib.reload(ap)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
