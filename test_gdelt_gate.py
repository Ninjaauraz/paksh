"""
test_gdelt_gate.py - Phase 21C: deterministic tests for the cross-process GDELT
pacing gate (gdelt_gate.py) and its integration into gdelt_source._fetch().

Uses a throwaway temp directory (PAKSH_STATE_DIR) for gate state - never touches the
real %LOCALAPPDATA%\\Paksh state, never makes a real HTTP request. The cross-process
test (section 4) spawns real short-lived Python subprocesses against the same shared
state dir, because that is the actual property being guaranteed - two threads in one
process are not a faithful stand-in for two independent `py gdelt_source.py` runs.

Run:  py test_gdelt_gate.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

STATE_DIR = tempfile.mkdtemp(prefix="paksh_gdelt_gate_test_")
os.environ["PAKSH_STATE_DIR"] = STATE_DIR
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO_ROOT)

import gdelt_gate as gate  # noqa: E402

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def reset_state():
    for name in ("gdelt_gate.json", "gdelt_gate.lock"):
        p = os.path.join(STATE_DIR, name)
        if os.path.exists(p):
            os.remove(p)


print("=== 1/7: first request when no state exists (missing state) ===")
reset_state()
check("1a: state file does not exist yet", not os.path.exists(gate._state_path()))
waited = gate.wait_for_slot(min_interval=0.3)
check("1b: no prior state -> no wait", waited == 0.0, f"waited={waited}")
check("1c: a reservation was persisted", os.path.exists(gate._state_path()))

print("\n=== 2/3: second request before vs after the interval has elapsed ===")
reset_state()
gate.wait_for_slot(min_interval=0.3)
t0 = time.monotonic()
waited2 = gate.wait_for_slot(min_interval=0.3)
elapsed = time.monotonic() - t0
check("2a: a request right after the first waits roughly one interval",
      0.15 <= waited2 <= 0.45, f"waited={waited2}")
check("2b: the call actually blocked for about that long", elapsed >= 0.15, f"elapsed={elapsed}")

reset_state()
gate.wait_for_slot(min_interval=0.2)
time.sleep(0.3)
waited3 = gate.wait_for_slot(min_interval=0.2)
check("3a: a request after the interval already elapsed does not wait",
      waited3 == 0.0, f"waited={waited3}")

print("\n=== 4/5/12/13: independent processes get serialized, non-overlapping, evenly spaced slots ===")
reset_state()
N = 3
INTERVAL = 1.0
worker_src = (
    "import os, sys, json, time\n"
    f"sys.path.insert(0, {REPO_ROOT!r})\n"
    f"os.environ['PAKSH_STATE_DIR'] = {STATE_DIR!r}\n"
    "import gdelt_gate as gate\n"
    f"w = gate.wait_for_slot(min_interval={INTERVAL})\n"
    "print(json.dumps({'wait': w, 'reserved_at': gate._read_last_request().isoformat()}))\n"
)
worker_path = os.path.join(STATE_DIR, "_worker.py")
with open(worker_path, "w", encoding="utf-8") as f:
    f.write(worker_src)

procs = [subprocess.Popen([sys.executable, worker_path], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True) for _ in range(N)]
outs = [p.communicate(timeout=30) for p in procs]
results = []
for out, err in outs:
    try:
        results.append(json.loads(out.strip().splitlines()[-1]))
    except Exception as e:
        check(f"4x: worker produced parseable output ({e})", False, f"stdout={out!r} stderr={err!r}")

reserved_times = sorted(datetime.fromisoformat(r["reserved_at"]) for r in results)
gaps = [(reserved_times[i + 1] - reserved_times[i]).total_seconds() for i in range(len(reserved_times) - 1)]
check("4a: all N independent processes got a slot (none crashed/deadlocked)", len(results) == N,
      f"got {len(results)}")
check("5a: no two processes reserved the same slot (atomic reservation)",
      len(set(reserved_times)) == len(reserved_times))
check("12a/13a: consecutive reservations are spaced by ~INTERVAL - serialized, not a burst",
      all(g >= INTERVAL * 0.7 for g in gaps), f"gaps={gaps}")
os.remove(worker_path)

print("\n=== 6: corrupt state file is reset safely, never blocks forever ===")
reset_state()
with open(gate._state_path(), "w", encoding="utf-8") as f:
    f.write("{not valid json")
waited = gate.wait_for_slot(min_interval=0.2)
check("6a: corrupt JSON is treated as no prior state (no wait)", waited == 0.0, f"waited={waited}")
with open(gate._state_path(), encoding="utf-8") as f:
    reparsed = json.load(f)
check("6b: the state file is valid JSON again afterwards", "last_request_utc" in reparsed)

print("\n=== 8: a persisted timestamp in the future (clock moved backwards) is not trusted ===")
reset_state()
future = datetime.now(timezone.utc) + timedelta(hours=1)
with open(gate._state_path(), "w", encoding="utf-8") as f:
    json.dump({"last_request_utc": future.isoformat()}, f)
waited = gate.wait_for_slot(min_interval=0.2)
check("8a: a future persisted timestamp does not force an hour-long wait",
      waited < 1.0, f"waited={waited}")

print("\n=== 9/10/11: gdelt_source._fetch() sends every attempt (incl. retries) through the gate, "
      "honours Retry-After, and a 429 can be followed by success ===")
import urllib.error  # noqa: E402
import gdelt_source as g  # noqa: E402

_orig_gate_wait = g.gdelt_gate.wait_for_slot
_orig_sleep = g.time.sleep
_orig_uniform = g.random.uniform
_orig_urlopen = g.urllib.request.urlopen

gate_calls = []
sleeps = []
g.gdelt_gate.wait_for_slot = lambda *a, **k: (gate_calls.append((a, k)), 0.0)[1]
g.time.sleep = lambda s: sleeps.append(s)
g.random.uniform = lambda a, b: 0.0

_attempts = {"n": 0}


class _FakeHTTPResp:
    def __init__(self, body):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def flaky_urlopen(req, timeout=60):
    _attempts["n"] += 1
    if _attempts["n"] < 3:
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": "1"}, None)
    return _FakeHTTPResp(b'{"articles": [{"url": "https://a/1"}]}')


g.urllib.request.urlopen = flaky_urlopen
arts = g._fetch("q", retries=4)

check("9a: every attempt (2 failures + 1 success = 3) passed through the gate first",
      len(gate_calls) == 3, f"gate_calls={len(gate_calls)}")
check("10a: the Retry-After header value (1s) was honoured for both backoff sleeps",
      sleeps == [1.0, 1.0], f"sleeps={sleeps}")
check("11a: a query that 429s twice still succeeds once GDELT stops refusing it",
      arts == [{"url": "https://a/1"}])

g.gdelt_gate.wait_for_slot = _orig_gate_wait
g.time.sleep = _orig_sleep
g.random.uniform = _orig_uniform
g.urllib.request.urlopen = _orig_urlopen

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    raise SystemExit(1)
print("ALL GDELT GATE CHECKS PASSED")
shutil.rmtree(STATE_DIR, ignore_errors=True)
