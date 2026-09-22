"""
test_gdelt_metrics.py - Phase 21D: deterministic tests for the observational
timing/outcome metrics added to gdelt_source._fetch()/_run() (the "metrics=" dict,
_classify_exc, _build_stage_metrics, _emit_stage_metrics). These tests exist to
prove the instrumentation is purely additive - _fetch()'s return value, exceptions,
retry count, and the existing print lines must be identical with or without it.

Never touches the real GDELT API, the real gdelt_gate state, or the real
gdelt_metrics.jsonl file.

Run:  py test_gdelt_metrics.py
"""
import json
import os
import socket
import ssl
import tempfile
import urllib.error

import gdelt_source as g

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


g.gdelt_gate.wait_for_slot = lambda *a, **k: 0.0
g.time.sleep = lambda s: None
g.random.uniform = lambda a, b: 0.0
g.METRICS_PATH = os.path.join(tempfile.mkdtemp(), "test_gdelt_metrics.jsonl")

_real_urlopen = g.urllib.request.urlopen


class _FakeResp:
    def __init__(self, body):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


print("=== _classify_exc: each network failure category maps correctly ===")
check("c1: HTTP 429 -> HTTP_429",
      g._classify_exc(urllib.error.HTTPError("u", 429, "x", None, None)) == "HTTP_429")
check("c2: HTTP 503 -> HTTP_5XX",
      g._classify_exc(urllib.error.HTTPError("u", 503, "x", None, None)) == "HTTP_5XX")
check("c3: HTTP 404 -> HTTP_4XX",
      g._classify_exc(urllib.error.HTTPError("u", 404, "x", None, None)) == "HTTP_4XX")
check("c4: DNS resolution failure -> DNS_FAILURE",
      g._classify_exc(urllib.error.URLError(socket.gaierror("getaddrinfo failed"))) == "DNS_FAILURE")
check("c5: TLS/SSL error -> TLS_FAILURE",
      g._classify_exc(urllib.error.URLError(ssl.SSLError("handshake timed out"))) == "TLS_FAILURE")
check("c6: socket timeout -> TIMEOUT",
      g._classify_exc(urllib.error.URLError(socket.timeout("timed out"))) == "TIMEOUT")
check("c7: connection refused -> CONNECTION_FAILURE",
      g._classify_exc(urllib.error.URLError(ConnectionRefusedError())) == "CONNECTION_FAILURE")
check("c8: a bare TimeoutError -> TIMEOUT", g._classify_exc(TimeoutError()) == "TIMEOUT")

print("\n=== _fetch(): metrics=None (every existing caller) is untouched - no crash, no side effect ===")
g.urllib.request.urlopen = lambda req, timeout=60: _FakeResp(b'{"articles": [{"url": "a"}]}')
arts = g._fetch("q", retries=1)
check("m1: return value is unaffected when metrics is not passed", arts == [{"url": "a"}])

print("\n=== _fetch(): metrics populated correctly on an immediate success ===")
qm = {}
arts = g._fetch("q success", retries=4, metrics=qm)
check("m2: attempts == 1", qm["attempts"] == 1, f"{qm}")
check("m3: classifications == ['SUCCESS']", qm["classifications"] == ["SUCCESS"])
check("m4: outcome == SUCCESS, articles == 1, attempts_exhausted == False",
      qm["outcome"] == "SUCCESS" and qm["articles"] == 1 and qm["attempts_exhausted"] is False)
check("m5: start/end timestamps are present and end >= start", qm["end_utc"] >= qm["start_utc"])
check("m6: exactly one attempt start timestamp was recorded", len(qm["attempt_starts_utc"]) == 1)

print("\n=== _fetch(): metrics populated correctly on 429-then-success ===")
_calls = {"n": 0}


def flaky_429_then_ok(req, timeout=60):
    _calls["n"] += 1
    if _calls["n"] == 1:
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
    return _FakeResp(b'{"articles": [{"url": "a"}, {"url": "b"}]}')


g.urllib.request.urlopen = flaky_429_then_ok
qm = {}
arts = g._fetch("q retry", retries=4, metrics=qm)
check("m7: attempts == 2, classifications == [HTTP_429, SUCCESS]",
      qm["attempts"] == 2 and qm["classifications"] == ["HTTP_429", "SUCCESS"], f"{qm}")
check("m8: outcome SUCCESS, 2 articles, retries were not exhausted",
      qm["outcome"] == "SUCCESS" and qm["articles"] == 2 and qm["attempts_exhausted"] is False)

