"""
test_phase42_provenance.py - production hardening: provenance metadata on every story page.

_story_html() writes a NewsArticle JSON-LD block into each pre-rendered story page. This pins the
provenance fields added on top of the existing ones (author, copyright holder/year, and the cited
source articles via isBasedOn) and re-verifies the pre-existing script-breakout escaping still holds
with the larger payload. No DB, no network.

Run:  py test_phase42_provenance.py
"""
import json
import re
from pathlib import Path

import export_static

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


SHELL = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


def ld_of(html):
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    # the story page's NewsArticle block is the LAST ld+json block in <head>
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return json.loads(blocks[-1]), blocks[-1]


EV = {
    "id": 12345, "title": "Test Story Headline", "summary": "A neutral summary of the event.",
    "created_at": "2026-09-19T09:33:13", "published_at": "2026-09-19T08:00:00", "lang": "en",
    "coverage": {"left": {"count": 1, "sources": ["Outlet A"]}, "center": {"count": 1, "sources": ["Outlet B"]},
                 "right": {"count": 0, "sources": []}},
    "sources": [{"source": "Outlet %d" % i, "url": "https://example.org/a/%d" % i, "headline": "Headline %d" % i}
                for i in range(12)] + [{"source": "Bad", "url": "javascript:alert(1)", "headline": "x"}],
}

print("=== provenance fields ===")
html = export_static._story_html(SHELL, dict(EV))
ld, raw = ld_of(html)
check("1: still a NewsArticle with the story URL", ld["@type"] == "NewsArticle" and ld["url"].endswith("/story/12345"))
check("2: author is the Paksh organisation", ld["author"]["@type"] == "Organization" and ld["author"]["name"] == "Paksh")
check("3: copyright holder is Redstocks Technology LLP", ld["copyrightHolder"]["name"] == "Redstocks Technology LLP")
check("4: copyrightYear derives from datePublished", ld["copyrightYear"] == 2026)
check("5: isBasedOn cites the source articles, capped at 8", len(ld["isBasedOn"]) == 8)
check("6: every cited source carries url + publisher name",
      all(x["url"].startswith("https://") and x["publisher"]["name"] for x in ld["isBasedOn"]))
check("7: non-http(s) source URLs are never cited", not any("javascript:" in x["url"] for x in ld["isBasedOn"]))
check("8: publisher/logo/free-access fields unchanged",
      ld["publisher"]["name"] == "Paksh" and ld["isAccessibleForFree"] is True)

print("\n=== safety ===")
evil = dict(EV, title='</script><script>alert(1)</script>', sources=[
    {"source": '</script>X', "url": "https://e.org/?a=</script><b>", "headline": "</script><img src=x>"}])
html2 = export_static._story_html(SHELL, evil)
_, raw2 = ld_of(html2)
check("9: hostile title/source text cannot break out of the JSON-LD <script>",
      "</script" not in raw2 and "<" not in raw2 and ">" not in raw2)
check("10: escaped JSON-LD still parses", isinstance(json.loads(raw2), dict))
noref = dict(EV); noref.pop("sources")
check("11: an event with no sources still renders (no isBasedOn key)",
      "isBasedOn" not in ld_of(export_static._story_html(SHELL, noref))[0])

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
