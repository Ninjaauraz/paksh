"""
gdelt_source.py - pull India-relevant article metadata from GDELT's free
DOC 2.0 API and feed it into the same database as the RSS feeds.

WHY
---
GDELT indexes thousands of outlets worldwide and refreshes every 15 minutes.
We use it as a firehose for *coverage density*: articles whose domain matches one
of our rated outlets (sources.py) are credited to that outlet; everything else is
ingested as an UNRATED outlet - it adds clustering density and can surface
blindspots, but it NEVER votes in the Left / Centre / Right bias bar.

No API key is needed. The endpoint is rate-limited (~1 request / 5s), so we sleep
between queries and cap each query at GDELT's hard limit of 250 records.

RUN
---
    py gdelt_source.py                 # after ingest.py, before cluster.py
    py gdelt_source.py --timespan 2d   # widen the window
    py refresh.py --gdelt              # as part of the full pipeline

NOTE: this hits an external API, so it must run on your machine (not in the
sandbox). It writes via database.insert_article() exactly like ingest.py, so the
rest of the pipeline (cluster -> analyze -> export) is unchanged.
"""

import json
import random
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

from database import init_db, insert_article
from sources import resolve_source
from ingest import is_junk, tidy_title, clean_text, canonical_url

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# India-relevant queries. `sourcecountry:india` = outlets GDELT geolocates to
# India (a huge long tail incl. regional/local papers we don't yet track). The
# keyword query catches India coverage from international outlets.
QUERIES = [
    'sourcecountry:india sourcelang:english',
    'sourcecountry:india sourcelang:hindi',
    'india sourcelang:english',
]

LANG_MAP = {"english": "en", "eng": "en", "en": "en", "hindi": "hi", "hin": "hi", "hi": "hi"}

# Syndication networks / content farms that republish one wire story across many
# domains (or subdomains) to fake breadth. Dropped at ingest to save embedding
# budget; the >=2-rated-outlet rule in analyze.py is the real safety net for any
# we miss. Keyed by registrable domain (resolve_source already collapses
# subdomains, so all *.iheart.com map to 'iheart.com').
_BLOCKLIST = {
    "iheart.com", "today.com",
    # World News Network geo-named farm (one wire feed, dozens of domains)
    "africaleader.com", "asiabulletin.com", "bangladeshsun.com", "calcuttanews.net",
    "chinanationalnews.com", "cincinnatisun.com", "europesun.com", "floridastatesman.com",
    "haitisun.com", "heraldglobe.com", "indiablooms.com", "indiagazette.com",
    "israelherald.com", "japanherald.com", "kenyastar.com", "massachusettssun.com",
    "middleeaststar.com", "myanmarnews.net", "neworleanssun.com", "newsindiatimes.com",
    "oklahomastar.com", "parisguardian.com", "pittsburghstar.com", "russiaherald.com",
    "saltlakecitysun.com", "sandiegosun.com", "southeastasiapost.com", "tennesseedaily.com",
    "texasguardian.com", "utahindependent.com", "arabherald.com", "azerbaijannews.net",
    "afghanistannews.net", "bruneinews.net", "dominicanrepublicpost.com",
}
TIMESPAN = "1d"        # last 24 hours
MAXRECORDS = 250       # GDELT hard cap per call
SLEEP = 6              # be polite between queries (~1 query / 6s)

# GDELT's DOC API returns HTTP 429 for non-browser User-Agents, so we must send
# a browser-like UA (see github.com/alex9smith/gdelt-doc-api issue #22).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _fetch(query, timespan=TIMESPAN, maxrecords=MAXRECORDS, retries=4):
    """Call the GDELT DOC API and return its ArtList. Retries on 429/503 with
    exponential backoff + jitter, honouring any Retry-After header."""
    params = {
        "query": query, "mode": "ArtList", "format": "json",
        "timespan": timespan, "maxrecords": str(maxrecords), "sort": "DateDesc",
    }
    url = GDELT_URL + "?" + urllib.parse.urlencode(params)
    delay = 8
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            try:
                return json.loads(body).get("articles", [])
            except json.JSONDecodeError:
                # GDELT returns an HTML notice (not JSON) when overloaded.
                return []
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", 0) or 0) or delay
                wait += random.uniform(0, 3)
                print(f"    (GDELT {e.code}; waiting {wait:.0f}s, retry "
                      f"{attempt + 1}/{retries - 1})")
                time.sleep(wait)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    return []


def _domain(art):
    d = (art.get("domain") or "").lower().strip()
    if not d:
        d = urllib.parse.urlparse(art.get("url", "")).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def normalize_gdelt(art):
    """A GDELT ArtList item -> our article dict, or None to skip it."""
    title = tidy_title(clean_text(art.get("title", "")))
    url = art.get("url", "")
    if not title or not url or is_junk(title):
        return None
    lang = LANG_MAP.get((art.get("language") or "").lower())
    if lang is None:
        return None                                # only en / hi display in the UI
    name, rated = resolve_source(_domain(art))     # registry name, or unrated domain
    if not rated and name in _BLOCKLIST:
        return None                                # syndication farm -> drop
    return {
        "source": name,
        "language": lang,
        "title": title,
        "url": canonical_url(url),
        "summary": "",
        "image_url": art.get("socialimage", "") or "",
        "published": (art.get("seendate", "") or "")[:8],   # YYYYMMDD if present
        "rated": rated,
        "domain": _domain(art),
    }


def run(queries=QUERIES, timespan=TIMESPAN, verbose=True):
    init_db()
    seen = set()
    added = rated_n = unrated_n = 0
    unrated_domains = set()
    for q in queries:
        try:
            arts = _fetch(q, timespan)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if verbose:
                print(f"  ! GDELT query failed ({q[:42]}...): {e}")
            time.sleep(SLEEP)
            continue
        if verbose:
            print(f"  > GDELT [{q[:48]}] -> {len(arts)} articles")
        for art in arts:
            norm = normalize_gdelt(art)
            if not norm or norm["url"] in seen:
                continue
            seen.add(norm["url"])
            rowid = insert_article(
                norm["source"], norm["language"], norm["title"], norm["url"],
                norm["summary"], norm["image_url"], norm["published"],
            )
            if rowid is not None:                  # None => already in DB
                added += 1
                if norm["rated"]:
                    rated_n += 1
                else:
                    unrated_n += 1
                    unrated_domains.add(norm["domain"])
        time.sleep(SLEEP)

    if verbose:
        print(f"\nGDELT added {added} new articles "
              f"({rated_n} to rated outlets; "
              f"{unrated_n} from {len(unrated_domains)} unrated outlets).")
        print("Unrated outlets add coverage + cluster density but never vote in the bias bar.")
    return added


if __name__ == "__main__":
    span = TIMESPAN
    if "--timespan" in sys.argv:
        i = sys.argv.index("--timespan")
        if i + 1 < len(sys.argv):
            span = sys.argv[i + 1]
    run(timespan=span)