"""
test_mobile_share.py - post-launch mobile Share fix (static/app.jsx, Masthead component).

Paksh has no npm build step and no JS test runner, so - matching the existing convention
in test_search_client_side.py/test_ads_consent_csp.py - this inspects the real app.jsx
SOURCE for the exact structure the fix requires, then compiles it with the project's own
vendored Babel into a TEMP file (no _site side effects) as a syntax-validity check.

What this pins:
  1. a Share button exists in the mobile-only action row (the one Save/Follow already ship to)
  2. navigator.share is called, with title/text/url, when the API is available
  3. the URL passed is the CURRENT page URL (window.location.href - the canonical /story/<id>
     the reader is actually on), never a source/external URL
  4. when navigator.share is unavailable, the existing clipboard-copy mechanism is used instead
  5. a cancelled native share (AbortError) is swallowed silently - no fallback, no error
  6. the existing DESKTOP Share/Copy button (the sm:flex row) is byte-for-byte untouched

Run:  py test_mobile_share.py
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

print("=== 1: Share button exists in the mobile-only action row ===")
mobile_row = re.search(
    r'\{isReading && story && \(\s*<div className="flex items-center gap-3 pb-3 sm:hidden">'
    r'(.*?)</div>\s*\)\}',
    src, re.S)
check("1a: the mobile action row block is present", mobile_row is not None)
mobile_row_text = mobile_row.group(1) if mobile_row else ""
check("1b: SaveButton and FollowButton are still the first two actions in that row (unchanged)",
      "<SaveButton" in mobile_row_text and "<FollowButton" in mobile_row_text)
check("1c: a third action (Share) is present in the SAME row, not gated behind authOn()",
      "onClick={share}" in mobile_row_text
      and not re.search(r"authOn\(\)\s*&&[^\n]*onClick=\{share\}", mobile_row_text))
check("1d: it uses a real <button> (keyboard-activatable) with an accessible label",
      re.search(r'<button type="button" onClick=\{share\}\s*\n?\s*aria-label=', mobile_row_text) is not None)

print("\n=== 2/3: navigator.share is called with title/text and the CURRENT page URL ===")
share_fn = re.search(r"const share=\(\)=>\{(.*?)\n {6}\};", src, re.S)
check("2a: a `share` handler function exists", share_fn is not None)
share_body = share_fn.group(1) if share_fn else ""
check("2b: it builds a shareData object with title, text and url",
      re.search(r"title:\s*\(story", share_body) is not None
      and re.search(r"text:\s*\(story", share_body) is not None
      and "url:window.location.href" in share_body)
check("2c: the URL passed is window.location.href - the canonical current-page URL, "
      "never a source/external article URL",
      "url:window.location.href" in share_body
      and "source" not in share_body.lower())
check("2d: navigator.share is actually invoked when present",
      re.search(r"if\(navigator\.share\)\{", share_body) is not None
      and "navigator.share(shareData)" in share_body)
check("2e: title/text use story.headline - the already language-resolved headline "
      "(Hindi when lang==='hi' and title_hi exists, English otherwise)",
      "story.headline" in share_body)

print("\n=== 4: clipboard fallback when navigator.share is unavailable ===")
check("4a: the else branch (no navigator.share) calls the existing copy() clipboard handler",
      re.search(r"\}\s*else\s*\{\s*copy\(\);\s*\}", share_body) is not None)
check("4b: copy() itself is the existing, untouched clipboard mechanism",
      'navigator.clipboard.writeText(window.location.href)' in src)

print("\n=== 5: a cancelled native share (AbortError) is swallowed, not treated as an error ===")
check("5a: navigator.share's rejection is caught",
      ".catch(e=>{" in share_body)
check("5b: AbortError returns immediately - no fallback call, no error path",
      re.search(r'\.catch\(e=>\{\s*if\(e&&e\.name==="AbortError"\)\s*return;\s*copy\(\);\s*\}\)', share_body) is not None)

print("\n=== 6: the existing DESKTOP Share/Copy action is untouched ===")
desktop_share = '<button onClick={copy} className={`inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}>{copied?<><Check size={13}/> {lang==="hi"?"कॉपी":"Copied"}</>:<><LinkIcon size={13}/> {lang==="hi"?"शेयर":"Share"}</>}</button>'
check("6a: the exact pre-existing desktop button markup is still present, byte-for-byte",
      desktop_share in src)
check("6b: it still lives inside the desktop-only (sm:flex) wrapper, not the mobile row",
      re.search(r'hidden shrink-0 items-center gap-3 sm:flex">\s*\{authOn\(\) && onToggleSave', src) is not None)

print("\n=== 7: no new dependency, no login required for Share ===")
check("7a: ShareIcon is a plain inline SVG (same style as every other icon here), not an import",
      re.search(r'const ShareIcon=\(p\)=><svg', src) is not None)
check("7b: the mobile Share button itself has no authOn() gate anywhere in its own JSX line",
      not re.search(r"authOn\(\)[^\n]*share\b", mobile_row_text))

if NODE:
    print("\n=== 8: app.jsx still compiles with the project's own Babel (temp file only) ===")
    babel = ROOT / "vendor" / "babel.min.js"
    tmp_out = Path(tempfile.mkdtemp(prefix="paksh_share_test_")) / "app.compiled.js"
    script = (
        "const B=require(process.argv[1]);const fs=require('fs');"
        "const code=B.transform(fs.readFileSync(process.argv[2],'utf8'),{presets:['react'],compact:false}).code;"
        "fs.writeFileSync(process.argv[3],code);"
    )
    try:
        r = subprocess.run([NODE, "-e", script, str(babel), str(ROOT / "static" / "app.jsx"), str(tmp_out)],
                            capture_output=True, text=True, timeout=300)
        check("8a: Babel compiles app.jsx without error", r.returncode == 0)
        check("8b: the compiled output actually contains the new share logic",
              tmp_out.exists() and "navigator.share" in tmp_out.read_text(encoding="utf-8"))
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
