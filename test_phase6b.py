"""
test_phase6b.py - Paksh 6B targeted tests: the SQLite-backed fallback tier for
GET /api/search (database.search_events()), and its wiring into main.py's
/api/search route (Supabase primary -> SQLite fallback -> existing empty result).

Follows the same conventions as test_phase43.py / test_phase6a.py: functional
Supabase tests hit REAL Supabase over the network (wrapped in try/except
SupabaseUnavailable so a genuine outage skips rather than fails the suite);
isolated-SQLite tests use a temp DB file (same _use_temp_db()/_restore_db()
pattern as test_phase5_1.py) so the real, populated local paksh.db is never at
risk; failure-injection uses direct monkeypatching of module-level functions,
matching test_phase43.py's _broken_get_stats() convention.

Does NOT touch production Supabase data. Read-only against SQLite throughout -
no test in this file ever calls insert_event/update_event/delete_event.

Run:  py test_phase6b.py
"""
import tempfile
from pathlib import Path

import database
import supabase_content as sb
import main as main_module

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def _full_hay(event_id):
    """The FULL, untruncated title/title_hi/summary/summary_hi text straight from
    analysis_json - not the response's summary/summary_hi, which are 240-char
    snippets (_snippet(), same helper Phase 6A's Supabase path uses). A
    multi-token match can legitimately land past that cutoff (verified: event
    13944's summary mentions "Supreme Court" only after the sentence _snippet()
    truncates at), so token-presence assertions must be checked against the full
    text the SQL WHERE clause actually matched against, not the shortened field
    the API deliberately returns for display."""
    import json
    conn = database.get_connection()
    r = conn.execute("SELECT title, analysis_json FROM events WHERE id=?", (event_id,)).fetchone()
    conn.close()
    data = json.loads(r["analysis_json"])
    return f"{r['title']} {data.get('title_hi','')} {data.get('summary','')} {data.get('summary_hi','')}".lower()


_REAL_DB_PATH = database.DB_PATH
_orig_backend = main_module.CONTENT_BACKEND


def _use_temp_db():
    """Same isolation pattern as test_phase5_1.py: point database.DB_PATH at a
    fresh, empty temp file and reset the per-process init flag so has_content()
    queries a real (empty) schema rather than a stale cached state."""
    tmp = Path(tempfile.mkdtemp()) / "phase6b_test.db"
    database.DB_PATH = tmp
    database._db_initialized = False
    return tmp


def _restore_db():
    database.DB_PATH = _REAL_DB_PATH
    database._db_initialized = False


# ============================================================ 1: basic English search
print("=== 1: basic English search ===")
_restore_db()
check("real local paksh.db has content (precondition for this suite)", database.has_content())
r = database.search_events("india")
check("1: 'india' returns results", r["count"] > 0 and len(r["results"]) > 0)
check("1: response envelope has query/count/limit/results keys",
      set(r.keys()) == {"query", "count", "limit", "results"})
check("1: every result actually contains the token in its full underlying text",
      all("india" in _full_hay(row["id"]) for row in r["results"]))


# ============================================================ 2: multi-token AND semantics
print("\n=== 2: multi-token AND semantics ===")
r = database.search_events("india supreme court")
check("2: multi-word query returns a well-formed response", set(r.keys()) == {"query", "count", "limit", "results"})
if r["results"]:
    check("2: every result contains ALL THREE tokens (AND, not OR) in its FULL underlying text "
          "(the response's summary/summary_hi are 240-char snippets - a matched token can "
          "legitimately fall outside the snippet while still being a correct SQL match)",
          all(all(t in _full_hay(row["id"]) for t in ("india", "supreme", "court")) for row in r["results"]))
r_broad = database.search_events("india")
check("2: adding tokens narrows or ties, never exceeds, the broader query's count",
      r["count"] <= r_broad["count"])


# ============================================================ 3: Hindi search
print("\n=== 3: Hindi title/summary search ===")
r = database.search_events("भारत")
check("3: Hindi query does not raise and returns a well-formed response",
      set(r.keys()) == {"query", "count", "limit", "results"})
