"""
source_enrichment.py - Phase 22C: additive, cached, direct-URL metadata
enrichment for thin/empty article summaries.

Validated by Phase 22A (source-depth forensic: 21.4% of articles have empty
summaries, median non-empty summary is 95 chars) and Phase 22B (a 75-event
stratified benchmark + blind generation A/B: enriched preferred 9/13, no
hallucinations, no L/C/R regression, prompt-injection resistant). Phase 22B's
verdict was LIMITED INTEGRATION - a narrow trigger, not blanket replacement:
information-gain analysis showed 74.8% of enrichments were merely duplicative
when the RSS summary already had *something*, so this module never fetches
when the existing summary already clears a "usable" length, and never
replaces existing text - only appends, and only when genuinely novel.

CORE INVARIANT: articles.summary is NEVER rewritten by this module. It reads
the articles table, writes ONLY to its own additive article_enrichment
table, and returns a derived combined_summary string for the CALLER
(analyze.py::build_prompt()) to use - the stored row is untouched either way.

Fails closed throughout: any fetch failure, quality-gate rejection, cache
corruption, or unexpected exception falls through to the original,
unmodified article summary. Enrichment can only ever ADD to what generation
sees, never remove or block it.
"""

from __future__ import annotations

import re
import time
import html as _html
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
import urllib.robotparser as robotparser

import requests

import database  # read-only reuse of get_connection() + the articles table read path

EXTRACTION_VERSION = "phase22c-meta-v1"
GENERATOR_NAME = "source_enrichment"

USER_AGENT = "Mozilla/5.0 (compatible; PakshBot/1.0; +https://paksh.news)"
REQUEST_TIMEOUT = 8
MAX_RESPONSE_BYTES = 3_000_000  # 3MB - a normal article page is a few hundred KB
MAX_REDIRECTS = 5
CRAWL_DELAY_SECONDS = 1.0
FAILURE_COOLDOWN_DAYS = 30

# Phase 22A's own established "usable source" threshold (>=100 chars). Reused
# here, not reinvented, as the pre-fetch eligibility trigger: an existing
# summary at or above this length is already "usable" and Phase 22B's
# information-gain data showed fetching for it is usually wasted (74.8%
# duplicative) - so the network request is skipped entirely, not just the
# combination step. This is what keeps the non-qualifying path fast (Section 29).
THIN_SUMMARY_THRESHOLD = 100

# Phase 22B's validated novelty bar for whether to actually COMBINE a fetched
# description with the existing summary, vs. keep the existing summary as-is.
NOVELTY_THRESHOLD = 0.5

_STOP = set("the a an of to in on for and or is are was were with by from as at that this it its "
            "will has have had be being not no so but if than then which who what when where "
            "into out up down over under again more most other some such only own same can could "
            "would should may might".split())

_robots_cache: dict = {}
_last_request_at: dict = {}


@dataclass
class FetchResult:
    status: str  # "accepted" | "rejected" | "failure" | "skipped"
    source_url: str
    canonical_url: Optional[str] = None
    metadata_description: Optional[str] = None
    extraction_method: Optional[str] = None
    failure_reason: Optional[str] = None


# --------------------------------------------------------------------------
# Cache schema (additive only - never touches articles/events). Same pattern
# as story_memory.py: this module owns its own migration, never woven into
# database.py's own init_db(), so a bug here cannot affect the core schema
# every production script depends on.
# --------------------------------------------------------------------------

