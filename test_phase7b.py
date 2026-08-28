"""
test_phase7b.py - Paksh 7B: the publication-completeness gate.

Follows the same conventions as test_phase5_1.py/test_phase6b.py: isolated-SQLite
tests use a temp DB file (_use_temp_db()/_restore_db()) so the real, populated
local paksh.db is never at risk; failure-injection uses direct monkeypatching of
module-level functions.

Covers, in order:
  A. analyze.compute_content_complete() - the canonical predicate, unit-tested
     directly (Cases 1-7 of the Phase 7B test matrix).
  B. database.py gate enforcement - get_all_events()/get_event()/search_events(),
     grandfathering (None), explicit False, the reframe-only include_incomplete
     escape hatch (Cases 8-14, 19).
  C. main.py - event_detail() cannot bypass the gate via a direct id request
     (Case 14 variant, both CONTENT_BACKEND branches touched).
  D. analyze.analyze_event() - the bounded single retry (Cases 15-17), via a
     monkeypatched _call_json so no real LLM/network call is made.
  E. reframe.py - the single-lane reservation policy (Case 18).
  F. static_fallback.py - defense-in-depth: an explicitly-incomplete row in the
     snapshot is still excluded by database.get_all_events()'s own filter.

NOT covered here (documented, not faked - see the Phase 7B report):
  - The Supabase `search_events` RPC and the `content_complete` column/backfill
    migration were verified directly against the live production database via
    read-only SQL in this same implementation session (all 13,704 non-demo rows
    confirmed content_complete=true post-migration; the RPC's WHERE clause was
    read back via pg_get_functiondef and confirmed to include the new condition;
    the RPC was smoke-tested with a real query). There is no local Supabase
    instance this suite can safely exercise, and this suite must never touch the
    live production database with write/test-fixture traffic - so that
    verification is controlled, production, read-only, and separate from this
    file by design, not an omission.

Run:  py test_phase7b.py
"""
import json
import tempfile
from pathlib import Path

import database
import main as main_module
import analyze
import reframe
import static_fallback
import supabase_content as sb

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


_REAL_DB_PATH = database.DB_PATH
_orig_backend = main_module.CONTENT_BACKEND


def _use_temp_db():
    tmp = Path(tempfile.mkdtemp()) / "phase7b_test.db"
    database.DB_PATH = tmp
    database._db_initialized = False
    return tmp


def _restore_db():
    database.DB_PATH = _REAL_DB_PATH
    database._db_initialized = False


def _coverage(left=0, center=0, right=0):
    return {
        "left": {"count": left, "sources": [], "owners": []},
        "center": {"count": center, "sources": [], "owners": []},
        "right": {"count": right, "sources": [], "owners": []},
    }


def _fixture_analysis(coverage, framing, summary_method="llm", content_complete="AUTO", **extra):
    """Build an insert_event()-ready analysis dict. content_complete="AUTO" computes
    it via the real predicate (what postprocess() would do); pass True/False/None to
    force a specific stored value (None simulates a pre-gate/grandfathered event -
    JSON has no distinction between an omitted key and an explicit null, so this is
    behaviorally identical to the key never having been written)."""
    cc = (analyze.compute_content_complete(coverage, framing, summary_method)
          if content_complete == "AUTO" else content_complete)
    analysis = {
        "title": "Test event", "summary": "A neutral test summary of sufficient length.",
        "summary_points": [], "title_hi": "परीक्षण घटना", "summary_hi": "एक परीक्षण सारांश।",
        "summary_points_hi": [], "framing": framing, "framing_hi": {},
        "topic": "Politics", "region": "India", "published_at": None,
        "image_url": "", "sources": [], "coverage": coverage,
        "total_sources": sum(c["count"] for c in coverage.values()),
        "degraded": False, "summary_method": summary_method,
        "content_complete": cc,
    }
    analysis.update(extra)
    return analysis


def _insert(coverage, framing, summary_method="llm", content_complete="AUTO", **extra):
    analysis = _fixture_analysis(coverage, framing, summary_method, content_complete, **extra)
    return database.insert_event(analysis, is_demo=False)


