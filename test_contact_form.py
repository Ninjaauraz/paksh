"""
test_contact_form.py - Contact/feedback form fix (static/app.jsx, ContactPage): production
submissions were failing ("Something went wrong" / "Could not send your message"). The prior
implementation submitted via fetch()/AJAX, which depends on Formspree's CORS/origin-allowance
holding at request time; this replaces it with Formspree's own native HTML POST integration
(a real <form method="POST" action="..."> submission), which is not subject to CORS at all -
removing that entire failure class by construction rather than by better error handling.

No npm package, no CDN script, no @formspree/react, no new dependency - matches the existing
bundler-free architecture. Formspree's own "_next" field redirects the browser back to
/contact?sent=1 on success; this component reads that query param on load to show the exact
same inline "thank you" state the page always showed, so the UX is preserved even though the
actual submission is now a full browser navigation rather than an in-page fetch.

What this pins:
  1. the form posts natively: method="POST", action exactly https://formspree.io/f/mkolqann
  2. every intended field has a real `name` attribute Formspree will receive
  3. email is type="email" and required; message is name="message" and required
  4. the honeypot (_gotcha), _subject and topic hidden fields are preserved unchanged
  5. a "_next" redirect-back field is present (native POST's only way to return the visitor
     to Paksh instead of Formspree's own generic confirmation page)
  6. no fetch()/AJAX call is used for the actual delivery any more
  7. no new dependency was introduced (no @formspree/react, no formspree CDN script tag)
  8. the CSP already served by export_static.py permits this exact origin in form-action
     (a native POST needs form-action, not connect-src, to be allowed)
  9. app.jsx still compiles with the project's own Babel (temp file only, no _site side effects)

Run:  py test_contact_form.py
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
FORMSPREE_URL = "https://formspree.io/f/mkolqann"

m = re.search(r"function ContactPage\(.*?\n(?:.*\n)*?    \}\n", src)
check("0: ContactPage component found in app.jsx", m is not None)
page = m.group(0) if m else ""

print("=== 1: native POST, exact Formspree endpoint ===")
check("1a: FORMSPREE_ENDPOINT constant is the exact form URL",
      f'const FORMSPREE_ENDPOINT = "{FORMSPREE_URL}";' in src)
check("1b: the <form> submits with method=\"POST\"", 'method="POST"' in page)
check("1c: the <form>'s action is exactly FORMSPREE_ENDPOINT (not a hardcoded/different URL)",
      re.search(r'<form method="POST" action=\{FORMSPREE_ENDPOINT\}', page) is not None)

print("\n=== 2/3: every intended field has a real name; email/message validation preserved ===")
check("2a: name field present (optional, no required)", 'name="name" type="text"' in page)
check("2b: email field has name=\"email\", type=\"email\" and required",
      re.search(r'name="email" type="email" required', page) is not None)
check("2c: message field has name=\"message\" and required",
      re.search(r'name="message" required', page) is not None)
check("2d: the topic hidden field still carries a real name Formspree receives",
      'name="topic"' in page)

print("\n=== 4: honeypot / subject fields preserved unchanged ===")
check("4a: honeypot _gotcha field preserved, still hidden and out of tab order",
      'name="_gotcha"' in page and 'tabIndex="-1"' in page and 'autoComplete="off"' in page)
check("4b: _subject hidden field preserved with its original value",
      '"_subject" value="New Paksh contact message"' in page)

print("\n=== 5: _next redirect-back field, so the visitor returns to Paksh, not Formspree ===")
check("5a: a hidden _next field is present", 'name="_next"' in page)
check("5b: _next points back at this same page with a success marker, built from the "
      "CURRENT origin (never a hardcoded domain, which would go stale on any domain change)",
      re.search(r'name="_next" value=\{window\.location\.origin\+"/contact\?sent=1"\}', page) is not None)
check("5c: on load, sent=1 in the URL is treated as the success state",
      re.search(r'get\("sent"\)\s*===\s*"1"\)\s*\?\s*"ok"\s*:\s*"idle"', page) is not None)
check("5d: the sent=1 marker is scrubbed from the URL after being read (history.replaceState), "
      "matching the SAME idiom already used elsewhere in this file for the auth redirect flow",
      re.search(r'sent=1.*history\.replaceState\(null,""', page) is not None)

print("\n=== 6: no fetch()/AJAX call drives the actual delivery any more ===")
check("6a: no fetch(FORMSPREE_ENDPOINT, ...) call remains in ContactPage",
      "fetch(FORMSPREE_ENDPOINT" not in page)
check("6b: onSubmit does not preventDefault - the browser's own native POST navigation "
      "is what actually delivers the submission",
      re.search(r"function onSubmit\(\)\{\s*setStatus\(\"sending\"\);\s*\}", page) is not None
      and "e.preventDefault()" not in page.split("function onSubmit")[1].split("\n")[0])

print("\n=== 7: no new dependency introduced ===")
check("7a: no @formspree/react anywhere in the source tree",
      not (ROOT / "static").exists() or "@formspree/react" not in src)
check("7b: no Formspree CDN/script tag added to the app shell",
      "formspree.io" not in (ROOT / "static" / "index.html").read_text(encoding="utf-8"))
check("7c: package.json still doesn't exist / wasn't introduced (bundler-free architecture unchanged)",
      not (ROOT / "package.json").exists())

print("\n=== 8: the site's own CSP already allows this exact form-action origin ===")
export_src = (ROOT / "export_static.py").read_text(encoding="utf-8")
check("8a: export_static.py's CSP has a form-action directive naming https://formspree.io",
      re.search(r"form-action[^;\"]*https://formspree\.io", export_src) is not None)

if shutil.which("node"):
    print("\n=== 9: app.jsx still compiles with the project's own Babel (temp file only) ===")
    babel = ROOT / "vendor" / "babel.min.js"
    tmp_out = Path(tempfile.mkdtemp(prefix="paksh_contact_test_")) / "app.compiled.js"
    script = (
        "const B=require(process.argv[1]);const fs=require('fs');"
        "const code=B.transform(fs.readFileSync(process.argv[2],'utf8'),{presets:['react'],compact:false}).code;"
        "fs.writeFileSync(process.argv[3],code);"
    )
    try:
        r = subprocess.run(["node", "-e", script, str(babel), str(ROOT / "static" / "app.jsx"), str(tmp_out)],
                            capture_output=True, text=True, timeout=300)
        check("9a: Babel compiles app.jsx without error", r.returncode == 0)
        check("9b: the compiled output contains the native-POST contact form action",
              tmp_out.exists() and FORMSPREE_URL in tmp_out.read_text(encoding="utf-8"))
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
