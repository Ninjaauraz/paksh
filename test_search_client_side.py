"""
test_search_client_side.py - search as it actually works today: CLIENT-SIDE, over static data.

Replaces test_phase6d.py. That file pinned the Phase 6D design (the search box calling a server
GET /api/search). Phase 18B deliberately reversed it - Paksh is a static export with no server to ask, and
/api/search (and the Supabase search RPC) are retired - so its assertions described code that no longer
exists. Its fifth section also ran the entire export_static.py (rebuilding _site) as a "compile check".
This file tests the current design instead:

  A. no request to a server search endpoint exists in the app
  B. the matcher: AND across whitespace tokens, case-insensitive, over BOTH languages' title + summary
     - checked by executing the app's REAL matcher code (extracted from static/app.jsx) in Node
  C. debounce (300 ms) with timer cleanup, and the pending/browsing/loading/error/ready status states
  D. the archive is fetched lazily for search, and a fetch failure is surfaced (not shown as "no results")
  E. SearchPage is wired to searchStatus
  F. app.jsx compiles with the project's own Babel, into a TEMP file (no _site side effects)

Needs `node` for B and F (skipped with a clear message if it is missing, never silently passed).

Run:  py test_search_client_side.py
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
FAILURES = []
SKIPPED = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


src = (ROOT / "static" / "app.jsx").read_text(encoding="utf-8")
NODE = shutil.which("node")

print("=== A: no server search endpoint is used ===")
check("A1: the app never asks apiGet() for a 'search' resource", not re.search(r'apiGet\(\s*["\']search', src))
check("A2: no fetch()/URL string targets /api/search",
      not re.search(r'(fetch\(|apiGet\(|API_BASE\s*\+)[^;\n]*api/search', src))
check("A3: the old server-driven result plumbing is gone (no stale-response token, no searchRows state setter, "
      "no toSearchCard adapter DEFINITION - a comment may still mention it)",
      "searchSeq" not in src and "setSearchRows" not in src
      and not re.search(r"(const|function)\s+toSearchCard", src))

print("\n=== B: the matcher (the app's real code, executed in Node) ===")
m = re.search(r"const searchRows = useMemo\(\(\)=>\{.*?\},\[searchStatus,debouncedQuery,allEvents,lang\]\);", src, re.S)
check("B0: the matcher block is present in app.jsx", m is not None)
EVENTS = [
    {"id": 1, "title": "Election Commission announces dates", "title_hi": "चुनाव आयोग ने तारीखों की घोषणा की", "summary": "Voting will be held in phases.", "summary_hi": "मतदान चरणों में होगा।"},
    {"id": 2, "title": "Budget raises tax slabs", "title_hi": "बजट में कर स्लैब बढ़े", "summary": "The finance minister presented the budget.", "summary_hi": ""},
    {"id": 3, "title": "Monsoon delays", "title_hi": None, "summary": "Rainfall is below average; tax on fuel unchanged.", "summary_hi": None},
]


def run_matcher(query, status="ready"):
    js = ("const useMemo=(f)=>f(); const toCard=(e,l)=>e.id; const lang='en';"
          "const searchStatus=%s; const debouncedQuery=%s; const allEvents=%s;" % (json.dumps(status), json.dumps(query), json.dumps(EVENTS))
          + m.group(0) + "console.log(JSON.stringify(searchRows));")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.returncode == 0 else ("ERR", r.stderr[-200:])


if NODE and m:
    check("B1: a single word matches case-insensitively", run_matcher("ELECTION") == [1])
    check("B2: several words are ANDed - every token must appear (budget + tax -> only #2)", run_matcher("budget tax") == [2])
    check("B3: a token may hit the summary, not just the title ('rainfall' -> #3)", run_matcher("rainfall") == [3])
    check("B4: Hindi is matched in the Hindi fields ('चुनाव' -> #1)", run_matcher("चुनाव") == [1])
    check("B5: the English UI still finds a Hindi-only match and vice versa ('मतदान' -> #1)", run_matcher("मतदान") == [1])
    check("B6: no match -> empty list", run_matcher("zzzqqqxx") == [])
    check("B7: regex/HTML metacharacters are treated as plain text and cannot crash the matcher",
          run_matcher("((<script>alert(1)</script>[*") == [] and run_matcher("a.*") == [])
    check("B8: nothing is matched until the status is 'ready' (e.g. still loading the archive)",
          run_matcher("election", status="loading") == [] and run_matcher("election", status="pending") == [])
    check("B9: events with null/empty fields are handled (no exception)", run_matcher("delays") == [3])
else:
    SKIPPED.append("B (node or matcher block missing)")
    print("  SKIPPED B1-B9: node not found on PATH" if not NODE else "  B0 failed above")

print("\n=== C: debounce and status states ===")
check("C1: the query is debounced by 300 ms", re.search(r"setTimeout\(\(\)=>setDebouncedQuery\(.*?\),\s*300\)", src, re.S) is not None)
check("C2: the pending timer is cancelled on the next keystroke / unmount",
      re.search(r"setTimeout\(\(\)=>setDebouncedQuery[^\n]*\n[^\n]*return \(\)=>clearTimeout\(timer\)", src) is not None)
check("C3: 'pending' covers the debounce gap (no flash of the browse feed)",
      'const pending = trimmedQuery!=="" && trimmedQuery!==debouncedQuery;' in src)
for st in ("pending", "browsing", "error", "loading", "ready"):
    check(f'C4: searchStatus can be "{st}"', f'"{st}"' in src[src.index("const searchStatus"):src.index("const searchRows")])

print("\n=== D: the archive is what search runs over ===")
check("D1: the archive loads for the search route once there is a query",
      'route.view==="search" && (query||"").trim()' in src)
check("D2: it is the static archive file that is fetched", 'apiGet("events-archive")' in src)
check("D3: an archive failure becomes an explicit 'error' state, not a silent zero-result",
      'archive==="error" ? "error"' in src and 'setArchive("error")' in src)

print("\n=== E: SearchPage is driven by searchStatus ===")
check("E1: SearchPage takes searchStatus", "function SearchPage({ t, lang, query, setQuery, results, browseCards, searchStatus, open })" in src)
check("E2: it renders the pending / loading / error states",
      all(f'searchStatus==="{s}"' in src for s in ("pending", "loading", "error")))
check("E3: the parent passes searchStatus in", "searchStatus={searchStatus}" in src)

print("\n=== F: app.jsx compiles with the project's Babel (into a temp file, _site untouched) ===")
babel = ROOT / "vendor" / "babel.min.js"
if NODE and babel.exists():
    out = Path(tempfile.mkdtemp(prefix="pk_babel_")) / "app.js"
    script = ("const B=require(process.argv[1]);const fs=require('fs');"
              "fs.writeFileSync(process.argv[3],B.transform(fs.readFileSync(process.argv[2],'utf8'),{presets:['react'],compact:false}).code);")
    r = subprocess.run([NODE, "-e", script, str(babel), str(ROOT / "static" / "app.jsx"), str(out)], capture_output=True, text=True, timeout=300)
    check("F1: the Babel transform succeeds", r.returncode == 0 and out.exists() and out.stat().st_size > 100_000)
    if r.returncode != 0:
        print(r.stderr[-1500:])
    js = out.read_text(encoding="utf-8") if out.exists() else ""
    check("F2: the compiled bundle contains no JSX left over and is plain JS", "React.createElement" in js and "</" not in js.split("createElement")[0][:200])
else:
    SKIPPED.append("F (node or vendor/babel.min.js missing)")
    print("  SKIPPED F: node or vendor/babel.min.js not available")

print(f"\n{'=' * 60}")
if SKIPPED:
    print("SKIPPED sections (not counted as passed): " + "; ".join(SKIPPED))
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED" + (" (with skipped sections)" if SKIPPED else ""))