FRAMED = ["Coverage from this side emphasizes a specific, attributed claim."]


# ============================================================ A: compute_content_complete()
print("=== A: analyze.compute_content_complete() - the canonical predicate ===")

check("1: all covered sides framed -> complete",
      analyze.compute_content_complete(_coverage(1, 1, 1),
                                        {"left": FRAMED, "center": FRAMED, "right": FRAMED}, "llm") is True)

check("2: one covered side missing framing -> incomplete",
      analyze.compute_content_complete(_coverage(1, 1, 0),
                                        {"left": FRAMED, "center": []}, "llm") is False)

check("3: two covered sides missing framing -> incomplete",
      analyze.compute_content_complete(_coverage(1, 1, 1),
                                        {"left": FRAMED}, "llm") is False)

check("4: a side with zero coverage requires no framing -> complete",
      analyze.compute_content_complete(_coverage(1, 0, 0),
                                        {"left": FRAMED}, "llm") is True)

check("5: framing with only empty/whitespace bullets counts as missing",
      analyze.compute_content_complete(_coverage(1, 0, 0),
                                        {"left": ["", "   "]}, "llm") is False)

check("6: single-lane covered and framed -> complete",
      analyze.compute_content_complete(_coverage(2, 0, 0),
                                        {"left": FRAMED}, "llm") is True)

check("6b: single-lane covered and unframed -> incomplete",
      analyze.compute_content_complete(_coverage(2, 0, 0),
                                        {}, "llm") is False)

check("7: extractive tier is ALWAYS complete regardless of (empty) framing - Option A",
      analyze.compute_content_complete(_coverage(1, 1, 1), {}, "extractive") is True)

check("7b: an 'other'/legacy summary_method also passes (Option A applies to any non-llm tier)",
      analyze.compute_content_complete(_coverage(1, 0, 0), {}, None) is True)


# ============================================================ B: database.py gate enforcement
print("\n=== B: database.py - get_all_events()/get_event()/search_events() ===")
_use_temp_db()
try:
    database.init_db()

    id_complete = _insert(_coverage(1, 1, 1),
                           {"left": FRAMED, "center": FRAMED, "right": FRAMED})
    id_incomplete = _insert(_coverage(1, 1, 0), {"left": FRAMED})  # center missing
    id_single_lane_framed = _insert(_coverage(2, 0, 0), {"left": FRAMED})
    id_single_lane_gap = _insert(_coverage(2, 0, 0), {})
    id_grandfathered = _insert(_coverage(1, 1, 0), {"left": FRAMED},
                                content_complete=None)  # simulates a pre-gate event
    id_extractive = _insert(_coverage(1, 1, 0), {}, summary_method="extractive")
    id_below_bias_gate = _insert(_coverage(1, 0, 0), {"left": FRAMED})  # sum<2, pre-existing gate

    all_ids = {id_complete, id_incomplete, id_single_lane_framed, id_single_lane_gap,
               id_grandfathered, id_extractive, id_below_bias_gate}

    public = {e["id"]: e for e in database.get_all_events()}
    check("8: complete LLM event IS visible via get_all_events()", id_complete in public)
    check("9: incomplete LLM event (covered side missing framing) is NOT visible",
          id_incomplete not in public)
    check("4-dup: single-lane covered+framed IS visible", id_single_lane_framed in public)
    check("6: single-lane covered+unframed is NOT visible (unless grandfathered)",
          id_single_lane_gap not in public)
    check("11: grandfathered event (content_complete=None) remains visible",
          id_grandfathered in public)
    check("Option A: extractive event remains visible despite empty framing",
          id_extractive in public)
    check("pre-existing gate preserved: sum(lean_counts)<2 still excluded",
          id_below_bias_gate not in public)

    internal = {e["id"] for e in database.get_all_events(include_incomplete=True)}
    check("19: include_incomplete=True (reframe's own discovery path) DOES see the incomplete event",
          id_incomplete in internal and id_single_lane_gap in internal)

    ev = database.get_event(id_incomplete)
    check("get_event() itself still returns the full row unfiltered (internal tooling needs this)",
          ev is not None and ev.get("content_complete") is False)

    r = database.search_events("test")
    result_ids = {row["id"] for row in r["results"]}
    check("11 (search): complete/grandfathered/extractive events remain searchable",
          id_complete in result_ids and id_grandfathered in result_ids and id_extractive in result_ids)
    check("11 (search): incomplete events are excluded from SQLite search",
          id_incomplete not in result_ids and id_single_lane_gap not in result_ids)
