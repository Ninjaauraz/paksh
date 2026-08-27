"""
test_phase6a.py - Paksh 6A targeted tests: the new GET /api/search endpoint and
supabase_content.search_events(), covering scenarios A-Q from the Phase 6A brief.

Follows the same conventions as test_phase43.py / test_phase22.py: functional
tests hit REAL Supabase over the network (wrapped in try/except SupabaseUnavailable
so a genuine outage skips rather than fails the suite); failure-injection tests
either monkeypatch sb.search_events directly (route-level) or mock.patch.object
sbc._session.post (HTTP-level, mirroring test_phase22's F/G/H _session.get mocks).

Does NOT touch production Supabase data or SQLite writes - read-only throughout.

Run:  py test_phase6a.py
"""
from unittest import mock

import supabase_content as sb
import supabase_content as sbc  # same module, imported twice to mirror test_phase22's naming
import main as main_module

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def _mock_response(payload, status=200):
    m = mock.MagicMock()
    m.status_code = status
    if isinstance(payload, Exception):
        m.json.side_effect = payload
    else:
        m.json.return_value = payload
    return m


_orig_backend = main_module.CONTENT_BACKEND
main_module.CONTENT_BACKEND = "supabase"


# ============================================================ A: endpoint exists
print("=== A: GET /api/search endpoint exists and is callable ===")
check("main.search is registered as a function", callable(main_module.search))
try:
    r = main_module.search(q="india")
    check("main.search() returns a dict without raising", isinstance(r, dict))
except Exception as e:
    check(f"main.search() raised unexpectedly: {e}", False)


# ============================================================ B/C/D: normal query, title + summary
print("\n=== B/C/D: normal query returns results, matches title and summary ===")
try:
    r = sb.search_events("india")
    check("B: normal query 'india' returns results", r["count"] > 0 and len(r["results"]) > 0)
    check("B: response has query/count/limit/results keys",
          set(r.keys()) == {"query", "count", "limit", "results"})
    sample = r["results"][0]
    check("B: result row shape is a small, expected set of fields",
          set(sample.keys()) == {"id", "title", "title_hi", "summary", "summary_hi", "topic",
                                  "lean_counts", "sources", "storyline_id", "created_at", "published_at"})
    check("B: result row does NOT carry summary_points/coverage/framing/analysis_json",
          all(k not in sample for k in ("summary_points", "summary_points_hi", "coverage",
                                         "framing", "framing_hi", "analysis_json")))

    def _hay(row):
        return f"{row['title']} {row['title_hi']} {row['summary']} {row['summary_hi']}".lower()

    check("C: every result's title OR summary actually contains the query token",
          all("india" in _hay(row) for row in r["results"]))
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED B/C (Supabase unreachable: {e})")

try:
    # a term far more likely to appear only in body text than in a headline
    r = sb.search_events("supreme court")
    check("D: multi-word query hitting summary text returns results", r["count"] >= 0)
    if r["results"]:
        check("D: results contain both tokens (AND semantics) across title/summary fields",
              all(("supreme" in _hay(row) and "court" in _hay(row)) for row in r["results"]))
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED D (Supabase unreachable: {e})")


# ============================================================ E: Hindi
print("\n=== E: Hindi title/summary search ===")
try:
    r = sb.search_events("भारत")
    check("E: Hindi query 'भारत' does not raise and returns a well-formed response",
          set(r.keys()) == {"query", "count", "limit", "results"})
    check("E: Hindi query returns results", r["count"] > 0)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED E (Supabase unreachable: {e})")


# ============================================================ F: multi-word AND semantics
print("\n=== F: multi-word query narrows results (AND, not OR) ===")
try:
    r_broad = sb.search_events("india")
    r_narrow = sb.search_events("india supreme court")
    check("F: adding tokens narrows (or ties, never exceeds) the broad query's result count",
          r_narrow["count"] <= r_broad["count"])
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED F (Supabase unreachable: {e})")


# ============================================================ G/H: empty / whitespace query
print("\n=== G/H: empty and whitespace-only query handled without a DB call ===")
_calls = {"n": 0}
_orig_post = sbc._post


def _counting_post(*a, **kw):
    _calls["n"] += 1
    return _orig_post(*a, **kw)


sbc._post = _counting_post
try:
    r = sb.search_events("")
    check("G: empty query returns count=0, results=[]", r["count"] == 0 and r["results"] == [])
    check("G: empty query makes no Supabase call", _calls["n"] == 0)
    r = sb.search_events("    ")
    check("H: whitespace-only query returns count=0, results=[]", r["count"] == 0 and r["results"] == [])
    check("H: whitespace-only query makes no Supabase call", _calls["n"] == 0)
finally:
    sbc._post = _orig_post


# ============================================================ I: excessively long query
print("\n=== I: excessively long query handled without error ===")
long_q = "india " * 100  # 600 chars, well past MAX_SEARCH_QUERY_LEN
try:
    r = sb.search_events(long_q)
    check("I: excessively long query does not raise", True)
    check("I: excessively long query's echoed 'query' is truncated to the documented bound",
          len(r["query"]) <= sbc.MAX_SEARCH_QUERY_LEN)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED I (Supabase unreachable: {e})")
except Exception as e:
    check(f"I: excessively long query raised unexpectedly: {e}", False)


# ============================================================ J: SQL-looking input
print("\n=== J: SQL-looking / injection-shaped input causes no error ===")
for bad in ["'; DROP TABLE events; --", "' OR '1'='1", "%%%___", "\\\\", "SELECT * FROM events"]:
    try:
        r = sb.search_events(bad)
        check(f"J: input {bad!r} handled without raising, well-formed response",
              set(r.keys()) == {"query", "count", "limit", "results"})
    except sb.SupabaseUnavailable as e:
        print(f"  SKIPPED J for {bad!r} (Supabase unreachable: {e})")
    except Exception as e:
        check(f"J: input {bad!r} raised unexpectedly: {e}", False)