print("\n=== _fetch(): metrics on a query that exhausts all retries on 429 ===")
g.urllib.request.urlopen = lambda req, timeout=60: (_ for _ in ()).throw(
    urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None))
qm = {}
try:
    g._fetch("q dead", retries=3, metrics=qm)
    raised = False
except urllib.error.HTTPError:
    raised = True
check("m9: the query still raises exactly as before (behavior unchanged)", raised)
check("m10: attempts == retries (3), outcome == HTTP_429, attempts_exhausted == True",
      qm["attempts"] == 3 and qm["outcome"] == "HTTP_429" and qm["attempts_exhausted"] is True, f"{qm}")
check("m11: all 3 attempts classified as HTTP_429",
      qm["classifications"] == ["HTTP_429", "HTTP_429", "HTTP_429"])

print("\n=== _fetch(): metrics on a DNS failure ===")
g.urllib.request.urlopen = lambda req, timeout=60: (_ for _ in ()).throw(
    urllib.error.URLError(socket.gaierror("getaddrinfo failed")))
qm = {}
try:
    g._fetch("q dns", retries=2, metrics=qm)
except urllib.error.URLError:
    pass
check("m12: DNS failure classified correctly end to end",
      qm["outcome"] == "DNS_FAILURE" and qm["classifications"] == ["DNS_FAILURE", "DNS_FAILURE"])

g.urllib.request.urlopen = _real_urlopen

print("\n=== _build_stage_metrics: aggregation across several per-query dicts ===")
q1 = {"attempts": 1, "gate_wait_s": 0.5, "max_gate_wait_s": 0.5,
      "attempt_starts_utc": ["2026-01-01T00:00:00+00:00"], "classifications": ["SUCCESS"]}
q2 = {"attempts": 3, "gate_wait_s": 2.0, "max_gate_wait_s": 1.2,
      "attempt_starts_utc": ["2026-01-01T00:00:10+00:00", "2026-01-01T00:00:20+00:00",
                              "2026-01-01T00:00:35+00:00"],
      "classifications": ["HTTP_429", "HTTP_429", "SUCCESS"]}
q3 = {}  # a query whose _fetch() was itself mocked away (no metrics at all) - must not crash aggregation
stage = g._build_stage_metrics([q1, q2, q3], "2026-01-01T00:00:00+00:00", 40.0,
                                ok_q=2, failed_q=1, total_q=3, added=7)
check("s1: total_http_attempts sums across queries (1+3+0=4)", stage["total_http_attempts"] == 4)
check("s2: count_429 == 2, count_success == 2", stage["count_429"] == 2 and stage["count_success"] == 2)
check("s3: gate_total_wait_s sums (0.5+2.0=2.5), gate_max_wait_s is the max (1.2)",
      stage["gate_total_wait_s"] == 2.5 and stage["gate_max_wait_s"] == 1.2)
check("s4: min_inter_request_interval_s is the smallest gap across ALL attempts globally (10s)",
      stage["min_inter_request_interval_s"] == 10.0, f"{stage['min_inter_request_interval_s']}")
check("s5: queries_succeeded/failed/total pass through unchanged", stage["queries_succeeded"] == 2
      and stage["queries_failed"] == 1 and stage["queries_total"] == 3)
check("s6: articles_added passes through unchanged", stage["articles_added"] == 7)

print("\n=== _emit_stage_metrics: writes one JSON line to METRICS_PATH, rotates when oversized ===")
path = os.path.join(tempfile.mkdtemp(), "metrics_emit_test.jsonl")
g.METRICS_PATH = path
g._emit_stage_metrics(stage)
with open(path, encoding="utf-8") as f:
    lines = f.readlines()
check("e1: exactly one line was written", len(lines) == 1)
parsed = json.loads(lines[0])
check("e2: the written record round-trips (same total_http_attempts)",
      parsed["total_http_attempts"] == 4)
check("e3: the persisted record DOES include the per-query detail",
      "queries" in parsed and len(parsed["queries"]) == 3)

g.METRICS_MAX_BYTES = 10   # force rotation on the next write
g._emit_stage_metrics(stage)
with open(path, encoding="utf-8") as f:
    lines2 = f.readlines()
check("e4: writing again after crossing METRICS_MAX_BYTES still leaves the file valid/parseable",
      all(json.loads(ln) for ln in lines2))

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL GDELT METRICS CHECKS PASSED")