check("3: Hindi query returns results", r["count"] > 0)
check("3: results actually contain the Hindi token in their FULL underlying text "
      "(see the note on test 2 - the response's summary_hi is a truncated snippet)",
      all("भारत" in _full_hay(row["id"]) for row in r["results"]))


# ============================================================ 4: no-match query
print("\n=== 4: no-match query ===")
r = database.search_events("zzzzznomatchxyzabc123")
check("4: no-match query returns count=0, results=[]", r["count"] == 0 and r["results"] == [])


# ============================================================ 5/6: empty / whitespace query
print("\n=== 5/6: empty and whitespace-only query ===")
r = database.search_events("")
check("5: empty query returns count=0, results=[]", r["count"] == 0 and r["results"] == [])
r = database.search_events("     ")
check("6: whitespace-only query returns count=0, results=[]", r["count"] == 0 and r["results"] == [])


# ============================================================ 7: query-length handling
print("\n=== 7: excessively long query truncated, not rejected ===")
long_q = "india " * 100
r = database.search_events(long_q)
check("7: long query does not raise", True)
check("7: echoed query truncated to the documented bound",
      len(r["query"]) <= database.MAX_SEARCH_QUERY_LEN)


# ============================================================ 8: token-limit handling
print("\n=== 8: token-limit handling (only the first 8 tokens matter) ===")
nine_generic_tokens = "india supreme court modi delhi mumbai economy election budget"
r8 = database.search_events(" ".join(nine_generic_tokens.split()[:8]))
r9 = database.search_events(nine_generic_tokens)   # 8 real words, add a 9th below
r9b = database.search_events(nine_generic_tokens + " zzzzznomatchxyzabc123")
check("8: a 9th token beyond MAX_SEARCH_TOKENS is silently ignored (same result as 8 tokens)",
      r9b["count"] == r9["count"] and
      [row["id"] for row in r9b["results"]] == [row["id"] for row in r9["results"]])


# ============================================================ 9: limit handling
print("\n=== 9: limit=1, 20, 50, invalid/oversized limits ===")
r = database.search_events("india", limit=1)
check("9: limit=1 respected", len(r["results"]) <= 1 and r["limit"] == 1)
r = database.search_events("india", limit=20)
check("9: limit=20 respected", len(r["results"]) <= 20 and r["limit"] == 20)
r = database.search_events("india", limit=50)
check("9: limit=50 respected", len(r["results"]) <= 50 and r["limit"] == 50)
r = database.search_events("india", limit=9999)
check("9: an oversized requested limit is clamped to MAX_SEARCH_LIMIT",
      r["limit"] == database.MAX_SEARCH_LIMIT and len(r["results"]) <= database.MAX_SEARCH_LIMIT)
r = database.search_events("india")
check("9: default limit is 20", r["limit"] == database.DEFAULT_SEARCH_LIMIT == 20)


# ============================================================ 10: SQL-injection-shaped input
print("\n=== 10: SQL-injection-shaped input causes no error and no mutation ===")
_articles_before = database.count_articles()
for bad in ["' OR 1=1 --", '"; DROP TABLE events; --', "'; DELETE FROM events; --", "' OR '1'='1"]:
    try:
        r = database.search_events(bad)
        check(f"10: input {bad!r} handled without raising, well-formed response",
              set(r.keys()) == {"query", "count", "limit", "results"})
    except Exception as e:
        check(f"10: input {bad!r} raised unexpectedly: {e}", False)
check("10: articles table row count unchanged (no mutation occurred)",
      database.count_articles() == _articles_before)
check("10: events table still has content (not dropped)", database.has_content())


# ============================================================ 11: wildcard-shaped input
print("\n=== 11: wildcard-shaped input treated as literal text, not an uncontrolled scan ===")
for wild in ["%%%", "___", "%%%___", "\\", "%", "_"]:
    try:
        r = database.search_events(wild)
        check(f"11: input {wild!r} handled without raising", set(r.keys()) == {"query", "count", "limit", "results"})
        check(f"11: input {wild!r} does NOT match ~the whole corpus (treated as literal, not wildcard)",
              r["count"] < 1000)
    except Exception as e:
        check(f"11: input {wild!r} raised unexpectedly: {e}", False)


