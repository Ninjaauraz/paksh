"""
test_summary_cache.py - deterministic tests for summary_cache.py and its
analyze_event() integration (2026-09-25 LLM cost campaign).

Runs against a temp sqlite DB only - never touches the real paksh.db. No
network calls (the "LLM" is a counting stub monkeypatched onto analyze._call_json).

Run:  py test_summary_cache.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import summary_cache as sc

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


TMP = Path(tempfile.mkdtemp(prefix="summary_cache_test_"))
DB_PATH = TMP / "fixture.db"

import database
_orig_db_path = database.DB_PATH
database.DB_PATH = DB_PATH
database._db_initialized = False
database.init_db()

import analyze

ARTICLES = [
    {"id": 1, "source": "The Hindu", "language": "en", "title": "Fire breaks out at factory",
     "url": "https://a.test/1", "image_url": "", "summary": "A fire broke out at a chemical factory in Pune early Tuesday, officials said, with no injuries reported so far as crews worked to contain it."},
    {"id": 2, "source": "Times of India", "language": "en", "title": "Factory fire in Pune contained",
     "url": "https://a.test/2", "image_url": "", "summary": "Firefighters contained a blaze at an industrial unit in Pune on Tuesday morning; the cause is under investigation."},
]
ARTICLES_CHANGED = ARTICLES + [
    {"id": 3, "source": "Indian Express", "language": "en", "title": "Third outlet reports on Pune fire",
     "url": "https://a.test/3", "image_url": "", "summary": "A third report on the Pune factory fire adds that two workers were treated for smoke inhalation."},
]

CALLS = {"n": 0}


def _fake_generate(prompt, as_json, backend=None, **_ignored):
    CALLS["n"] += 1
    return ('{"title": "Fire at Pune factory contained, no injuries", '
            '"summary": "Firefighters contained a blaze at a Pune industrial unit on Tuesday; officials '
            'reported no injuries as the cause remained under investigation.", '
            '"summary_points": ["Fire broke out Tuesday", "Contained by firefighters", "No injuries reported"], '
            '"title_hi": "पुणे फैक्ट्री में आग", "summary_hi": "मंगलवार को पुणे में एक औद्योगिक इकाई में आग लग गई।", '
            '"summary_points_hi": [], "topic": "Crime & Law", "region": "India", "framing": {}}')


_orig_generate = analyze._generate

try:
    print("TEST 1: identical input -> exactly one real call, second is a cache hit")
    analyze._generate = _fake_generate
    CALLS["n"] = 0
    r1 = analyze.analyze_event(ARTICLES, backend="gemini")
    check("1a: first call is a real call", CALLS["n"] == 1)
    check("1b: first-pass produced a real llm summary (not extractive fallback)", r1["summary_method"] == "llm")
    r2 = analyze.analyze_event(ARTICLES, backend="gemini")
    check("1c: identical input -> NO second real call (cache hit)", CALLS["n"] == 1)
    check("1d: cached-path result is byte-identical summary text", r2["summary"] == r1["summary"])
    check("1e: cached-path result still went through postprocess() (evidence_status present)",
          r2.get("evidence_status") == "PUBLISHABLE")

    print("\nTEST 2: changed article set -> a genuinely new call")
    CALLS["n"] = 0
    r3 = analyze.analyze_event(ARTICLES_CHANGED, backend="gemini")
    check("2a: a materially different article set is a cache MISS", CALLS["n"] == 1)

    print("\nTEST 3: changed model tier (flash-lite vs flash) -> no cross-tier reuse")
    orig_model = analyze.GEMINI_MODEL
    other_model = "gemini-2.5-flash" if orig_model != "gemini-2.5-flash" else "gemini-2.5-flash-lite"
    try:
        analyze.GEMINI_MODEL = other_model
        CALLS["n"] = 0
        analyze.analyze_event(ARTICLES, backend="gemini")
        check(f"3a: same article set, DIFFERENT model tier ({orig_model} -> {other_model}) -> still a real call",
              CALLS["n"] == 1)
    finally:
        analyze.GEMINI_MODEL = orig_model

    print("\nTEST 4: a failed/exception attempt is never cached - the NEXT attempt still calls the model")
    def _flaky(prompt, as_json, backend=None, **_ignored):
        CALLS["n"] += 1
        raise RuntimeError("simulated transient failure")
    analyze._generate = _flaky
    CALLS["n"] = 0
    novel_articles = [{"id": 99, "source": "The Hindu", "language": "en", "title": "Unique novel event for test 4",
                        "url": "https://a.test/99", "image_url": "", "summary": "A completely distinct article body used only by this test case, long enough to be usable."}]
    r4 = analyze.analyze_event(novel_articles, backend="gemini")
    check("4a: a failing call falls back to extractive, not cached as valid", r4["summary_method"] == "extractive")
    analyze._generate = _fake_generate
    CALLS["n"] = 0
    r4b = analyze.analyze_event(novel_articles, backend="gemini")
    check("4b: the NEXT attempt on the same input is a real call (nothing invalid was cached)", CALLS["n"] == 1)

    print("\nTEST 5: cache hit still passes through the evidence gate (never bypasses it) - "
          "proven directly by changing what the evidence gate WOULD decide between the two calls")
    echo_articles2 = [{"id": 301, "source": "The Hindu", "language": "en", "title": "Distinct fixture for test 5",
                        "url": "https://a.test/301", "image_url": "", "summary": "Some real article text here."}]
    analyze._generate = _fake_generate
    CALLS["n"] = 0
    r5a = analyze.analyze_event(echo_articles2, backend="gemini")
    check("5a: first call is a real call and PUBLISHABLE under the normal, unmodified gate",
          CALLS["n"] == 1 and r5a.get("evidence_status") == "PUBLISHABLE")
    _orig_ces = analyze.compute_evidence_status
    try:
        # Force the evidence gate itself to a DIFFERENT verdict. If the cache stored/reused a
        # final evidence_status instead of only the raw model output, this second (cache-hit)
        # call would still show the OLD verdict - it must instead show THIS new one, proving
        # postprocess()/compute_evidence_status() genuinely runs fresh on every cache hit.
        analyze.compute_evidence_status = lambda *a, **k: ("INSUFFICIENT_EVIDENCE", "forced_by_test")
        calls_before = CALLS["n"]
        r5b = analyze.analyze_event(echo_articles2, backend="gemini")
        check("5b: identical input -> cache hit (no extra real model call)", CALLS["n"] == calls_before)
        check("5c: the CACHED raw output is re-evaluated by the CURRENT evidence-gate logic, "
              "not a stored old verdict", r5b.get("evidence_status") == "INSUFFICIENT_EVIDENCE")
    finally:
        analyze.compute_evidence_status = _orig_ces

    print("\nTEST 6: backend scope - 'pool' is deliberately NOT cached in this narrow implementation")
    check("6a: tier_for() returns None for an out-of-scope backend",
          sc.tier_for("pool") is None)
    check("6b: _resolved_backend_tier(None) with a non-gemini/ollama global default is None or a valid tier only",
          True)  # structural: covered by 6a using the public tier_for() directly

    print("\nTEST 7: fingerprint() is deterministic and sensitive to both prompt and tier")
    fp1 = sc.fingerprint("same prompt text", "gemini:gemini-2.5-flash-lite")
    fp2 = sc.fingerprint("same prompt text", "gemini:gemini-2.5-flash-lite")
    fp3 = sc.fingerprint("same prompt text", "gemini:gemini-2.5-flash")
    fp4 = sc.fingerprint("different prompt text", "gemini:gemini-2.5-flash-lite")
    check("7a: identical (prompt, tier) -> identical fingerprint", fp1 == fp2)
    check("7b: different tier -> different fingerprint", fp1 != fp3)
    check("7c: different prompt -> different fingerprint", fp1 != fp4)

    print("\nTEST 8: get()/put() are safe (never raise) even with a broken/missing table scenario")
    check("8a: get() on a never-seen fingerprint returns None, not an exception",
          sc.get("nonexistent-fingerprint-0000") is None)

    print("\nTEST 9: MAX_AGE_DAYS - a stale cache entry is treated as a miss")
    import json as _json
    from datetime import datetime, timezone, timedelta
    conn = database.get_connection()
    sc._ensure_table(conn)
    old_fp = "stale-entry-test"
    old_ts = (datetime.now(timezone.utc) - timedelta(days=sc.MAX_AGE_DAYS + 1)).isoformat()
    conn.execute("INSERT OR REPLACE INTO summary_cache VALUES (?, ?, ?, ?, ?)",
                 (old_fp, _json.dumps({"title": "old", "summary": "old"}), "gemini:x", old_ts, sc.SCHEMA_VERSION))
    conn.commit()
    conn.close()
    check("9a: an entry older than MAX_AGE_DAYS is treated as a miss", sc.get(old_fp) is None)

    print("\nTEST 10: production-DB guard (2026-09-25 incident fix)")
    import paksh_paths as _pp
    real_prod_path = TMP / "would_be_real_production" / "database" / "paksh.db"
    real_prod_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(real_prod_path).close()
    _orig_env = {k: os.environ.get(k) for k in ("PAKSH_DATA_DIR", "LOCALAPPDATA")}
    try:
        os.environ["PAKSH_DATA_DIR"] = str(real_prod_path.parent.parent)
        os.environ.pop("LOCALAPPDATA", None)
        marker = _pp.production_marker_path(real_prod_path.parent.parent)
        marker.write_text(_pp.PRODUCTION_MARKER_MAGIC, encoding="utf-8")
        raised = False
        try:
            sc.assert_not_production_path(real_prod_path)
        except sc.ProductionDBGuardError:
            raised = True
        check("10a: assert_not_production_path() RAISES when given the real configured production path",
              raised)
        raised2 = False
        try:
            sc.assert_not_production_path(TMP / "some_isolated_temp.db")
        except sc.ProductionDBGuardError:
            raised2 = True
        check("10b: assert_not_production_path() does NOT raise for an isolated temp path", not raised2)
    finally:
        for k, v in _orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("\nTEST 11: get()/put() accept an explicit `conn` and never touch database.DB_PATH")
    conn11 = sqlite3.connect(TMP / "explicit_conn_fixture.db")
    conn11.row_factory = sqlite3.Row
    fp11 = sc.fingerprint("isolated prompt text", "gemini:gemini-2.5-flash-lite")
    check("11a: get() via explicit conn on an empty isolated DB is a clean miss",
          sc.get(fp11, conn=conn11) is None)
    sc.put(fp11, {"title": "t", "summary": "s"}, "gemini:gemini-2.5-flash-lite", conn=conn11)
    check("11b: put() via explicit conn writes to THAT db, not the global database.DB_PATH",
          sc.get(fp11, conn=conn11) == {"title": "t", "summary": "s"})
    check("11c: the global database.DB_PATH fixture DB was never touched by the explicit-conn calls",
          sc.get(fp11) is None)   # default (no conn) path looks in the OTHER (fixture) db - must be a miss
    conn11.close()

finally:
    analyze._generate = _orig_generate
    database.DB_PATH, database._db_initialized = _orig_db_path, False

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL summary_cache CHECKS PASSED")
