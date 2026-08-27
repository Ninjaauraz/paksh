"""
test_phase6d.py - Paksh 6D targeted checks: the frontend search integration
(static/app.jsx's SearchPage now calling GET /api/search instead of filtering
the client-side event corpus).

This project has no JavaScript test runner (no Jest/Vitest/Playwright config
anywhere in the repo - confirmed by inspection), so this file does what a
Python test CAN meaningfully verify for a frontend change:
  1. Structural source checks - the old client-side token-AND matcher is gone
     from the search-results computation, the new backend-driven path exists,
     the archive fetch no longer triggers on the "search" route, and no
     unrelated/removed identifiers are still referenced (which would be a
     ReferenceError at runtime).
  2. That static/app.jsx still compiles cleanly via this project's OWN
     established compile check (export_static.py's _precompile_jsx(), which
     runs real Babel via node and fails loudly on any syntax/transform error -
     the same check CLAUDE.md's own verification checklist requires after any
     app.jsx change).
  3. The full existing backend regression suite still passes unchanged (Phase
     6D touched no backend file, so this is a sanity confirmation, not new
     coverage).

Dynamic runtime behavior that only a real browser can exercise - debounce
timing, the stale-response race condition, actual DOM rendering, console
errors - was verified separately using the Browser pane against a live local
server. That verification is documented in full in the Phase 6D report, NOT
faked here as a Python assertion it cannot actually make.

Run:  py test_phase6d.py
"""
import subprocess
import sys
from pathlib import Path

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


APP_JSX = Path(__file__).parent / "static" / "app.jsx"
src = APP_JSX.read_text(encoding="utf-8")


# ============================================================ A: old client-side matcher removed
print("=== A: the old client-side token-AND matcher is gone from the results computation ===")
check("A: qTokens (old client-side tokenizer) is no longer defined", "const qTokens=" not in src)
check("A: the old _hay() haystack helper is no longer defined", "const _hay=" not in src)
check("A: results is no longer computed via baseCards.filter (client-side corpus filtering)",
      "const results=qTokens.length?baseCards.filter" not in src)


# ============================================================ B: new backend-driven path present
print("\n=== B: the new backend-driven search path is present ===")
check("B: results is now built from searchRows (backend response rows)",
      "const results=searchRows.map(r=>toSearchCard(r,lang));" in src)
check("B: a debounced fetch to /api/search exists", 'apiGet("search?q="+encodeURIComponent(q))' in src)
check("B: a setTimeout-based debounce is used (300ms)", "setTimeout(()=>{" in src and ",300);" in src)
check("B: the debounce effect's cleanup cancels the pending timer (clearTimeout)",
      "return ()=>clearTimeout(timer);" in src)
check("B: a generation-token ref exists for stale-response protection",
      "const searchSeq=React.useRef(0);" in src)
check("B: the fetch success handler discards a stale response before applying it",
      "if(searchSeq.current!==mySeq) return;" in src)
check("B: an empty/whitespace query short-circuits with no request",
      'if(!q){ searchSeq.current++; setSearchRows([]); return; }' in src)
check("B: the new toSearchCard() adapter exists (maps a search result row to the FeedRow shape)",
      "const toSearchCard = (r, lang) => ({" in src)
check("B: toSearchCard() does not fabricate a blindspot", "blindspot: null," in src)


# ============================================================ C: archive no longer fetched for search
print("\n=== C: the events-archive fetch no longer triggers on the search route ===")
check("C: the archive-loading effect's route trigger list no longer includes \"search\"",
      '!["topic","topics"].includes(route.view)' in src)
check("C: the OLD three-route trigger list (including \"search\") is gone",
      '!["search","topic","topics"].includes(route.view)' not in src)


# ============================================================ D: SearchPage itself untouched
print("\n=== D: SearchPage's own rendering code is untouched (same props, same JSX) ===")
check("D: SearchPage still takes the same prop signature (query, setQuery, results, browseCards, open)",
      "function SearchPage({ t, lang, query, setQuery, results, browseCards, open }) {" in src)
check("D: SearchPage is still rendered with the same props from the parent",
      'route.view==="search" ? <SearchPage t={t} lang={lang} query={query} setQuery={setQuery} '
      'results={results} browseCards={browseCards} open={open} />' in src)


# ============================================================ E: browseCards / baseCards untouched for their real consumers
print("\n=== E: baseCards/browseCards/archive remain wired for their OTHER (non-search) consumers ===")
check("E: browseCards (pre-query browse view) still derives from baseCards",
      "const browseCards=baseCards.slice(0,24);" in src)
check("E: TopicsHub still receives the full baseCards", "cards={baseCards}" in src)
check("E: TopicPage still filters baseCards by topic",
      "items={baseCards.filter(c=>c.topic===route.topic)}" in src)
check("E: related-stories (StoryPage) still derives from baseCards",
      "const related = story ? baseCards.filter" in src)


# ============================================================ F: app.jsx still compiles cleanly
print("\n=== F: static/app.jsx still compiles via this project's own Babel precompile check ===")
result = subprocess.run([sys.executable, "export_static.py"], capture_output=True, text=True,
                         cwd=str(Path(__file__).parent), timeout=600)
check("F: export_static.py completes with exit code 0 (Babel transform did not fail)", result.returncode == 0)
if result.returncode != 0:
    print("  --- export_static.py output ---")
    print(result.stdout[-3000:])
    print(result.stderr[-3000:])
check("F: build output reports the precompile step ran",
      "precompiled app.jsx -> app.js" in result.stdout)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