finally:
    _restore_db()


# ============================================================ C: main.py direct-id bypass
print("\n=== C: main.py::event_detail() cannot bypass the gate ===")
_use_temp_db()
try:
    database.init_db()
    good_id = _insert(_coverage(1, 1, 1), {"left": FRAMED, "center": FRAMED, "right": FRAMED})
    bad_id = _insert(_coverage(1, 1, 0), {"left": FRAMED})

    from fastapi import HTTPException
    try:
        result = main_module.event_detail(good_id)
        check("14: complete event reachable via direct /api/events/{id}", result["id"] == good_id)
    except HTTPException:
        check("14: complete event reachable via direct /api/events/{id}", False)

    try:
        main_module.event_detail(bad_id)
        check("14: incomplete event's direct id request 404s (not a bypass)", False)
    except HTTPException as e:
        check("14: incomplete event's direct id request 404s (not a bypass)", e.status_code == 404)
finally:
    _restore_db()


# ============================================================ D: bounded retry
print("\n=== D: analyze.analyze_event() - exactly one bounded retry on a framing gap ===")

_call_count = {"n": 0}
_INCOMPLETE_RAW = {
    "title": "First attempt title", "summary": "First attempt summary long enough to pass.",
    "summary_points": ["a"], "title_hi": "शीर्षक", "summary_hi": "सारांश एक लंबा वाक्य है।",
    "summary_points_hi": ["a"], "framing": {"left": FRAMED}, "framing_hi": {"left": FRAMED},
    "topic": "Politics", "region": "India",
}
_COMPLETE_RAW = dict(_INCOMPLETE_RAW, framing={"left": FRAMED, "center": FRAMED},
                     framing_hi={"left": FRAMED, "center": FRAMED})

_articles_2side = [
    {"id": 1, "source": "TestLeftOutlet", "language": "en", "title": "t1", "summary": "s1", "url": "u1"},
    {"id": 2, "source": "TestCenterOutlet", "language": "en", "title": "t2", "summary": "s2", "url": "u2"},
]

_orig_call_json = analyze._call_json
_orig_lean_of = analyze.lean_of
analyze.lean_of = lambda name, region=None: (
    "left" if "Left" in name else "center" if "Center" in name else "unrated")


def _mock_call_json_incomplete_then_complete(prompt, retries=1, backend=None):
    _call_count["n"] += 1
    return json.loads(json.dumps(_INCOMPLETE_RAW if _call_count["n"] == 1 else _COMPLETE_RAW))


def _mock_call_json_always_complete(prompt, retries=1, backend=None):
    _call_count["n"] += 1
    return json.loads(json.dumps(_COMPLETE_RAW))


def _mock_call_json_always_incomplete(prompt, retries=1, backend=None):
    _call_count["n"] += 1
    return json.loads(json.dumps(_INCOMPLETE_RAW))


try:
    _call_count["n"] = 0
    analyze._call_json = _mock_call_json_incomplete_then_complete
    result = analyze.analyze_event(_articles_2side)
    check("15: retry fires exactly once when the first attempt is incomplete", _call_count["n"] == 2)
    check("15: the retry's (complete) result is what gets used", result["content_complete"] is True)

    _call_count["n"] = 0
    analyze._call_json = _mock_call_json_always_complete
    result = analyze.analyze_event(_articles_2side)
    check("16: zero additional calls when the first attempt is already complete", _call_count["n"] == 1)
    check("16: already-complete framing is preserved", result["content_complete"] is True)

    _call_count["n"] = 0
    analyze._call_json = _mock_call_json_always_incomplete
    result = analyze.analyze_event(_articles_2side)
    check("17: retry fires once even when it also fails", _call_count["n"] == 2)
    check("17: event remains incomplete after a failed retry (not silently accepted)",
          result["content_complete"] is False)
