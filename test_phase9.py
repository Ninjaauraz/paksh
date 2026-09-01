"""
test_phase9.py - Paksh 9B: production content-path restoration.

Phase 9A proved CLASS A: the live production frontend at paksh.vercel.app was
unconditionally loading /static/api-base.js, which set window.PAKSH_API_BASE to
the stale (3-day-old) Render/Supabase mirror - causing apiGet()'s detectMode()
to resolve to "api" mode on every real page load, bypassing the correctly-fresh
static JSON path entirely. Root cause: commit 1317d21ace ("Cut over production
frontend to staging API", 2026-08-21) added static/api-base.js and an
unconditional <script> tag loading it in static/index.html's <head>.

The fix (Phase 9B) is deliberately minimal: delete static/api-base.js and its
<script> tag. apiGet()/detectMode()/the localStorage dev-override path in
static/app.jsx are left completely untouched - they are legitimate,
already-tested, dev-only capability, not the bug. The bug was the UNCONDITIONAL
PRODUCTION INJECTION, not the existence of API-mode code.

This suite behaviorally EXECUTES the real detectMode()/apiGet() logic (via
Node.js, extracted verbatim from the current static/app.jsx source - not a
hand-copied duplicate that could silently drift) under four scenarios: normal
production (no override, static fallback), Render/API unreachable (proving
independence), and both dev-override mechanisms (window.PAKSH_API_BASE set
explicitly, and the localStorage override) - to prove the distinction between
"capability preserved" and "no longer production-default" rather than just
asserting the function exists.

Run:  py test_phase9.py    (requires `node` on PATH; used only to execute the
                             real, unmodified JS logic under mocked fetch/window/
                             localStorage - no network calls, no browser)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# ============================================================ A: extract the REAL apiGet/detectMode block
print("=== extracting the real apiGet()/detectMode()/API_BASE block from static/app.jsx ===")
app_jsx = (ROOT / "static" / "app.jsx").read_text(encoding="utf-8")
START = "    const API_BASE = (typeof window!==\"undefined\""
END = "    async function loadAll(){"
start_i = app_jsx.index(START)
end_i = app_jsx.index(END, start_i)
JS_BLOCK = app_jsx[start_i:end_i]
check("0: extracted a non-trivial block containing detectMode/apiGet from the real source",
      "function detectMode" in JS_BLOCK and "async function apiGet" in JS_BLOCK and len(JS_BLOCK) > 400)


def run_node_scenario(window_api_base, localstorage_value, fetch_js):
    """Runs the REAL extracted JS block under Node with mocked window/localStorage/fetch,
    then calls detectMode() and apiGet('events'). Returns the parsed JSON result dict."""
    win_line = f'globalThis.window = {{PAKSH_API_BASE: {json.dumps(window_api_base)}}};' if window_api_base is not None \
        else 'globalThis.window = {};'
    ls_line = (f'globalThis.localStorage = {{getItem: (k) => k==="paksh_api_base" ? {json.dumps(localstorage_value)} : null}};'
               if localstorage_value is not None else
               'globalThis.localStorage = {getItem: (k) => null};')
    script = f"""
{win_line}
{ls_line}
globalThis.fetch = {fetch_js};

{JS_BLOCK}

