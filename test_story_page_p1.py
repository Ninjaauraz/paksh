"""
test_story_page_p1.py - Story Page maturity P1 fixes (static/app.jsx, StoryPage component):
thin-coverage signal, Blindspot explanation, related-stories reordering.

Paksh has no npm build step and no JS test runner, so - matching the existing convention in
test_mobile_share.py/test_search_client_side.py/test_onboarding_personalization.py - this
inspects the real app.jsx SOURCE for the exact structure each fix requires, behaviorally
EXECUTES the real `related` composition logic via Node (extracted verbatim, not a fake
reimplementation), and compiles the whole file with the project's own vendored Babel into a
TEMP file (no _site side effects) as a final syntax-validity check.

What this pins:
  1. thin-coverage note: appears only when total<=3 (coverage DEPTH, reusing the existing
     `total` outlet count already shown in metaLine - no new field, no confidence language)
  2. Blindspot explanation: reuses BlindspotPage's own methodNote text VERBATIM (both extracted
     from source and compared, so a future edit to one that misses the other fails loudly),
     renders only when story.blindspot is truthy
  3. related stories: storyline siblings first, then story_context.historical_event, then the
     pre-existing topic filter fills remaining slots - capped at 6, no duplicates, never self,
     silently skips any id not already loaded client-side (no new fetch/query)
  4. app.jsx still compiles

Run:  py test_story_page_p1.py
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


src = (ROOT / "static" / "app.jsx").read_text(encoding="utf-8")
NODE = shutil.which("node")

print("=== 1: thin-coverage signal ===")
check("1a: UI.thinCoverage exists with both EN and HI",
      re.search(r'thinCoverage:\{en:"[^"]+",\s*hi:"[^"]+"\}', src) is not None)
check("1b: wording is coverage-DEPTH language ('Early coverage'), not a confidence claim",
      'thinCoverage:{en:"Early coverage"' in src
      and not any(bad in src[src.find("thinCoverage"):src.find("thinCoverage") + 80].lower()
                   for bad in ("uncertain", "unreliable", "unverified", "doubtful", "questionable")))
isthin = re.search(r"const isThinCoverage\s*=\s*total\s*<=\s*3\s*;", src)
check("1c: gated on the EXISTING `total` outlet count (same number already shown in metaLine), "
      "threshold <=3, no new field introduced", isthin is not None)
check("1d: the note is rendered in the meta line via ui(\"thinCoverage\",lang), same visual "
      "register as the existing AUTO tag (uppercase mono span), not a new component",
      re.search(r'\{isThinCoverage && <> · <span className="uppercase">\{ui\("thinCoverage",lang\)\}</span></>\}', src) is not None)
check("1e: total_sources/story.sources itself is not modified anywhere near this change "
      "(no reassignment of `total`)",
      not re.search(r"total\s*=\s*(?!story\.sources)", src[src.find("const isThinCoverage"):src.find("const isThinCoverage") + 200]))

print("\n=== 2: Blindspot explanation reuses the existing Coverage-Gaps copy verbatim ===")
method_note = re.search(
    r'const methodNote = lang==="hi"\s*\?\s*"([^"]+)"\s*:\s*"([^"]+)"', src)
check("2a: BlindspotPage's own existing methodNote is still present, unchanged", method_note is not None)
blindspot_ui = re.search(r'blindspotNote:\{en:"([^"]+)",\s*hi:"([^"]+)"\}', src)
check("2b: a UI.blindspotNote entry exists with EN and HI", blindspot_ui is not None)
if method_note and blindspot_ui:
    hi_orig, en_orig = method_note.group(1), method_note.group(2)
    en_new, hi_new = blindspot_ui.group(1), blindspot_ui.group(2)
    check("2c: the reused EN text is BYTE-IDENTICAL to BlindspotPage's methodNote (no new "
          "definition was written)", en_new == en_orig)
    check("2d: the reused HI text is BYTE-IDENTICAL to BlindspotPage's methodNote", hi_new == hi_orig)
check("2e: the explanation is gated on the SAME story.blindspot flag that already gates the "
      "existing BlindspotBadge (renders nothing when absent)",
      re.search(r'\{story\.blindspot && <p className=[^>]*>\{ui\("blindspotNote",lang\)\}</p>\}', src) is not None)
check("2f: the existing BlindspotBadge line itself is untouched",
      '{story.blindspot && <BlindspotBadge side={story.blindspot} t={t} lang={lang} />}' in src)
check("2g: no new section/modal component was introduced for this (it's a <p>, not a component)",
      "function BlindspotExplanation" not in src and "function BlindspotModal" not in src)

print("\n=== 3: related-stories reordering (behavior, executed via Node) ===")
related_fn = re.search(
    r"const related = \(\(\) => \{(.*?)\n\s*\}\)\(\);", src, re.S)
check("3a: the reordering IIFE is present", related_fn is not None)
related_body = related_fn.group(1) if related_fn else ""
check("3b: storyline siblings are considered before story_context",
      related_body.find("story.storyline") < related_body.find("story_context")
      if "story.storyline" in related_body and "story_context" in related_body else False)
check("3c: story_context is considered before the topic fallback",
      related_body.find("story_context") < related_body.find('c.topic === story.topic')
      if "story_context" in related_body else False)
check("3d: is_update===false entries are excluded from storyline siblings",
      "ev.is_update !== false" in related_body)
check("3e: the current story itself seeds the `seen` set (never included)",
      "seen = new Set([selfId])" in related_body)
check("3f: result is capped at 6", "picked.slice(0, 6)" in related_body)
check("3g: no new fetch/query call - unresolved ids are skipped via the existing baseCards "
      "lookup only (checking for an actual call, not just the word in prose/comments)",
      "byId.get(key)" in related_body
      and not re.search(r"\b(fetch|apiGet|apiPost|axios)\s*\(", related_body))

if NODE:
    print("\n=== behavioral execution of the REAL related-composition function (Node) ===")
    node_script = r"""
