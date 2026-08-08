"""
build_missing_feeds.py - give every registry source an RSS feed (idempotent)
============================================================================
`ingest.py` skips any source that has no entry in feeds.py ("no feed configured
- skip"). This tool fills those gaps: for each source in sources.py that is NOT
yet in FEEDS, it writes an entry using the project's proven pattern -

  * a GOOGLE NEWS bridge  (site-scoped, reliable for ANY outlet; RSS articles are
    attributed to the feed's owning source, so credit is always correct), plus
  * a NATIVE RSS feed where a stable one is well known (fuller, real URLs).

Everything it adds is a CANDIDATE - broken/native feeds just log a warning and are
skipped by ingest.py, and the Google News bridge still delivers. Confirm/replace
natives with:  py ingest.py --discover https://the-site.com

Idempotent: re-running only adds sources still missing. Safe to run after any
future source expansion.

Run:  py build_missing_feeds.py        (add --dry to preview without writing)
"""

import re
import sys
from pathlib import Path

from sources import SOURCES, _host
from feeds import FEEDS

FEEDS_PY = Path(__file__).with_name("feeds.py")

# Native RSS feeds we're reasonably confident are stable. Anything not listed
# here gets a Google News bridge only. Wrong guesses fail gracefully.
NATIVE = {
    # --- Indian ---
    "economic_times":     ["https://economictimes.indiatimes.com/rssfeedstopstories.cms",
                           "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"],
    "financial_express":  ["https://www.financialexpress.com/feed/"],
    "hindu_business_line":["https://www.thehindubusinessline.com/feeder/default.rss"],
    "the_statesman":      ["https://www.thestatesman.com/feed"],
    # --- International: news ---
    "nyt":                ["https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
                           "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"],
    "washington_post":    ["https://feeds.washingtonpost.com/rss/world"],
    "npr":                ["https://feeds.npr.org/1001/rss.xml"],
    "cbs_news":           ["https://www.cbsnews.com/latest/rss/world"],
    "cbc_news":           ["https://www.cbc.ca/webfeed/rss/rss-world"],
    "nbc_news":           ["https://feeds.nbcnews.com/nbcnews/public/world"],
    "abc_australia":      ["https://www.abc.net.au/news/feed/51120/rss.xml"],
    "sky_news":           ["https://feeds.skynews.com/feeds/rss/world.xml"],
    "the_independent":    ["https://www.independent.co.uk/news/world/rss"],
    "le_monde":           ["https://www.lemonde.fr/en/rss/une.xml"],
    "euronews":           ["https://www.euronews.com/rss"],
    "the_atlantic":       ["https://www.theatlantic.com/feed/all/"],
    "time_magazine":      ["https://time.com/feed/"],
    "metro_uk":           ["https://metro.co.uk/feed/"],
    "global_news_ca":     ["https://globalnews.ca/feed/"],
    "japan_times":        ["https://www.japantimes.co.jp/feed/"],
    "scmp":               ["https://www.scmp.com/rss/91/feed"],
    "cna":                ["https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml"],
    "financial_times":    ["https://www.ft.com/rss/home"],
    "the_economist":      ["https://www.economist.com/international/rss.xml"],
    # --- International: business/finance ---
    "fortune":            ["https://fortune.com/feed/"],
    "forbes":             ["https://www.forbes.com/business/feed/"],
}


def _gn_bridge(host: str, lang: str, intl: bool, when: str = "2d") -> str:
    """Google News site-scoped RSS bridge. India sources use IN locale; foreign
    sources use a broad en-US locale (returns that outlet's English coverage)."""
    if intl:
        hl, gl, ceid = "en-US", "US", "US:en"
    elif lang == "hi":
        hl, gl, ceid = "hi-IN", "IN", "IN:hi"
    else:
        hl, gl, ceid = "en-IN", "IN", "IN:en"
    return (f"https://news.google.com/rss/search?q=site:{host}+when:{when}"
            f"&hl={hl}&gl={gl}&ceid={ceid}")


def _entry_lines(src) -> str:
    sid = src["id"]
    host = _host(src["website"])
    intl = src.get("region") == "International"
    urls = list(NATIVE.get(sid, []))
    urls.append(_gn_bridge(host, src["language"], intl))
    tag = "intl" if intl else src["language"]
    body = ",\n".join(f'        "{u}"' for u in urls)
    return (f'    # {src["name"]} ({tag}){" [+native]" if sid in NATIVE else ""}\n'
            f'    "{sid}": [\n{body},\n    ],\n')


def main():
    missing = [s for s in SOURCES if s["id"] not in FEEDS]
    if not missing:
        print("All sources already have feeds. Nothing to do.")
        return
    block = ("\n    # ===== v1.6 auto-added feeds (build_missing_feeds.py) =====\n"
             "    # Google News bridges (reliable) + native RSS where known. All\n"
             "    # CANDIDATE - verify/replace natives with `py ingest.py --discover URL`.\n")
    block += "".join(_entry_lines(s) for s in missing)

    text = FEEDS_PY.read_text(encoding="utf-8")
    # insert just before the line that closes the FEEDS dict (the `}` preceding
    # the "# Confirmed against public RSS directories" VERIFIED block).
    anchor = "\n}\n\n# Confirmed against public RSS directories"
    if anchor not in text:
        print("ERROR: could not find FEEDS closing anchor in feeds.py; aborting.")
        sys.exit(1)
    new_text = text.replace(anchor, "\n" + block + "}\n\n# Confirmed against public RSS directories", 1)

    print(f"Adding feeds for {len(missing)} source(s):")
    for s in missing:
        n = " (+native)" if s["id"] in NATIVE else ""
        print(f"  + {s['id']}{n}")
    if "--dry" in sys.argv:
        print("\n--dry: not writing. Preview of block:\n")
        print(block)
        return
    FEEDS_PY.write_text(new_text, encoding="utf-8")
    print(f"\nWrote {FEEDS_PY.name}. Re-run `py ingest.py` to pull them.")


if __name__ == "__main__":
    main()
