"""
ingest.py - STEP 1 of the pipeline: pull fresh articles from every feed.

Run:
    python ingest.py                      # ingest all sources in the registry
    python ingest.py --discover URL       # find RSS feeds for a new site

What it does, per source -> per feed -> per article:
  * fetches each RSS feed (politely: UA header, timeout, small delay)
  * normalises: clean title/summary, canonical URL (strips tracking params),
    publish date parsed to UTC ISO, best-effort image
  * tags language + outlet from the registry
  * de-dupes within the run (canonical URL) and across runs (DB UNIQUE on url)
  * isolates failures: one broken feed logs a warning and never stops the run

Storage uses database.insert_article() unchanged, so the rest of the app
(clustering, API) keeps working.
"""

import sys
import re
import html
import time
import socket
import calendar
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote
import urllib.request

import feedparser

from database import init_db, insert_article, count_articles
from sources import SOURCES, get_source
from feeds import FEEDS, VERIFIED

USER_AGENT = "Mozilla/5.0 (compatible; PakshBot/0.3; +news transparency research)"
REQUEST_HEADERS = {"Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"}
FETCH_TIMEOUT = 15           # seconds
POLITE_DELAY = 1.0           # seconds between feed requests
SUMMARY_MAX = 600            # chars

# query params that are tracking noise, not article identity
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src",
    "source", "cmpid", "at_medium", "at_campaign", "ncid", "spm",
}


# ----------------------------- normalisation -----------------------------

def clean_text(raw: str) -> str:
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    decoded = html.unescape(no_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def tidy_title(title: str, source_name: str = "") -> str:
    """Clean up titles, mainly from Google-News-bridged feeds, which often arrive
    URL-encoded ('Namma%20Metro') and with the outlet appended (' - Swarajyamag')."""
    if not title:
        return ""
    if "%2" in title or "%3" in title:          # looks URL-encoded -> decode it
        try:
            title = re.sub(r"\s+", " ", unquote(title)).strip()
        except Exception:
            pass
    for sep in (" - ", " \u2013 ", " | ", " \u2014 "):   # strip a trailing " - Outlet" suffix
        idx = title.rfind(sep)
        if idx > 0:
            tail = title[idx + len(sep):].strip()
            if 0 < len(tail) <= 30 and len(tail.split()) <= 4:   # short -> it's the outlet name
                title = title[:idx].strip()
                break
    return title


# Non-news that leaks in via Google-News bridges and aggregator feeds: horoscopes,
# recipes, "quote of the day", search/tag/pagination pages, candidate-bio election
# templates. These pollute the pool and some even cluster into junk "events" (the
# मकर राशि horoscope did). Drop them at ingestion. Kept deliberately conservative so
# real headlines are never caught.
_JUNK_RE = re.compile(
    r"(search results for|you searched for|\|\s*page\s*\d+|read all latest updates|"
    r"insightful articles and opinions|quote of the day|proverb of the day|"
    r"horoscope|astrological prediction|rashifal|राशिफल|कुंडली|धन योग|"
    r"\brecipe\b|रेसिपी|"
    r"election result\s*20\d\d|निर्वाचन परिणाम\s*20\d\d|"
    r"age,?\s*education,?\s*political career|विधानसभा चुनाव.{0,8}परिणाम|"
    r"news in hindi:\s*latest|latest .{0,30}news[:,].{0,30}top stories)", re.I)

_ZODIAC_HI = ("मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या",
              "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन")


def is_junk(title: str) -> bool:
    """True if the 'article' is really a horoscope / recipe / tag / search page etc."""
    t = (title or "").strip()
    if len(t) < 6:                                  # empty or suffix-only remnant
        return True
    if t.startswith("- ") or t.startswith("#"):     # "- Scroll.in", "#Crime"
        return True
    if " " not in t and t.count("-") >= 2:          # url-slug titles ("jio-sim-offer-...")
        return True
    if _JUNK_RE.search(t):
        return True
    if len(t) < 30 and ("राशि" in t or any(z in t for z in _ZODIAC_HI)):
        return True                                 # "मकर राशि" zodiac category pages
    if len(t.split()) == 1 and t.isascii() and len(t) < 18:
        return True                                 # single-word tag pages ("Stokes", "Kashmir")
    return False


def canonical_url(url: str) -> str:
    """Lower-case host, drop fragment, strip tracking params - so the same
    article arriving with different ?utm_... tags de-dupes to one record."""
    if not url:
        return ""
    try:
        s = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = s.scheme.lower() or "https"
    netloc = s.netloc.lower()
    kept = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=False)
            if k.lower() not in TRACKING_PARAMS]
    query = urlencode(kept)
    path = s.path.rstrip("/") or s.path
    return urlunsplit((scheme, netloc, path, query, ""))  # fragment dropped


def parse_date(entry) -> str:
    """Return an ISO-8601 UTC string when the feed gives a real date, else the
    raw string, else ''. feedparser exposes *_parsed as UTC struct_time."""
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                dt = datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
                return dt.isoformat()
            except (ValueError, OverflowError):
                pass
    return entry.get("published", "") or entry.get("updated", "")