function computeRelated(story, baseCards) {
""" + related_body + r"""
}
function assert(label, cond) { console.log("  " + label + " ... " + (cond ? "OK" : "FAIL")); if (!cond) process.exitCode = 1; }
const card = (id, topic) => ({ id, topic });
const baseCards = [card(1,"Politics"),card(2,"Politics"),card(3,"Politics"),card(4,"Politics"),
                   card(5,"Politics"),card(6,"Politics"),card(7,"Politics")];
let story = { id: 5, topic: "Politics",
  storyline: { events: [{ id: 1, is_update: true }, { id: 2, is_update: true }, { id: 5, is_update: true }] } };
let r = computeRelated(story, baseCards);
assert("storyline siblings (1,2) lead, self (5) excluded, capped at 6, no dupes",
  r[0].id === 1 && r[1].id === 2 && !r.some(x => x.id === 5) && r.length === 6
  && new Set(r.map(x => x.id)).size === r.length);
story = { id: 5, topic: "Politics" };
r = computeRelated(story, baseCards);
const expected = baseCards.filter(c => c.topic === "Politics" && c.id !== 5).slice(0, 6).map(c => c.id);
assert("no storyline/context -> IDENTICAL to the old pure topic-filter fallback",
  JSON.stringify(r.map(x => x.id)) === JSON.stringify(expected));
"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="paksh_storypage_test_"))
    try:
        (tmp_dir / "check.js").write_text(node_script, encoding="utf-8")
        r = subprocess.run([NODE, str(tmp_dir / "check.js")], capture_output=True, text=True, timeout=60)
        print(r.stdout)
        if r.returncode != 0 or "FAIL" in r.stdout:
            FAILURES.append("3h: behavioral Node execution of the real related() logic")
            print(r.stderr)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
else:
    print("\n(skipping Node behavioral execution - node not found on PATH)")

if NODE:
    print("\n=== 4: app.jsx still compiles with the project's own Babel (temp file only) ===")
    babel = ROOT / "vendor" / "babel.min.js"
    tmp_out = Path(tempfile.mkdtemp(prefix="paksh_storypage_compile_")) / "app.compiled.js"
    script = (
        "const B=require(process.argv[1]);const fs=require('fs');"
        "const code=B.transform(fs.readFileSync(process.argv[2],'utf8'),{presets:['react'],compact:false}).code;"
        "fs.writeFileSync(process.argv[3],code);"
    )
    try:
        r = subprocess.run([NODE, "-e", script, str(babel), str(ROOT / "static" / "app.jsx"), str(tmp_out)],
                            capture_output=True, text=True, timeout=300)
        check("4a: Babel compiles app.jsx without error", r.returncode == 0)
        check("4b: the compiled output contains the new thin-coverage/blindspot/related logic",
              tmp_out.exists() and all(s in tmp_out.read_text(encoding="utf-8")
                                        for s in ("isThinCoverage", "blindspotNote", "story.storyline")))
    finally:
        shutil.rmtree(tmp_out.parent, ignore_errors=True)
else:
    print("\n(skipping Babel compile check - node not found on PATH)")

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
