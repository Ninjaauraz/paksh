"""
pdi_providers.py - PDI discovery adapters (Reddit, Substack).

Provider-specific logic lives ONLY here, isolated from pdi.py's core pipeline exactly
as required (Part 6: "Design adapters so additional people-led sources can be added
later without changing the core PDI pipeline"). pdi.py's run_discovery() only ever
calls adapter(query, limit) -> list[pdi.Candidate] through the PROVIDERS registry
below - it has no knowledge of Reddit/Substack specifics.

DISCOVERY IS PERMISSIVE (Part 6): an adapter's only job is to find and NORMALIZE
candidates. It must never decide whether a candidate is true, important,
representative, or relevant - those judgments happen later, in pdi.py's
filter_candidates()/associate_candidate(). Concretely, an adapter here never drops a
result for being "probably irrelevant" - it only fails to include something it
genuinely could not fetch/parse.

REDDIT: uses old.reddit.com's public search.json endpoint (no API key, no praw
dependency - praw is not installed in this repository and this avoids adding a new
dependency for a v1). A large thread is reduced to a small number of REPRESENTATIVE
candidates (the top self-text posts by relevance-sort, plus a bounded number of
top-level comments) rather than one candidate per comment - this is the direct
implementation of Part 9's "20 Reddit comments from one thread are NOT 20 independent
sources": the reduction happens here, at discovery, before anything downstream could
ever be tempted to count comments as independent evidence.

IMPORTANT DEPLOYMENT FINDING (hardening pass, deployment validation Part 9): both
reddit.com/robots.txt and old.reddit.com/robots.txt currently disallow ALL automated
access ("User-agent: * / Disallow: /"), pointing crawlers at Reddit's Public Content
Policy instead. This adapter correctly RESPECTS that (via _robots_allows() - Part 6
forbids uncontrolled scraping, full stop), which means discover_reddit() will return
[] from ANY network, not just this sandbox - this is not something re-running from a
"real" deployment network fixes. Genuine Reddit discovery requires migrating to
Reddit's official, authenticated API (OAuth2 + praw, or direct OAuth calls), which is
a sanctioned access path governed by Reddit's API Terms rather than the website's
robots.txt - a concrete follow-up item, not a network/environment issue.

SUBSTACK: Substack has no public, unauthenticated search API. Rather than scrape an
undocumented endpoint (Part 6 explicitly forbids uncontrolled scraping), this adapter
discovers from a small, explicit, operator-configured list of publication RSS/Atom
feed URLs (PDI_SUBSTACK_SEED_FEEDS env var, comma-separated) - every Substack
publication exposes a public /feed endpoint for exactly this kind of consumption, so
this is unambiguously within the provider's own intended use. With no seeds
configured (the honest default in this environment - see the implementation report's
KNOWN LIMITATIONS), the adapter returns no candidates rather than fabricating any.

Both adapters:
  - respect robots.txt (same urllib.robotparser pattern as source_enrichment.py)
  - use the same USER_AGENT / REQUEST_TIMEOUT conventions as source_enrichment.py
  - never raise past their own boundary - pdi.run_discovery() also catches per-adapter
    exceptions, but each adapter additionally fails closed internally so a partial
    failure (e.g. one bad feed) never loses candidates from a good one.
"""
from __future__ import annotations

import html
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import urllib.robotparser as robotparser

from pdi import Candidate

USER_AGENT = "Mozilla/5.0 (compatible; PakshBot/1.0; +https://paksh.news) PDI/1.0"
REQUEST_TIMEOUT = 8
CRAWL_DELAY_SECONDS = 1.0
MAX_RESPONSE_BYTES = 3_000_000

_robots_cache = {}
_last_request_at = {}


def _robots_allows(url):
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = robotparser.RobotFileParser()
        try:
            resp = requests.get(origin + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots_cache[origin] = rp
    try:
        return _robots_cache[origin].can_fetch(USER_AGENT, url)
    except Exception:
        return True   # a malformed robots.txt must not block a legitimate, otherwise-allowed fetch


def _respect_crawl_delay(domain):
    last = _last_request_at.get(domain)
    now = time.time()
    if last is not None:
        elapsed = now - last
        if elapsed < CRAWL_DELAY_SECONDS:
            time.sleep(CRAWL_DELAY_SECONDS - elapsed)
    _last_request_at[domain] = time.time()


def _get(url, params=None):
    domain = urlparse(url).netloc
    if not _robots_allows(url):
        return None
    _respect_crawl_delay(domain)
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
                         stream=True)
    content = resp.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
    if len(content) > MAX_RESPONSE_BYTES:
        content = content[:MAX_RESPONSE_BYTES]
    resp._content = content
    return resp


# =====================================================================================
# Reddit
# =====================================================================================

REDDIT_SEARCH_URL = "https://old.reddit.com/search.json"
REDDIT_MAX_REPRESENTATIVE_COMMENTS = 5   # a large thread -> a handful of representative
                                          # top-level comments, never one-per-comment