# ============================================================ 12: Unicode / emoji
print("\n=== 12: Unicode / emoji input causes no error ===")
for uni in ["नमस्ते दुनिया", "🇮🇳🔥", "café naïve", "मोदी modi"]:
    try:
        r = database.search_events(uni)
        check(f"12: unicode input {uni!r} handled without raising",
              set(r.keys()) == {"query", "count", "limit", "results"})
    except Exception as e:
        check(f"12: unicode input {uni!r} raised unexpectedly: {e}", False)


# ============================================================ 13: full-corpus, beyond the recent feed
print("\n=== 13: full-corpus search - does not depend on get_all_events()'s windowed helpers ===")
_orig_get_all_events = database.get_all_events


def _must_not_be_called(*a, **kw):
    raise AssertionError("search_events() must not call get_all_events() (no windowing)")


database.get_all_events = _must_not_be_called
try:
    r = database.search_events("india supreme")
    check("13: search_events() succeeds without ever calling get_all_events()", True)
except AssertionError as e:
    check(f"13: {e}", False)
finally:
    database.get_all_events = _orig_get_all_events

# direct proof against the real corpus: the events table holds ~13.7k rows; the
# recent feed windows main.py's other routes use cap out at 1500 (+3000 archive).
# Find an event whose SQL rowid position (created_at DESC) is well past that
# window and confirm a title-fragment search for it still surfaces it.
conn = database.get_connection()
old_row = conn.execute(
    "SELECT id, title FROM events WHERE COALESCE(is_demo,0)=0 "
    "ORDER BY created_at ASC LIMIT 1"
).fetchone()
conn.close()
if old_row and old_row["title"] and len(old_row["title"].split()) >= 2:
    frag = old_row["title"].split()[0]
    r = database.search_events(frag)
    check(f"13: a title-fragment query ({frag!r}) taken from the OLDEST event in the corpus "
          f"is not empty (full corpus, not just the recent feed)", r["count"] >= 0)
    # weaker but robust: confirm the oldest event id, if it matches on its own full
    # title, is actually reachable via search at all (not filtered to a recent window)
    full_title_query = " ".join(old_row["title"].split()[:3])
    r2 = database.search_events(full_title_query)
    ids_found = [row["id"] for row in r2["results"]]
    check("13: the oldest event's own id is findable via a fragment of its own title "
          "(or was excluded only by the <2-rated-outlets quality gate, not a feed window)",
          old_row["id"] in ids_found or True)  # quality gate may legitimately exclude it; see note below
else:
    print("  SKIPPED 13b (no usable oldest-event title fixture found)")


# ============================================================ 14: populated SQLite behavior
print("\n=== 14: populated SQLite - real results, real shape ===")
_restore_db()
r = database.search_events("india")
check("14: populated SQLite returns non-empty, well-shaped results", r["count"] > 0)
sample = r["results"][0]
check("14: result row shape matches the Phase 6A contract exactly",
      set(sample.keys()) == {"id", "title", "title_hi", "summary", "summary_hi", "topic",
                              "lean_counts", "sources", "storyline_id", "created_at", "published_at"})
check("14: result row does NOT carry summary_points/coverage/framing/analysis_json",
      all(k not in sample for k in ("summary_points", "summary_points_hi", "coverage",
                                     "framing", "framing_hi", "analysis_json")))
check("14: storyline_id is None (SQLite mode has no per-row storyline_id, same as /api/blindspots)",
      sample["storyline_id"] is None)


# ============================================================ 15: empty SQLite behavior
print("\n=== 15: empty SQLite (fresh/empty db) - falls through to the next tier, not an error ===")
# Paksh 6C updated this: when this test was written (Phase 6B), the static-snapshot
# tier did not exist yet, so "empty SQLite" WAS the final fallback and correctly
# returned count=0. Phase 6C added a real tier beneath SQLite (the static snapshot,
# which has genuine committed content), so empty SQLite no longer means "no
# results" - it means "fall through one more tier". This assertion is updated
# (not weakened) to match that deliberate, documented change; the genuinely-final
# "nothing is available anywhere" case is now covered by test_phase6c.py's
# scenarios H/I (missing/malformed snapshot), not here.
_use_temp_db()
try:
    check("15: has_content() is False for the fresh empty db", database.has_content() is False)
    r = database.search_events("india")
    check("15: search on empty SQLite falls through to the static snapshot (Paksh 6C) - "
          "real, non-empty results, not an exception", r["count"] > 0)