def extract_image(entry) -> str:
    """Feeds expose images many ways - try them in order of reliability."""
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures", []) or []:
        if "image" in (enc.get("type") or "") and enc.get("href"):
            return enc["href"]
    for l in entry.get("links", []) or []:
        if "image" in (l.get("type") or "") and l.get("href"):
            return l["href"]
    blob = entry.get("summary", "") or ""
    for c in entry.get("content", []) or []:
        blob += c.get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob)
    return m.group(1) if m else ""


def normalize_entry(entry, source: dict):
    """Turn a raw feed entry into the record shape the DB expects, or None."""
    title = tidy_title(clean_text(entry.get("title", "")), source.get("name", ""))
    link = canonical_url(entry.get("link", ""))
    if not title or not link or is_junk(title):
        return None
    summary = clean_text(entry.get("summary", "") or entry.get("description", ""))[:SUMMARY_MAX]
    return {
        "source": source["name"],
        "language": source["language"],
        "title": title,
        "url": link,
        "summary": summary,
        "image_url": extract_image(entry),
        "published": parse_date(entry),
    }


# ----------------------------- fetching -----------------------------

def fetch_feed(feed_url: str):
    """Parse one feed URL. Returns feedparser result or None on hard failure."""
    try:
        return feedparser.parse(feed_url, agent=USER_AGENT, request_headers=REQUEST_HEADERS)
    except Exception as e:
        print(f"      ! fetch error: {e}")
        return None


def ingest_feed(feed_url: str, source: dict, seen: set):
    """Ingest one feed URL into the DB. Returns (new, considered)."""
    parsed = fetch_feed(feed_url)
    if parsed is None:
        return 0, 0
    if parsed.bozo and not parsed.entries:
        reason = getattr(parsed, "bozo_exception", "unreadable")
        print(f"      ! no entries ({reason})")
        return 0, 0

    new = considered = 0
    for entry in parsed.entries:
        norm = normalize_entry(entry, source)
        if not norm:
            continue
        considered += 1
        if norm["url"] in seen:        # duplicate within this run
            continue
        seen.add(norm["url"])
        rowid = insert_article(
            norm["source"], norm["language"], norm["title"], norm["url"],
            norm["summary"], norm["image_url"], norm["published"],
        )
        if rowid is not None:          # None => already in DB (cross-run dupe)
            new += 1
    return new, considered


def ingest_source(source: dict, seen: set) -> int:
    urls = FEEDS.get(source["id"], [])
    tag = "verified" if source["id"] in VERIFIED else "candidate"
    if not urls:
        print(f"  - {source['name']} ({source['language']}): no feed configured - skip")
        return 0
    print(f"  > {source['name']} ({source['language']}, {tag})")
    total_new = 0
    for u in urls:
        new, considered = ingest_feed(u, source, seen)
        total_new += new
        print(f"      {new:>3} new / {considered:>3} items   {u}")
        time.sleep(POLITE_DELAY)
    return total_new


# ----------------------------- feed discovery -----------------------------

def discover_feeds(site_url: str):
    """Find RSS/Atom feeds for a site: read <link rel=alternate> on the home
    page, then probe a few common paths. Prints anything that looks valid.
    (Runs on your machine - the sandbox can't reach news sites.)"""
    print(f"\nDiscovering feeds for {site_url}\n" + "-" * 40)
    found = []
    try:
        req = urllib.request.Request(site_url, headers={"User-Agent": USER_AGENT})
        homepageHtml = urllib.request.urlopen(req, timeout=FETCH_TIMEOUT).read().decode("utf-8", "ignore")
        for m in re.finditer(
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', homepageHtml, re.I):
            href = re.search(r'href=["\']([^"\']+)["\']', m.group(0))
            if href:
                found.append(href.group(1))
    except Exception as e:
        print(f"  (couldn't read home page: {e})")

    base = "{0.scheme}://{0.netloc}".format(urlsplit(site_url))
    for path in ("/feed/", "/rss", "/rss.xml", "/feeds/all.rss", "/feed.xml", "/atom.xml"):
        cand = base + path
        p = fetch_feed(cand)
        if p is not None and p.entries:
            found.append(cand)

    found = sorted(set(found))
    if found:
        print("  Working feeds found:")
        for f in found:
            print(f"    {f}")
        print("\n  Paste the good one(s) into feeds.py under this source's id.")
    else:
        print("  No feeds auto-found. Check the site's footer for an RSS link.")
    return found


# ----------------------------- entrypoint -----------------------------

def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--discover":
        discover_feeds(sys.argv[2])
        return

    socket.setdefaulttimeout(FETCH_TIMEOUT)
    print("\n=== Paksh ingestion ===")
    init_db()
    seen: set = set()
    total_new = sum(ingest_source(s, seen) for s in SOURCES)
    print("-" * 40)
    print(f"Added {total_new} new articles. Database holds {count_articles()} total.")
    configured = sum(1 for s in SOURCES if FEEDS.get(s["id"]))
    print(f"Sources with a feed configured: {configured}/{len(SOURCES)} "
          f"({len(VERIFIED)} verified).")
    if total_new == 0:
        print("\nNo new articles - normal if you just ingested, or feeds need updating.")
        print("Tip:  python ingest.py --discover https://www.bhaskar.com")
    print("\nNext step:  python analyze.py\n")


if __name__ == "__main__":
    main()