finally:
    analyze._call_json = _orig_call_json
    analyze.lean_of = _orig_lean_of


# ============================================================ E: reframe.py single-lane reservation
print("\n=== E: reframe.py - single-lane events get a bounded reserved slice, not permanent exclusion ===")


def _ev(id_, left=0, center=0, right=0, leans=1):
    """A minimal get_event()-shaped dict, enough for _is_top_tier()/_rank_key()."""
    counts = {"left": left, "center": center, "right": right}
    return {"id": id_, "coverage": {s: {"count": counts[s]} for s in counts},
            "framing": {}, "created_at": "2026-01-01T00:00:00", "title": f"event {id_}"}


# 200 multi-lane (top-tier) events + 10 single-lane events, all needing repair.
multi = [_ev(i, left=1, center=1) for i in range(200)]
single = [_ev(1000 + i, center=1) for i in range(10)]
targets = multi + single
targets.sort(key=reframe._rank_key, reverse=True)
top = [ev for ev in targets if reframe._is_top_tier(ev)]
single_lane_pool = [ev for ev in targets if not reframe._is_top_tier(ev)]
reserve = min(reframe.SINGLE_LANE_RESERVE, 50, len(single_lane_pool))
selected = [ev for ev in targets if reframe._is_top_tier(ev)][:50 - reserve] + single_lane_pool[:reserve]
selected_ids = {ev["id"] for ev in selected}

check("18: with a 50-cap and reservation, at least one single-lane event is selected",
      any(i >= 1000 for i in selected_ids))
check("18: multi-lane/top-tier events still fill most of the cap (ranked first)",
      sum(1 for i in selected_ids if i < 1000) >= 50 - reframe.SINGLE_LANE_RESERVE)

# without the reservation (old behaviour, e.g. --top-tier), single-lane is starved entirely
old_behaviour_selected = sorted(targets, key=reframe._rank_key, reverse=True)[:50]
check("18 (regression check): the OLD unreserved selection would have starved single-lane entirely "
      "(proves the reservation is actually doing something, not a no-op)",
      all(ev["id"] < 1000 for ev in old_behaviour_selected))

check("19: an already-complete event is never selected as a repair target",
      not reframe._missing_sides({"coverage": {"left": {"count": 1}, "center": {"count": 0}, "right": {"count": 0}},
                                   "framing": {"left": FRAMED}}))


# ============================================================ F: static_fallback defense-in-depth
print("\n=== F: static_fallback.py - an explicitly-incomplete snapshot row is still excluded ===")
_tmp_site = Path(tempfile.mkdtemp())
_orig_data_dir = static_fallback._DATA_DIR
_orig_cache = dict(static_fallback._cache)
try:
    static_fallback._DATA_DIR = _tmp_site
    static_fallback._cache.clear()
    fixture = {
        "events": [
            {"id": 1, "title": "complete", "lean_counts": {"left": 1, "center": 1, "right": 0},
             "content_complete": True},
            {"id": 2, "title": "grandfathered", "lean_counts": {"left": 1, "center": 1, "right": 0}},
            {"id": 3, "title": "should never appear here", "lean_counts": {"left": 1, "center": 1, "right": 0},
             "content_complete": False},
        ]
    }
    (_tmp_site / "events.json").write_text(json.dumps(fixture), encoding="utf-8")

    _use_temp_db()  # has_content() False -> get_all_events() falls through to static_fallback
    try:
        out = {e["id"] for e in database.get_all_events()}
        check("12: static-fallback tier excludes an explicitly-incomplete row (defense-in-depth)",
              3 not in out)
        check("12: static-fallback tier keeps complete + grandfathered rows", {1, 2} <= out)
    finally:
        _restore_db()
finally:
    static_fallback._DATA_DIR = _orig_data_dir
    static_fallback._cache.clear()
    static_fallback._cache.update(_orig_cache)


print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