def init_enrichment_schema(conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = database.get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS article_enrichment (
            article_id           INTEGER PRIMARY KEY,
            source_url             TEXT,
            canonical_url            TEXT,
            status                   TEXT NOT NULL,   -- accepted|rejected|failure|skipped
            metadata_description       TEXT,
            extraction_method            TEXT,
            retrieved_at                   TEXT NOT NULL,
            extraction_version               TEXT NOT NULL,
            failure_reason                     TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_article_enrichment_status "
                 "ON article_enrichment(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_article_enrichment_version "
                 "ON article_enrichment(extraction_version)")
    conn.commit()
    if owns_conn:
        conn.close()


# --------------------------------------------------------------------------
# Eligibility (Section 7) - direct URL only, never news.google.com, never
# a redirect-resolution attempt.
# --------------------------------------------------------------------------

def is_eligible_url(url: Optional[str]) -> bool:
    if not url:
        return False
    if "news.google.com" in url:
        return False
    return url.startswith("http://") or url.startswith("https://")


def should_attempt_fetch(url: Optional[str], existing_summary: Optional[str]) -> bool:
    """The PRE-FETCH trigger (Section 8) - deterministic, based only on what's
    already known (URL shape + existing summary length), never on
    new_token_fraction, which is only knowable after a fetch. Conservative:
    empty or below Phase 22A's own 'usable' threshold only."""
    if not is_eligible_url(url):
        return False
    length = len(existing_summary or "")
    return length < THIN_SUMMARY_THRESHOLD


# --------------------------------------------------------------------------
# Robots + rate limiting (Sections 10, 12)
# --------------------------------------------------------------------------

def _robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = robotparser.RobotFileParser()
        try:
            resp = requests.get(origin + "/robots.txt", headers={"User-Agent": USER_AGENT},
                                 timeout=REQUEST_TIMEOUT)
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots_cache[origin] = rp
    return _robots_cache[origin].can_fetch(USER_AGENT, url)


def _respect_crawl_delay(domain: str):
    last = _last_request_at.get(domain)
    now = time.time()
    if last is not None:
        elapsed = now - last
        if elapsed < CRAWL_DELAY_SECONDS:
            time.sleep(CRAWL_DELAY_SECONDS - elapsed)
    _last_request_at[domain] = time.time()


# --------------------------------------------------------------------------
# Metadata extraction only (Section 9) - og:description -> meta description.
# No articleBody, no CSS selectors, no paragraph text.
# --------------------------------------------------------------------------

_OG_DESC_RE = re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\']', re.I)
_META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', re.I)
_CANONICAL_RE = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)["\']', re.I)


def _extract_metadata(html_text: str):
    m = _OG_DESC_RE.search(html_text)
    if m:
        return _html.unescape(m.group(1)).strip(), "og:description"
    m = _META_DESC_RE.search(html_text)
    if m:
        return _html.unescape(m.group(1)).strip(), "meta:description"
    return None, None


def _extract_canonical(html_text: str, fallback_url: str):
    m = _CANONICAL_RE.search(html_text)
    return m.group(1).strip() if m else fallback_url


# --------------------------------------------------------------------------
# Quality gate (Section 13) - multilingual (Latin + Devanagari). Ported,
# corrected, from Phase 22B: the initial gate only counted Latin-script
# tokens, silently rejecting genuine, well-formed Hindi descriptions as
# "too_few_words" (0% acceptance on Navbharat Times/Jagran/Amar Ujala until
# fixed; 75-100% after). That regression must never reoccur - see
# test_source_enrichment.py's explicit Hindi regression tests.
# --------------------------------------------------------------------------

_BOILERPLATE_PATTERNS = [
    r"^\s*$", r"cookie", r"we use cookies", r"privacy policy", r"subscribe (now|today)",
    r"sign up for", r"log ?in to continue", r"create a free account", r"advertisement",
    r"javascript is (disabled|required)", r"enable javascript", r"page not found", r"error 404",
    r"^home\s*[\|\-]", r"latest news", r"breaking news$", r"click here",
]
_BOILERPLATE_RE = re.compile("|".join(_BOILERPLATE_PATTERNS), re.I)


def _content_tokens(text: str) -> tuple[set, set]:
    latin = set(re.findall(r"[a-z]{3,}", (text or "").lower())) - _STOP
    deva = set(re.findall(r"[ऀ-ॿ]{2,}", text or ""))
    return latin, deva


def quality_gate(candidate: Optional[str], title: str) -> tuple[bool, Optional[str]]:
    if not candidate or not candidate.strip():
        return False, "empty"
    text = candidate.strip()
    if len(text) < 30:
        return False, "implausibly_short"
    if len(text) > 500:
        return False, "implausibly_long"
    if _BOILERPLATE_RE.search(text):
        return False, "boilerplate_pattern"
    norm_title = re.sub(r"[^a-z0-9ऀ-ॿ]", "", (title or "").lower())
    norm_cand = re.sub(r"[^a-z0-9ऀ-ॿ]", "", text.lower())
    if norm_title and norm_cand and (norm_title == norm_cand
                                      or (norm_title in norm_cand and len(norm_cand) < len(norm_title) + 10)):
        return False, "duplicates_title"
    latin, deva = _content_tokens(text)
    if len(latin) + len(deva) < 6:
        return False, "too_few_words"
    return True, None


# --------------------------------------------------------------------------
# Information gain / novelty (Section 15) - reused from Phase 22B's
# validated methodology. Only decides whether to COMBINE, never whether to
# fetch (that's should_attempt_fetch, a pre-fetch, existing-summary-only rule).
# --------------------------------------------------------------------------

def new_token_fraction(existing: str, candidate: str) -> float:
    e_latin, e_deva = _content_tokens(existing)
    c_latin, c_deva = _content_tokens(candidate)
    existing_tokens = e_latin | e_deva
    candidate_tokens = c_latin | c_deva
    if not candidate_tokens:
        return 0.0
    overlap = len(existing_tokens & candidate_tokens) / len(candidate_tokens)
    return round(1 - overlap, 3)


def combined_summary(existing: str, candidate: str) -> str:
    """Additive only (Section 14/16/17): the original summary is always the
    base; the candidate is appended, never substituted, so a concrete detail
    already present in RSS can never be silently dropped because a fetched
    description phrased it differently or omitted it."""
    existing = (existing or "").strip()
    candidate = (candidate or "").strip()
    if not existing:
        return candidate
    if not candidate:
        return existing
    return f"{existing} {candidate}"


# --------------------------------------------------------------------------
# The actual fetch (network-bound, Sections 10-12)
# --------------------------------------------------------------------------

def _fetch(url: str, title: str) -> FetchResult:
    if not is_eligible_url(url):
        return FetchResult(status="skipped", source_url=url, failure_reason="ineligible_url")
    domain = urlparse(url).netloc
    try:
        if not _robots_allows(url):
            return FetchResult(status="rejected", source_url=url, failure_reason="robots_disallowed")
    except Exception as e:
        return FetchResult(status="failure", source_url=url, failure_reason=f"robots_check_error:{type(e).__name__}")

    _respect_crawl_delay(domain)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
                             stream=True, allow_redirects=True)
        if len(resp.history) > MAX_REDIRECTS:
            return FetchResult(status="failure", source_url=url, failure_reason="too_many_redirects")
        content = b""
        for chunk in resp.iter_content(chunk_size=65536):
            content += chunk
            if len(content) > MAX_RESPONSE_BYTES:
                return FetchResult(status="failure", source_url=url, failure_reason="response_too_large")
        html_text = content.decode(resp.encoding or "utf-8", errors="replace")
    except requests.exceptions.Timeout:
        return FetchResult(status="failure", source_url=url, failure_reason="timeout")
    except Exception as e:
        return FetchResult(status="failure", source_url=url, failure_reason=f"request_error:{type(e).__name__}")

    if resp.status_code != 200:
        return FetchResult(status="failure", source_url=url, failure_reason=f"http_{resp.status_code}")

    canonical = _extract_canonical(html_text, url)
    desc, method = _extract_metadata(html_text)
    ok, reason = quality_gate(desc, title)
    if not ok:
        return FetchResult(status="rejected", source_url=url, canonical_url=canonical,
                            metadata_description=desc, extraction_method=method, failure_reason=reason)
    return FetchResult(status="accepted", source_url=url, canonical_url=canonical,
                        metadata_description=desc, extraction_method=method)