def _reddit_post_to_candidate(post, query_text, rank):
    d = post.get("data", {})
    created = d.get("created_utc")
    published_at = None
    if created is not None:
        try:
            published_at = datetime.fromtimestamp(float(created), tz=timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        except Exception:
            published_at = None
    permalink = d.get("permalink") or ""
    url = f"https://old.reddit.com{permalink}" if permalink else d.get("url", "")
    body = (d.get("selftext") or "")[:4000]
    return Candidate(
        provider="reddit", provider_item_id=d.get("id") or permalink,
        url=url, canonical_url=url, title=d.get("title") or "",
        author=d.get("author") or "unknown", published_at=published_at,
        language=None, discovery_query=query_text, discovery_rank=rank,
        content_hash="", body_text=body,
        engagement={"score": d.get("score", 0), "num_comments": d.get("num_comments", 0),
                    "subreddit": d.get("subreddit")},
    )


def discover_reddit(query, limit=8):
    """query: pdi.Query. Returns list[Candidate]. Engagement (score/num_comments) is
    attached only as a discovery-time signal for the adapter's own representative-
    comment selection below - it is never treated as evidence strength downstream
    (Part 9); pdi.py's association/quality stages never read candidate.engagement."""
    try:
        resp = _get(REDDIT_SEARCH_URL, params={"q": query.text, "limit": max(limit, 5), "sort": "relevance"})
    except Exception:
        return []
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []   # e.g. an HTML interstitial/consent page instead of JSON - fail closed, not a crash
    children = (data.get("data") or {}).get("children") or []
    out = []
    for rank, post in enumerate(children[:limit]):
        try:
            out.append(_reddit_post_to_candidate(post, query.text, rank))
        except Exception:
            continue
    # Thread-to-representative-observation reduction (Part 9/20 case 4 "massive Reddit
    # thread"): for the single highest-engagement thread found, pull a BOUNDED number of
    # its own top-level comments as separate, clearly-provenanced candidates - never all
    # of them, and never presented as more than what they are (individual comments, not
    # independent sources - association/independence scoring downstream treats every
    # candidate as one vote regardless of the thread's total comment count).
    if out:
        top_thread = max(out, key=lambda c: c.engagement.get("num_comments", 0))
        if top_thread.engagement.get("num_comments", 0) >= 20:
            try:
                out.extend(_reddit_top_comments(top_thread, query.text))
            except Exception:
                pass
    return out


def _reddit_top_comments(thread_candidate, query_text):
    url = thread_candidate.url.rstrip("/") + ".json"
    resp = _get(url, params={"limit": REDDIT_MAX_REPRESENTATIVE_COMMENTS, "sort": "top"})
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    if not isinstance(data, list) or len(data) < 2:
        return []
    listing = data[1].get("data", {}).get("children", [])
    out = []
    for rank, item in enumerate(listing[:REDDIT_MAX_REPRESENTATIVE_COMMENTS]):
        d = item.get("data", {})
        body = d.get("body") or ""
        if not body or body in ("[deleted]", "[removed]"):
            continue
        created = d.get("created_utc")
        published_at = None
        if created is not None:
            try:
                published_at = datetime.fromtimestamp(float(created), tz=timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
            except Exception:
                pass
        out.append(Candidate(
            provider="reddit", provider_item_id=d.get("id") or f"{thread_candidate.provider_item_id}-c{rank}",
            url=f"https://old.reddit.com{d.get('permalink', '')}" or thread_candidate.url,
            canonical_url="", title=f"comment on: {thread_candidate.title}"[:120],
            author=d.get("author") or "unknown", published_at=published_at, language=None,
            discovery_query=query_text, discovery_rank=100 + rank, content_hash="", body_text=body[:2000],
            engagement={"score": d.get("score", 0)},
        ))
    return out


# =====================================================================================
# Substack (RSS/Atom feed based - see module docstring for why)
# =====================================================================================

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_CONTENT_ENCODED_TAG = "{http://purl.org/rss/1.0/modules/content/}encoded"

_HTML_TAG_RX = re.compile(r"<[^>]+>")
_HTML_SCRIPT_STYLE_RX = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_HTML_WS_RX = re.compile(r"[ \t]+")
_HTML_BLANKLINES_RX = re.compile(r"\n\s*\n+")


def _strip_html(raw):
    """Minimal stdlib-only HTML->text (no new dependency - same module convention as
    the rest of this file): drops script/style bodies, strips remaining tags, decodes
    entities, collapses whitespace. Not a full HTML parser - good enough to turn a
    Substack post's <content:encoded>/Atom <content> into plain text for the
    deterministic jaccard association in pdi.py, which already only ever worked on
    plain text anyway (title + short RSS <description>)."""
    if not raw:
        return ""
    text = _HTML_SCRIPT_STYLE_RX.sub(" ", raw)
    text = _HTML_TAG_RX.sub(" ", text)
    text = html.unescape(text)
    text = _HTML_WS_RX.sub(" ", text)
    text = _HTML_BLANKLINES_RX.sub("\n\n", text)
    return text.strip()


def _seed_feeds():
    raw = os.environ.get("PDI_SUBSTACK_SEED_FEEDS", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def _parse_feed(xml_text):
    """Minimal, defensive RSS 2.0 / Atom parser (stdlib only - no new dependency).
    Returns a list of {title, link, author, published_at, summary, content}.
    'summary' is the feed's short <description>/<summary> element (a subtitle on
    Substack, typically well under 300 characters). 'content' is the full post body
    from <content:encoded> (RSS) / <content> (Atom) when the feed provides it, raw
    HTML, or "" when absent - discover_substack() is what strips/caps/falls back on
    this, not this parser (this function stays a pure, presentation-free feed reader)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for item in root.iter("item"):   # RSS 2.0
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "author": (item.findtext("author") or item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip(),
            "published_at": _rfc822_to_iso(item.findtext("pubDate")),
            "summary": (item.findtext("description") or "").strip(),
            "content": item.findtext(_CONTENT_ENCODED_TAG) or "",
            "guid": (item.findtext("guid") or item.findtext("link") or "").strip(),
        })
    for entry in root.iter(f"{_ATOM_NS}entry"):   # Atom
        link_el = entry.find(f"{_ATOM_NS}link")
        items.append({
            "title": (entry.findtext(f"{_ATOM_NS}title") or "").strip(),
            "link": link_el.get("href") if link_el is not None else "",
            "author": (entry.findtext(f"{_ATOM_NS}author/{_ATOM_NS}name") or "").strip(),
            "published_at": _rfc822_to_iso(entry.findtext(f"{_ATOM_NS}updated") or entry.findtext(f"{_ATOM_NS}published")),
            "summary": (entry.findtext(f"{_ATOM_NS}summary") or "").strip(),
            "content": entry.findtext(f"{_ATOM_NS}content") or "",
            "guid": (entry.findtext(f"{_ATOM_NS}id") or "").strip(),
        })
    return items


def _rfc822_to_iso(s):
    if not s:
        return None
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.isoformat(timespec="seconds")
    except Exception:
        try:
            return datetime.fromisoformat(s.replace("Z", "")).isoformat(timespec="seconds")
        except Exception:
            return None


_TOKEN_RX = re.compile(r"[a-z0-9ऀ-ॿ]+")   # same Devanagari range as pdi._tokens() -
                                                     # ASCII-only here was a real, confirmed
                                                     # DISCOVERY-layer bug (audited separately
                                                     # from association): a Devanagari title/
                                                     # summary tokenizes to the empty set against
                                                     # this old pattern, so q_tokens & title_tokens
                                                     # can never be non-empty for a Hindi item
                                                     # against an English query - it never became
                                                     # a Candidate at all, regardless of relevance.
                                                     # pdi.py's own association layer already
                                                     # tokenizes Devanagari correctly; only this
                                                     # separate overlap-matching regex did not.


def discover_substack(query, limit=8):
    """Fetches each configured seed feed (bounded, robots-compliant) and keeps items
    whose title/summary lexically overlap the query text. With no seeds configured,
    returns [] - an honest empty result, not a fabricated one (see module docstring)."""
    feeds = _seed_feeds()
    if not feeds:
        return []
    q_tokens = set(_TOKEN_RX.findall(query.text.lower()))
    out = []
    for feed_url in feeds:
        try:
            resp = _get(feed_url)
        except Exception:
            continue
        if resp is None or resp.status_code != 200:
            continue
        for item in _parse_feed(resp.text):
            title_tokens = set(_TOKEN_RX.findall((item["title"] + " " + item["summary"]).lower()))
            if not (q_tokens & title_tokens):
                continue
            # Prefer the full post body (<content:encoded>/Atom <content>) when the feed
            # provides one - Substack's <description> is only a short subtitle (see the
            # real-Substack shadow experiment's finding: 35-234 chars vs. 26k-213k chars
            # of actual content). Falls back to the existing description-only behavior
            # when a feed has no full-content element, so nothing regresses for feeds
            # that never had one.
            full_text = _strip_html(item["content"])
            body_text = (full_text or item["summary"])[:4000]
            out.append(Candidate(
                provider="substack", provider_item_id=item["guid"] or item["link"],
                url=item["link"], canonical_url=item["link"], title=item["title"],
                author=item["author"] or "unknown", published_at=item["published_at"], language=None,
                discovery_query=query.text, discovery_rank=len(out), content_hash="",
                body_text=body_text,
            ))
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    return out


PROVIDERS = {
    "reddit": discover_reddit,
    "substack": discover_substack,
}