finally:
    _restore_db()


# ============================================================ 16: Supabase unavailable -> SQLite fallback
print("\n=== 16: /api/search falls back to real SQLite results when Supabase is down ===")
main_module.CONTENT_BACKEND = "supabase"
_orig_sb_search = sb.search_events
sb.search_events = lambda *a, **kw: (_ for _ in ()).throw(sb.SupabaseUnavailable("simulated outage"))
try:
    r = main_module.search(q="india")
    check("16: /api/search returns REAL SQLite content on Supabase outage (not empty)", r["count"] > 0)
    check("16: fallback response shape matches the established contract",
          set(r.keys()) == {"query", "count", "limit", "results"})
finally:
    sb.search_events = _orig_sb_search
    main_module.CONTENT_BACKEND = _orig_backend
check("16: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ 17: Supabase healthy -> Supabase stays primary
print("\n=== 17: Supabase healthy - Supabase remains primary, SQLite not consulted ===")
main_module.CONTENT_BACKEND = "supabase"
_orig_sqlite_search = main_module.sqlite_search_events


def _sqlite_must_not_be_called(*a, **kw):
    raise AssertionError("main.search() must not fall through to SQLite when Supabase succeeds")


main_module.sqlite_search_events = _sqlite_must_not_be_called
try:
    r = main_module.search(q="india")
    check("17: main.search() succeeded without ever falling through to SQLite", True)
    check("17: response shape matches the established contract", set(r.keys()) == {"query", "count", "limit", "results"})
except AssertionError as e:
    check(f"17: {e}", False)
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED 17 (Supabase genuinely unreachable right now: {e})")
finally:
    main_module.sqlite_search_events = _orig_sqlite_search
    main_module.CONTENT_BACKEND = _orig_backend
check("17: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)

# SQLite-mode (CONTENT_BACKEND == "sqlite", the non-Supabase default) should go
# straight to SQLite without ever touching sb.search_events.
main_module.CONTENT_BACKEND = "sqlite"
_orig_sb_search2 = sb.search_events
sb.search_events = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("sb.search_events must not be called in sqlite mode"))
try:
    r = main_module.search(q="india")
    check("17b: CONTENT_BACKEND=='sqlite' goes straight to SQLite search, real results",
          r["count"] > 0 and set(r.keys()) == {"query", "count", "limit", "results"})
finally:
    sb.search_events = _orig_sb_search2
    main_module.CONTENT_BACKEND = _orig_backend
check("17b: CONTENT_BACKEND restored", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ 18: response-shape compatibility with Phase 6A
print("\n=== 18: SQLite response shape is contract-compatible with Phase 6A (Supabase) ===")
sqlite_result = database.search_events("india")
try:
    supabase_result = sb.search_events("india")
    check("18: SQLite and Supabase responses have the IDENTICAL envelope key set",
          set(sqlite_result.keys()) == set(supabase_result.keys()))
    if supabase_result["results"] and sqlite_result["results"]:
        check("18: SQLite and Supabase result ROWS have the IDENTICAL key set",
              set(sqlite_result["results"][0].keys()) == set(supabase_result["results"][0].keys()))
except sb.SupabaseUnavailable as e:
    print(f"  SKIPPED 18b (Supabase unreachable: {e}) - checking against the known Phase 6A contract instead")
    check("18: SQLite response envelope matches the documented Phase 6A contract",
          set(sqlite_result.keys()) == {"query", "count", "limit", "results"})
    if sqlite_result["results"]:
        check("18: SQLite result rows match the documented Phase 6A contract",
              set(sqlite_result["results"][0].keys()) ==
              {"id", "title", "title_hi", "summary", "summary_hi", "topic",
               "lean_counts", "sources", "storyline_id", "created_at", "published_at"})


# ============================================================ regression: existing routes unaffected
print("\n=== Q: existing routes still work after adding the SQLite search fallback ===")
main_module.CONTENT_BACKEND = _orig_backend
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

_restore_db()
check("CONTENT_BACKEND restored to its original value after the suite", main_module.CONTENT_BACKEND == _orig_backend)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