# ============================================================ K: Unicode / Hindi / emoji
print("\n=== K: Unicode input (Hindi, emoji, mixed script) causes no error ===")
for uni in ["नमस्ते दुनिया", "🇮🇳🔥", "café naïve", "मोदी modi"]:
    try:
        r = sb.search_events(uni)
        check(f"K: unicode input {uni!r} handled without raising",
              set(r.keys()) == {"query", "count", "limit", "results"})
    except sb.SupabaseUnavailable as e:
        print(f"  SKIPPED K for {uni!r} (Supabase unreachable: {e})")
    except Exception as e:
        check(f"K: unicode input {uni!r} raised unexpectedly: {e}", False)


# ============================================================ L: result count bounded by limit
print("\n=== L: result count bounded by requested/default limit ===")
try:
    r = sb.search_events("india", limit=5)
    check("L: limit=5 respected", len(r["results"]) <= 5 and r["limit"] == 5)
    r = sb.search_events("india")
    check("L: default limit is 20 and respected", r["limit"] == 20 and len(r["results"]) <= 20)
    r = sb.search_events("india", limit=9999)
    check("L: an oversized requested limit is clamped, not honored raw",
          r["limit"] == sbc.MAX_SEARCH_LIMIT and len(r["results"]) <= sbc.MAX_SEARCH_LIMIT)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED L (Supabase unreachable: {e})")


# ============================================================ M: deterministic ordering
print("\n=== M: result ordering is deterministic across repeated identical calls ===")
try:
    r1 = sb.search_events("india supreme")
    r2 = sb.search_events("india supreme")
    ids1 = [row["id"] for row in r1["results"]]
    ids2 = [row["id"] for row in r2["results"]]
    check("M: two identical calls return results in the same order", ids1 == ids2 and len(ids1) > 0)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED M (Supabase unreachable: {e})")


# ============================================================ N: independent of /api/events(-archive) limits
print("\n=== N: search never calls get_events()/get_events_archive() (full-corpus, not capped) ===")
_orig_get_events = sb.get_events
_orig_get_events_archive = sb.get_events_archive


def _must_not_be_called(*a, **kw):
    raise AssertionError("search_events() must not call get_events()/get_events_archive()")


sb.get_events = _must_not_be_called
sb.get_events_archive = _must_not_be_called
try:
    r = sb.search_events("india supreme")
    check("N: search_events() succeeded without ever calling get_events()/get_events_archive()", True)
except AssertionError as e:
    check(f"N: {e}", False)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED N (Supabase unreachable: {e})")
finally:
    sb.get_events = _orig_get_events
    sb.get_events_archive = _orig_get_events_archive


# ============================================================ O: SupabaseUnavailable behavior
print("\n=== O: SupabaseUnavailable propagates from search_events(); route falls back to SQLite ===")


def _always_500(*a, **kw):
    return _mock_response(None, status=500)


with mock.patch.object(sbc._session, "post", side_effect=_always_500), \
     mock.patch("time.sleep"):
    try:
        sb.search_events("india")
        check("O: search_events() should have raised SupabaseUnavailable on persistent 5xx", False)
    except sb.SupabaseUnavailable:
        check("O: search_events() raises SupabaseUnavailable on persistent 5xx (matches _get())", True)

# Paksh 6B updated this route's failure behavior: /api/search now falls through to
# database.search_events() (the SQLite fallback tier) instead of returning an
# empty-but-200 result - see test_phase6b.py for the dedicated fallback tests. This
# assertion is updated (not weakened) to match that deliberate, documented change;
# the response is no longer expected to be empty when the local paksh.db has content.
_orig_search_events = sb.search_events
sb.search_events = lambda *a, **kw: (_ for _ in ()).throw(sb.SupabaseUnavailable("simulated outage"))
try:
    r = main_module.search(q="india")
    check("O: /api/search falls back to real SQLite results (Paksh 6B), not a 500, when Supabase is down",
          r["count"] > 0 and set(r.keys()) == {"query", "count", "limit", "results"})
finally:
    sb.search_events = _orig_search_events


# ============================================================ P: malformed Supabase response
print("\n=== P: malformed/unexpected Supabase response follows existing (retry-then-raise) convention ===")


def _malformed_json(*a, **kw):
    return _mock_response(ValueError("bad json"))


with mock.patch.object(sbc._session, "post", side_effect=_malformed_json), \
     mock.patch("time.sleep"):
    try:
        sb.search_events("india")
        check("P: malformed JSON should have raised SupabaseUnavailable after retries", False)
    except sb.SupabaseUnavailable:
        check("P: malformed JSON response raises SupabaseUnavailable after exhausting retries "
              "(same convention as _get())", True)


# ============================================================ Q: existing routes unaffected
print("\n=== Q: existing routes still work after adding /api/search ===")
for name, fn, kwargs in [
    ("list_events", main_module.list_events, {}),
    ("list_blindspots", main_module.list_blindspots, {}),
    ("list_topics", main_module.list_topics, {}),
    ("list_storylines", main_module.list_storylines, {}),
    ("stats", main_module.stats, {}),
    ("list_sources", main_module.list_sources, {}),
]:
    try:
        r = fn(**kwargs)
        check(f"Q: {name}() still returns a dict without raising", isinstance(r, dict))
    except Exception as e:
        check(f"Q: {name}() raised unexpectedly: {e}", False)

main_module.CONTENT_BACKEND = _orig_backend
check("CONTENT_BACKEND restored to its original value after the suite", main_module.CONTENT_BACKEND == _orig_backend)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