# --------------------------------------------------------------------------
# Cache read/write (Sections 4-6, 20)
# --------------------------------------------------------------------------

def _cache_get(conn, article_id: int):
    try:
        row = conn.execute("SELECT * FROM article_enrichment WHERE article_id=?", (article_id,)).fetchone()
    except Exception:
        return None  # table missing/corrupt -> treat as no cache, fail closed
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        return None  # malformed row -> ignore, fail closed (Section 20)


def _cache_put(conn, article_id: int, url: str, result: FetchResult):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO article_enrichment "
        "(article_id, source_url, canonical_url, status, metadata_description, "
        " extraction_method, retrieved_at, extraction_version, failure_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (article_id, url, result.canonical_url, result.status, result.metadata_description,
         result.extraction_method, now, EXTRACTION_VERSION, result.failure_reason),
    )
    conn.commit()


def _cache_is_stale(row: dict) -> bool:
    """A cached row is stale (eligible for re-fetch) if it was written under
    a superseded extraction_version, or if it's a failure/rejection older
    than the cooldown window (Section 5/6)."""
    if row.get("extraction_version") != EXTRACTION_VERSION:
        return True
    if row.get("status") in ("failure", "rejected"):
        try:
            retrieved = datetime.fromisoformat(row["retrieved_at"])
            if retrieved.tzinfo is None:
                retrieved = retrieved.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - retrieved > timedelta(days=FAILURE_COOLDOWN_DAYS)
        except Exception:
            return True  # malformed timestamp -> treat as stale, safe to re-check
    return False


