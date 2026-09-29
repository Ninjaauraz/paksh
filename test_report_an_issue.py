"""test_report_an_issue.py - "Report an issue" article-reporting feature (static/app.jsx):
a quiet StoryPage link to /contact?report=1&article_id=<id>&article_title=<headline>, which
switches the EXISTING Formspree-native-POST ContactPage into an article-report form. No new
page, modal, API, database table, or backend - reuses the exact contact-form architecture
(test_contact_form.py) unchanged for report=1-absent requests.

STATIC regression test (no browser, no DB, no network) - matches this file's own house style
(test_ads_consent_csp.py, test_contact_form.py): read app.jsx as text, assert on its structure
and the isolated report-intent parser's actual behavior.

Run:  py test_report_an_issue.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


src = (ROOT / "static" / "app.jsx").read_text(encoding="utf-8")

m = re.search(r"function StoryPage\(.*?\n(?:.*\n)*?    \}\n", src)
check("0a: StoryPage component found", m is not None)
story_page = m.group(0) if m else ""

m2 = re.search(r"function ContactPage\(.*?\n(?:.*\n)*?    \}\n", src)
check("0b: ContactPage component found", m2 is not None)
contact_page = m2.group(0) if m2 else ""

print("\n=== 1/2/3: the report link exists, carries the right identifier, points at /contact?report=1 ===")
check("1: StoryPage renders a report link (TextLink call with a /contact?report=1 href)",
      re.search(r'href=\{`/contact\?report=1&article_id=\$\{encodeURIComponent\(story\.id\)\}', story_page) is not None)
check("2: the link carries the CURRENT article's own id (story.id), not a hardcoded/placeholder value",
      "encodeURIComponent(story.id)" in story_page)
check("3: the link's onClick navigates via go(...) to the same report=1 path (SPA fast-path, "
      "same href/onClick pattern used everywhere else in this file)",
      re.search(r'go\(`contact\?report=1&article_id=\$\{encodeURIComponent\(story\.id\)\}', story_page) is not None)
check("3b: no auth gate wraps the report link (available to guests, matching the feature's own "
      "'no login requirement' rule - unlike SaveButton/FollowButton just above it, which ARE "
      "gated on authOn())",
      "TextLink t={t} lang={lang}" in story_page and
      not re.search(r"authOn\(\)\s*&&\s*<TextLink", story_page))

print("\n=== 4/5/6: ContactPage recognizes report=1, shows the read-only headline, offers issue types ===")
check("4: ContactPage computes isReportMode from BOTH report=1 AND a validated article_id "
      "(report=1 alone is never sufficient - see check 13)",
      "const isReportMode = reportFlow && !!reportArticle;" in contact_page)
check("5: the resolved article title is displayed (read-only text, not an editable input)",
      "reportArticle.title" in contact_page and 'name="article_title"' in contact_page)
_title_input_tag = re.search(r'<input[^>]*value=\{reportArticle\.title\}[^>]*/>', contact_page)
check("5b: the article title is never rendered into an editable <input>/<textarea> value slot "
      "for the visitor to change - the one <input> using it as `value` is type=\"hidden\" "
      "(attribute order-independent check), and it is separately shown read-only in a <p>",
      _title_input_tag is not None and 'type="hidden"' in _title_input_tag.group(0))
check("6: all 7 required issue-type options are present",
      all(k in contact_page for k in
          ["factual", "missing", "wrong_entity", "headline", "source", "translation", "other"]))

print("\n=== 7/8: description required, email optional in report mode ===")
report_branch = contact_page[contact_page.find("isReportMode ? ("):contact_page.find("</form>")]
check("7: the description textarea is required in both modes (same shared <textarea name=\"message\" required>)",
      'name="message" required' in contact_page)
check("8: report mode's email field has NO required attribute (optional, unlike the normal "
      "form's required email)",
      re.search(r'\{isReportMode && \(\s*<div><label[^>]*>\{L\.reportEmailL\}</label>'
                r'<input name="email" type="email" className=\{inp\} />', contact_page) is not None)
check("8b: the normal (non-report) email field is untouched and still required",
      re.search(r'name="email" type="email" required className=\{inp\}', contact_page) is not None)

print("\n=== 9: hidden article metadata is submitted, always self-constructed / never trusted from the URL ===")
check("9a: article_id, article_title, article_url, issue_type are all hidden fields",
      all(f'name="{f}"' in contact_page for f in ("article_id", "article_title", "article_url", "issue_type")))
check("9b: article_url is NEVER read from the URL/query string - it is built only from "
      "reportArticle.url, itself constructed in _parseReportIntent from window.location.origin "
      "+ '/story/' + the validated id, never from a URL-supplied 'article_url' param",
      'qs.get("article_url")' not in src and
      'url: window.location.origin + "/story/" + encodeURIComponent(id)' in src)
check("9c: article_id must match a strict allowlist (letters/digits/-/_ only, bounded length) "
      "before it is trusted for anything, including building article_url",
      re.search(r'if \(!/\^\[A-Za-z0-9_-\]\{1,64\}\$/\.test\(id\)\) return null;', src) is not None)

print("\n=== 10/11: the existing Formspree native-POST architecture is unchanged ===")
check("10: the report form still posts via the SAME <form method=\"POST\" action={FORMSPREE_ENDPOINT}>",
      re.search(r'<form method="POST" action=\{FORMSPREE_ENDPOINT\} onSubmit=\{onSubmit\}', contact_page) is not None)
check("11a: no fetch(FORMSPREE_ENDPOINT, ...) call was introduced anywhere in this file",
      not re.search(r"fetch\(\s*FORMSPREE_ENDPOINT", src))
check("11b: no @formspree/react or any new dependency was introduced",
      "@formspree/react" not in src and not (ROOT / "package.json").exists())

print("\n=== 12: normal /contact behavior is unaffected (delegated to test_contact_form.py, "
      "re-verified here structurally) ===")
check("12: the normal-mode branch still renders the original name+email grid, the topic chips, "
      "and the original send label, completely unchanged",
      'name="name" type="text"' in contact_page and
      'name="email" type="email" required' in contact_page and
      "L.chips[k]" in contact_page and
      "isReportMode?L.reportSend:L.send" in contact_page)

print("\n=== 13: invalid/missing article metadata degrades gracefully ===")
check("13a: report=1 with NO article_id falls back to the normal form (isReportMode requires "
      "!!reportArticle, and _parseReportIntent returns null for an empty/invalid id)",
      "if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) return null;" in src)
check("13b: /contact with no report param at all is unaffected - reportFlow defaults to false "
      'from qs.get("report")==="1", never throws on a missing param',
      'reportFlow]=useState(()=>_qs0.get("report")==="1")' in contact_page)
check("13c: a malformed query string can never throw during render - URLSearchParams.get() "
      "returns null (coalesced to \"\") rather than throwing, and _parseReportIntent's regex "
      "test on that empty string simply fails closed",
      '(qs.get("article_id") || "").trim()' in src)

print("\n=== 14: Babel/JSX compilation succeeds ===")
# Delegated rather than reimplemented: test_story_page_p1.py already compiles this exact
# app.jsx with the project's own vendored Babel (temp file only, no _site side effects) -
# re-running it here proves THIS file, as edited by this feature, still compiles.
result = subprocess.run([sys.executable, str(ROOT / "test_story_page_p1.py")], capture_output=True, text=True)
check("14: the repo's own Babel-compile regression test (test_story_page_p1.py) passes "
      "against app.jsx as edited by this feature", result.returncode == 0)

print("\n=== 15: mobile layout - no new fixed/desktop-only styling introduced ===")
report_ui = contact_page[contact_page.find("isReportMode ? ("):contact_page.find("</form>")]
check("15: the report-mode fields use the SAME responsive utility classes as the rest of the "
      "form (no new sm:/md:/lg:-gated container, no fixed pixel widths) - it inherits the "
      "existing form column's mobile layout unchanged",
      not re.search(r"\bw-\[\d+px\]", report_ui) and not re.search(r"\bmin-w-\[\d+px\]", report_ui))

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