(async () => {{
  try {{
    const mode = await detectMode();
    let events = null, eventsErr = null;
    try {{ events = await apiGet("events"); }} catch(e) {{ eventsErr = String(e); }}
    console.log(JSON.stringify({{mode, apiBaseUsed: API_BASE, events, eventsErr}}));
  }} catch (e) {{
    console.log(JSON.stringify({{fatal: String(e)}}));
  }}
}})();
"""
    r = subprocess.run(["node", "--input-type=module", "-e", script],
                        capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(f"node failed: {r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


# ============================================================ TEST 1: production injection absent (static check)
print("\n=== TEST 1: production HTML/export no longer injects PAKSH_API_BASE ===")
index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
check("1a: static/index.html (source template) has no api-base.js script tag",
      "api-base.js" not in index_html)
check("1b: static/index.html has no inline PAKSH_API_BASE assignment either",
      "PAKSH_API_BASE" not in index_html)
check("1c: the source file static/api-base.js no longer exists",
      not (ROOT / "static" / "api-base.js").exists())
check("1d: no file under static/ (source) still sets window.PAKSH_API_BASE unconditionally",
      not any("PAKSH_API_BASE =" in p.read_text(encoding="utf-8", errors="ignore")
              for p in (ROOT / "static").glob("*.html")))


# ============================================================ TEST 2: static production mode (real execution)
print("\n=== TEST 2: normal production (no override) resolves to static mode - REAL execution ===")
# Vercel's own vercel.json returns 404 for /api/* (Phase 8.5/9A finding) - simulate exactly that,
# and simulate /data/events.json?t=... succeeding, exactly as export_static.py actually produces.
fetch_vercel_like = """(async (url) => {
  if (String(url).includes("/api/")) return {ok: false, status: 404, headers: {get: () => "text/plain"}};
  if (String(url).startsWith("/data/events.json")) {
    return {ok: true, headers: {get: () => "application/json"}, json: async () => ({events: [{id: 1, title: "static-served"}]})};
  }
  return {ok: false, status: 404, headers: {get: () => "text/plain"}};
})"""
result = run_node_scenario(window_api_base=None, localstorage_value=None, fetch_js=fetch_vercel_like)
check("2a: detectMode() resolves to 'static' with no override and a 404ing /api/*",
      result.get("mode") == "static")
check("2b: apiGet('events') actually returned the static-file payload",
      result.get("events") == {"events": [{"id": 1, "title": "static-served"}]})
check("2c: API_BASE resolved to the empty string (no accidental base)",
      result.get("apiBaseUsed") == "")


# ============================================================ TEST 3: static content availability (real files)
print("\n=== TEST 3: production JSON files exist and are consumable ===")
for fname in ("events.json", "events-archive.json", "topics.json", "sources.json", "blindspots.json"):
    p = ROOT / "_site" / "data" / fname
    ok = p.exists()
    check(f"3: _site/data/{fname} exists", ok)
    if ok:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            check(f"3: _site/data/{fname} is valid, non-trivial JSON",
                  isinstance(data, dict) and len(data) > 0)
        except Exception as e:
            check(f"3: _site/data/{fname} is valid JSON (error: {e})", False)


# ============================================================ TEST 4: Render/API independence (real execution)
print("\n=== TEST 4: production content works even if the api probe target is fully unreachable ===")
fetch_render_down = """(async (url) => {
  if (String(url).includes("/api/")) { throw new TypeError("fetch failed: network unreachable"); }
  if (String(url).startsWith("/data/events.json")) {
    return {ok: true, headers: {get: () => "application/json"}, json: async () => ({events: [{id: 2, title: "still-works"}]})};
  }
  return {ok: false, status: 404, headers: {get: () => "text/plain"}};
})"""
result = run_node_scenario(window_api_base=None, localstorage_value=None, fetch_js=fetch_render_down)
check("4a: a hard network failure on the api probe does not throw out of detectMode()",
      result.get("mode") == "static")
check("4b: content still loads correctly from the static path despite the api target being down",
      result.get("events") == {"events": [{"id": 2, "title": "still-works"}]})
check("4c: no fatal/uncaught error surfaced",
      "fatal" not in result)


# ============================================================ TEST 5: dev-override capability preserved, distinctly
print("\n=== TEST 5: deliberate dev overrides still work; production default does not trigger them ===")
fetch_api_ok = """(async (url) => {
  if (String(url).includes("/api/topics")) {
    return {ok: true, headers: {get: () => "application/json"}, json: async () => ({topics: ["Politics"]})};
  }
  if (String(url).includes("/api/events")) {
    return {ok: true, headers: {get: () => "application/json"}, json: async () => ({events: [{id: 3, title: "api-mode"}]})};
  }
  return {ok: false, status: 404, headers: {get: () => "text/plain"}};
})"""
# 5a: explicit window.PAKSH_API_BASE (simulates a deliberately-reintroduced dev/staging injection)
result_window = run_node_scenario(window_api_base="https://example-dev-api.test",
                                   localstorage_value=None, fetch_js=fetch_api_ok)
check("5a: an EXPLICIT window.PAKSH_API_BASE still activates api mode (capability preserved)",
      result_window.get("mode") == "api" and result_window.get("apiBaseUsed") == "https://example-dev-api.test")

# 5b: localStorage-based dev override, independent of window.PAKSH_API_BASE
result_ls = run_node_scenario(window_api_base=None, localstorage_value="https://example-dev-api.test",
                               fetch_js=fetch_api_ok)
check("5b: the localStorage('paksh_api_base') dev override still activates api mode",
      result_ls.get("mode") == "api")

# 5c: with the REAL production-shaped fetch (Vercel's own /api/* 404s, per vercel.json - same
# mock as Test 2), confirm mode is 'static' precisely because nothing overrides API_BASE - i.e.
# the production-safe outcome depends only on Vercel's own routing, never on an injected global.
# (detectMode() correctly returns "api" whenever /api/topics genuinely responds - that's its
# intended auto-detection behavior, not something this fix should defeat; see Test 5a/5b.)
result_prod = run_node_scenario(window_api_base=None, localstorage_value=None, fetch_js=fetch_vercel_like)
check("5c: with NEITHER override set, and Vercel's real 404-on-/api/* behavior, mode is 'static' "
      "- the production-safe default depends only on Vercel's own routing, not an injected global",
      result_prod.get("mode") == "static")


# ============================================================ TEST 6: survives the real export
print("\n=== TEST 6: the fix survives a real export_static.py run (checked after the export below) ===")
site_index = (ROOT / "_site" / "index.html").read_text(encoding="utf-8")
check("6a: _site/index.html (deployed artifact) no longer references api-base.js",
      "api-base.js" not in site_index)
check("6b: _site/static/api-base.js (deployed artifact) no longer exists",
      not (ROOT / "_site" / "static" / "api-base.js").exists())
# Spot-check a few story pages too, since the same shared header is stamped into every one.
story_dir = ROOT / "_site" / "story"
story_files = sorted(story_dir.glob("*.html"))[:25] if story_dir.exists() else []
check("6c: found story pages to spot-check", len(story_files) > 0)
bad_story_pages = [f.name for f in story_files if "api-base.js" in f.read_text(encoding="utf-8", errors="ignore")]
check(f"6d: no api-base.js reference in {len(story_files)} sampled story pages (bad: {bad_story_pages[:5]})",
      len(bad_story_pages) == 0)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