# --------------------------------------------------------------------------
# The one function analyze.py calls (Section 18) - the entire integration
# surface. Never raises; any failure degrades to the article's own summary.
# --------------------------------------------------------------------------

def get_combined_summary_for_article(article: dict, conn=None) -> str:
    """article: a dict with at least id, url, title, summary (the shape
    database.get_event_articles()/get_articles_for_events() already return).
    Returns a string - the original summary, unchanged, unless a cached or
    freshly-fetched enrichment was accepted AND cleared the novelty bar, in
    which case the two are combined additively. NEVER writes to
    articles.summary - this is a derived, in-memory value only."""
    existing = article.get("summary") or ""
    try:
        article_id = article.get("id")
        url = article.get("url")
        title = article.get("title") or ""
        if article_id is None:
            return existing

        owns_conn = conn is None
        if owns_conn:
            conn = database.get_connection()
        try:
            init_enrichment_schema(conn)
            cached = _cache_get(conn, article_id)

            if cached is not None and not _cache_is_stale(cached):
                result = FetchResult(status=cached["status"], source_url=cached["source_url"],
                                      canonical_url=cached["canonical_url"],
                                      metadata_description=cached["metadata_description"],
                                      extraction_method=cached["extraction_method"],
                                      failure_reason=cached["failure_reason"])
            elif should_attempt_fetch(url, existing):
                result = _fetch(url, title)
                try:
                    _cache_put(conn, article_id, url, result)
                except Exception:
                    pass  # cache write failure must not block generation either
            else:
                return existing  # doesn't qualify - fast path, no network, no cache write

            if result.status != "accepted" or not result.metadata_description:
                return existing
            frac = new_token_fraction(existing, result.metadata_description)
            if frac < NOVELTY_THRESHOLD:
                return existing  # accepted but duplicative - Phase 22B's core finding
            return combined_summary(existing, result.metadata_description)
        finally:
            if owns_conn:
                conn.close()
    except Exception:
        return existing  # absolute fail-closed backstop - generation must never break
