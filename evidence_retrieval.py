"""
evidence_retrieval.py - Evidence Retrieval v2: BOUNDED retrieval of a little article text, only when Story Intelligence
cannot decide from the ~100-character excerpts Paksh stores. It is not a crawler.

What it is:   a polite, budgeted fetch of ONE article page at a time (the article's own direct URL), a small stdlib HTML
              extractor that keeps a short lede (<= MAX_TEXT characters), and a failure-aware cache in its own table.
What it is not: it never resolves news.google.com redirect links, never logs in, never defeats a paywall / bot check /
              robots.txt, never uses a browser, never retries aggressively, never stores raw HTML, and the text it keeps is
              for internal analysis only (nothing here is published or shown to readers).

Reused from source_enrichment.py (Phase 22C, the only earlier fetcher): the PakshBot User-Agent and the "direct URL only,
never news.google.com" rule. That module fetches meta descriptions only and is left untouched; this one adds redirect
validation, a private-address guard, robots TTL, a total per-fetch deadline and body-text extraction.

Every function here fails closed: a failed fetch or extraction returns a status, never an exception, and a good cached
extraction is never overwritten by a later failure.
"""
import hashlib
import html as _html
import ipaddress
import json
import re
import socket
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

EXTRACTOR_VERSION = "ev-extract-3"
USER_AGENT = "Mozilla/5.0 (compatible; PakshBot/1.0; +https://paksh.news)"     # same identity as source_enrichment.py

# ---- limits (small on purpose; see docs/PHASE11 for how they were chosen) ----
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 8
FETCH_DEADLINE_S = 15            # total wall time for one page, headers + body
MAX_BYTES = 1_500_000            # response body cap
MAX_TEXT = 2000                  # characters of extracted article text kept per article
MIN_USABLE_TEXT = 200            # below this the extraction is 'short' and never used as evidence
MAX_REDIRECTS = 4
DOMAIN_DELAY_S = 1.5             # minimum gap between two requests to one host
ROBOTS_TTL_S = 24 * 3600
ROBOTS_MAX_BYTES = 200_000
TTL_OK = timedelta(days=30)
TTL_FAILED = timedelta(days=3)       # timeouts, 5xx, connection errors
TTL_BLOCKED = timedelta(days=30)     # robots, 401/402/403/451, bot protection, paywall marker
TTL_GONE = timedelta(days=30)        # 404 / 410 / not html

_last_request = {}
_robots = {}                          # origin -> (fetched_at_epoch, RobotFileParser | None(=unreadable))


# =====================================================================================
# URL policy
# =====================================================================================

def is_eligible_url(url):
    """The article's OWN url only. news.google.com links (about 2/3 of the corpus) are redirect wrappers whose real target is
    only obtainable by decoding/calling Google's service; that is deliberately not attempted."""
    if not url or not isinstance(url, str):
        return False, "no_url"
    try:
        p = urlparse(url.strip())
    except Exception:
        return False, "unparseable_url"
    if p.scheme not in ("http", "https"):
        return False, "scheme_not_http"
    if not p.hostname or p.username or p.password:
        return False, "bad_host_or_userinfo"
    if p.hostname.lower().endswith("news.google.com") or p.hostname.lower() == "google.com":
        return False, "google_news_redirect_url"
    return True, None


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _ip_is_public(ip):
    """Public-address test. IPv6 forms that merely CARRY an IPv4 address (NAT64 64:ff9b::/96, IPv4-mapped ::ffff:a.b.c.d) are judged
    by that embedded IPv4 - some networks (this one) resolve every public host through NAT64, and those must not be mistaken for
    private space."""
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in _NAT64:
            ip = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _host_is_public(host):
    """Reject loopback / private / link-local / reserved addresses (literals and anything the name resolves to)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
        if not _ip_is_public(ip):
            return False
    return bool(infos)


def _wait_domain(host):
    last = _last_request.get(host)
    if last is not None:
        gap = time.time() - last
        if gap < DOMAIN_DELAY_S:
            time.sleep(DOMAIN_DELAY_S - gap)
    _last_request[host] = time.time()


# =====================================================================================
# robots.txt
# =====================================================================================

def robots_allows(url, session):
    """True/False, or None when robots.txt could not be read this time (5xx / timeout): the caller then does NOT fetch."""
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    now = time.time()
    hit = _robots.get(origin)
    if hit is None or now - hit[0] > ROBOTS_TTL_S:
        rp = robotparser.RobotFileParser()
        try:
            _wait_domain(p.hostname)
            r = session.get(origin + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                            allow_redirects=False, stream=True)
            if r.status_code == 200:
                body = b""
                for chunk in r.iter_content(65536):
                    body += chunk
                    if len(body) > ROBOTS_MAX_BYTES:
                        break
                rp.parse(body.decode("utf-8", "replace").splitlines())
                hit = (now, rp)
            elif 400 <= r.status_code < 500 or 300 <= r.status_code < 400:
                rp.parse([])                                   # no robots.txt (or redirected away): nothing forbids
                hit = (now, rp)
            else:
                hit = (now, None)                              # 5xx: unreadable -> do not fetch now
        except Exception:
            hit = (now, None)
        _robots[origin] = hit
    rp = hit[1]
    if rp is None:
        return None
    return rp.can_fetch(USER_AGENT, url) and rp.can_fetch("PakshBot", url)


# =====================================================================================
# Fetch
# =====================================================================================

@dataclass
class FetchResult:
    url: str
    status: str                    # ok | blocked | failed | skipped
    http_status: int = None
    final_url: str = None
    html: str = None
    error_class: str = None
    nbytes: int = 0
    ttl: timedelta = TTL_FAILED
    seconds: float = 0.0
    requests_made: int = 0


_BOT_MARKERS = re.compile(r"(cf-chl|just a moment\.\.\.|attention required|captcha|access denied|are you a robot|"
                          r"enable javascript and cookies|please verify you are (a )?human)", re.I)


def _decode(body, r):
    """requests guesses ISO-8859-1 for text/html WITHOUT a charset header, which turns UTF-8 apostrophes into mojibake. Honour an
    explicit charset; otherwise try UTF-8 first, then the statistical detector, then latin-1."""
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "charset=" in ctype:
        try:
            return body.decode(ctype.split("charset=")[1].split(";")[0].strip(" '\""), errors="replace")
        except (LookupError, ValueError):
            pass
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        import charset_normalizer
        best = charset_normalizer.from_bytes(body).best()
        if best is not None:
            return str(best)
    except Exception:
        pass
    return body.decode("latin-1", errors="replace")


def fetch_page(url, session=None, deadline_s=FETCH_DEADLINE_S):
    """One bounded, polite page fetch. Never raises. No retries. Manual redirects so EVERY hop is validated."""
    t0 = time.time()
    res = FetchResult(url=url, status="skipped")
    ok, why = is_eligible_url(url)
    if not ok:
        res.error_class = why
        res.ttl = TTL_GONE
        return res
    import requests
    session = session or requests.Session()
    cur = url.strip()
    try:
        for hop in range(MAX_REDIRECTS + 1):
            p = urlparse(cur)
            if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
                res.status, res.error_class, res.ttl = "skipped", "unsafe_redirect_target", TTL_BLOCKED
                return res
            if hop and p.scheme == "http" and urlparse(url).scheme == "https":
                res.status, res.error_class, res.ttl = "skipped", "https_downgrade_redirect", TTL_BLOCKED
                return res
            if not _host_is_public(p.hostname):
                res.status, res.error_class, res.ttl = "skipped", "non_public_address", TTL_BLOCKED
                return res
            allow = robots_allows(cur, session)
            if allow is None:
                res.status, res.error_class, res.ttl = "failed", "robots_unreadable", TTL_FAILED
                return res
            if allow is False:
                res.status, res.error_class, res.ttl = "blocked", "robots_disallowed", TTL_BLOCKED
                return res
            if time.time() - t0 > deadline_s:
                res.status, res.error_class = "failed", "deadline"
                return res
            _wait_domain(p.hostname)
            r = session.get(cur, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
                            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False, stream=True)
            res.requests_made += 1
            res.http_status = r.status_code
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location")
                r.close()
                if not loc:
                    res.status, res.error_class = "failed", "redirect_without_location"
                    return res
                cur = urljoin(cur, loc)
                continue
            res.final_url = cur
            if r.status_code in (401, 402, 403, 451):
                r.close()
                res.status, res.error_class, res.ttl = "blocked", f"http_{r.status_code}", TTL_BLOCKED
                return res
            if r.status_code == 429:
                r.close()
                res.status, res.error_class, res.ttl = "failed", "http_429", timedelta(days=1)
                return res
            if r.status_code in (404, 410):
                r.close()
                res.status, res.error_class, res.ttl = "failed", f"http_{r.status_code}", TTL_GONE
                return res
            if r.status_code != 200:
                r.close()
                res.status, res.error_class = "failed", f"http_{r.status_code}"
                return res
            ctype = (r.headers.get("Content-Type") or "").lower()
            if ctype and "html" not in ctype and "xml" not in ctype:
                r.close()
                res.status, res.error_class, res.ttl = "failed", "not_html", TTL_GONE
                return res
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    r.close()
                    res.status, res.error_class, res.ttl = "failed", "response_too_large", TTL_GONE
                    res.nbytes = len(body)
                    return res
                if time.time() - t0 > deadline_s:
                    r.close()
                    res.status, res.error_class = "failed", "deadline"
                    return res
            res.nbytes = len(body)
            text = _decode(body, r)
            if _BOT_MARKERS.search(text[:4000]) and len(text) < 40_000:
                res.status, res.error_class, res.ttl = "blocked", "bot_protection_or_interstitial", TTL_BLOCKED
                return res
            res.status, res.html, res.ttl = "ok", text, TTL_OK
            return res
        res.status, res.error_class = "failed", "too_many_redirects"
        return res
    except Exception as e:                                        # noqa: BLE001 - fetching must never raise
        res.status, res.error_class = "failed", f"{type(e).__name__}"
        return res
    finally:
        res.seconds = time.time() - t0


# =====================================================================================
# Extraction (stdlib only: no bs4 / lxml / trafilatura are installed and none is added)
# =====================================================================================

_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "iframe", "button", "select", "template"}
_SKIP_ATTR = re.compile(r"(^|[\s_-])(ad|ads|advert\w*|cookie\w*|consent|banner|promo\w*|related|recommend\w*|newsletter|share|social|"
                        r"comment\w*|subscribe\w*|paywall|sidebar|breadcrumb\w*|menu|widget|popup|modal)($|[\s_-])", re.I)
_BOILER = re.compile(r"(read more|also read|follow us|subscribe|subscription|sign up|sign in|log in to|already a subscriber|share this|"
                     r"all rights reserved|copyright|advertisement|click here|download the app|whatsapp|join our|terms of use|"
                     r"privacy policy|cookie|digital access|save now|free app|breaking news email|live blog for latest|unlock|"
                     r"premium content|register to read|©)", re.I)
_VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "param", "source", "track", "wbr"}


_LIVEBLOG = re.compile(r"(live (updates|blog|coverage|stream|tracker)|liveblog|share price|stock price|latest news today|top headlines)", re.I)
_LIVEBLOG_URL = re.compile(r"(/live[-/]|-live-|/liveblog|live-updates|/live$)", re.I)


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []                 # (tag, skipped, in_article)
        self.skip = 0
        self.article_depth = 0
        self.title = ""
        self._in_title = False
        self.meta = {}
        self.canonical = None
        self.jsonld = []
        self._in_jsonld = False
        self._jsonld_buf = []
        self._p = None
        self.p_article, self.p_all = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k and a.get("content"):
                self.meta.setdefault(k, a["content"].strip())
        if tag == "link" and (a.get("rel") or "").lower() == "canonical" and a.get("href"):
            self.canonical = a["href"].strip()
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld, self._jsonld_buf = True, []
        if tag in _VOID:
            return
        skipped = tag in _SKIP_TAGS or bool(_SKIP_ATTR.search((a.get("class") or "") + " " + (a.get("id") or "")))
        in_art = tag in ("article", "main") or (tag == "div" and (a.get("itemprop") or "").lower() == "articlebody")
        self.stack.append((tag, skipped, in_art))
        self.skip += skipped
        self.article_depth += in_art
        if tag == "p" and not self.skip:
            self._p = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._jsonld_buf))
        if tag in _VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):             # tolerate unclosed tags
            if self.stack[i][0] == tag:
                for _t, sk, ar in self.stack[i:]:
                    self.skip -= sk
                    self.article_depth -= ar
                del self.stack[i:]
                break
        if tag == "p" and self._p is not None:
            txt = " ".join("".join(self._p).split())
            self._p = None
            if len(txt) >= 40 and not _BOILER.search(txt):
                self.p_all.append(txt)
                if self.article_depth:
                    self.p_article.append(txt)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_jsonld:
            self._jsonld_buf.append(data)
        if self._p is not None and not self.skip:
            self._p.append(data)


def _walk_jsonld(node, out):
    if isinstance(node, list):
        for x in node:
            _walk_jsonld(x, out)
    elif isinstance(node, dict):
        t = node.get("@type")
        ts = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and x.endswith("Article") for x in ts):
            out.append(node)
        for v in node.values():
            if isinstance(v, (list, dict)):
                _walk_jsonld(v, out)


def extract_article(html_text, url=None):
    """-> dict(status ok|short|empty|failed, title, text, canonical_url, publisher, author, published, method).
    text <= MAX_TEXT, lede-first; boilerplate, navigation, ads, consent banners, recommendations and scripts dropped."""
    try:
        ex = _Extractor()
        ex.feed(html_text or "")
        ex.close()
        arts = []
        for raw in ex.jsonld:
            try:
                _walk_jsonld(json.loads(raw), arts)
            except Exception:
                continue
        body, method = "", None
        for a in arts:
            b = a.get("articleBody")
            if isinstance(b, str) and len(" ".join(b.split())) >= MIN_USABLE_TEXT:
                body, method = " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", b)).split()), "json-ld:articleBody"    # bodies often carry markup
                break
        if not body:
            paras = ex.p_article if sum(map(len, ex.p_article)) >= MIN_USABLE_TEXT else ex.p_all
            body, method = " ".join(paras), ("dom:article-paragraphs" if paras is ex.p_article else "dom:paragraphs")
        body = " ".join(re.sub(r"<[^>]+>", " ", body).split())[:MAX_TEXT]
        if body and len(body) == MAX_TEXT and " " in body:
            body = body[:body.rfind(" ")]
        pub = None
        author = None
        for a in arts:
            p = a.get("publisher")
            pub = pub or (p.get("name") if isinstance(p, dict) else p if isinstance(p, str) else None)
            au = a.get("author")
            author = author or (au[0].get("name") if isinstance(au, list) and au and isinstance(au[0], dict) else au.get("name") if isinstance(au, dict) else au if isinstance(au, str) else None)
        status = "ok" if len(body) >= MIN_USABLE_TEXT else ("short" if body else "empty")
        title_l = (ex.meta.get("og:title") or ex.title or "").lower()
        if status == "ok" and (_LIVEBLOG.search(title_l) or (url and _LIVEBLOG_URL.search(url))):
            status = "not_article"                          # live blogs / ticker pages cover many stories: never evidence for one
        return {"status": status, "title": (ex.meta.get("og:title") or " ".join(ex.title.split()) or "")[:300], "text": body,
                "canonical_url": ex.canonical or ex.meta.get("og:url"), "publisher": pub or ex.meta.get("og:site_name"),
                "author": author if isinstance(author, str) else None,
                "published": ex.meta.get("article:published_time") or next((a.get("datePublished") for a in arts if a.get("datePublished")), None),
                "method": method}
    except Exception as e:                                       # noqa: BLE001
        return {"status": "failed", "title": "", "text": "", "canonical_url": None, "publisher": None, "author": None,
                "published": None, "method": None, "error": type(e).__name__}


# =====================================================================================
# Cache (own table, own migration; never touches articles / events / article_enrichment)
# =====================================================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS si_evidence (
    article_id INTEGER PRIMARY KEY, url TEXT NOT NULL, canonical_url TEXT, final_url TEXT,
    status TEXT NOT NULL,                       -- ok | blocked | failed | skipped   (state of the LAST attempt that produced this row)
    extraction_status TEXT,                     -- ok | short | empty | failed
    http_status INTEGER, title TEXT, text TEXT, content_hash TEXT, extractor_version TEXT NOT NULL,
    fetched_at TEXT, expires_at TEXT, error_class TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT, last_error TEXT, nbytes INTEGER, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_si_evidence_updated ON si_evidence(updated_at);
"""


def init_evidence_schema(conn):
    conn.executescript(_SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(si_evidence)")}
    for col, decl in (("url_source", "TEXT DEFAULT 'ORIGINAL'"), ("original_url", "TEXT")):     # Phase 12 provenance: which URL was really fetched
        if col not in have:
            conn.execute(f"ALTER TABLE si_evidence ADD COLUMN {col} {decl}")
    conn.commit()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d):
    return d.isoformat(timespec="seconds")


def cache_get(conn, article_id):
    try:
        r = conn.execute("SELECT * FROM si_evidence WHERE article_id=?", (article_id,)).fetchone()
    except Exception:
        return None
    return dict(r) if r else None


def usable_text(row):
    """The cached text if (and only if) it is a good extraction. An expired or old-extractor row is still returned
    (stale-but-usable): a re-fetch is a separate, budgeted decision and must not erase evidence the graph relies on."""
    if row and row.get("extraction_status") == "ok" and row.get("text"):
        return row["text"]
    return None


def cache_state(row, now=None):
    """'MISS' | 'FRESH' (usable + unexpired + current extractor) | 'STALE' (usable but expired/old extractor) |
    'FAILED_FRESH' (a recent failure/block: do not retry yet) | 'FAILED_EXPIRED' (a failure whose TTL has passed)."""
    now = now or _now()
    if row is None:
        return "MISS"
    exp = None
    try:
        exp = datetime.fromisoformat(row["expires_at"]) if row.get("expires_at") else None
    except Exception:
        exp = None
    if usable_text(row):
        if row.get("extractor_version") != EXTRACTOR_VERSION or exp is None or exp <= now:
            return "STALE"
        return "FRESH"
    return "FAILED_FRESH" if (exp is not None and exp > now) else "FAILED_EXPIRED"


def store(conn, article_id, url, fetch, extracted=None, now=None, url_source="ORIGINAL", original_url=None):
    """Write the outcome of one attempt. A failure NEVER replaces a good previous extraction: it only records the attempt."""
    now = now or _now()
    old = cache_get(conn, article_id)
    have_good = usable_text(old) is not None
    got_good = bool(extracted and extracted.get("status") == "ok" and fetch.status == "ok")
    attempts = (old["attempts"] if old else 0) + 1
    if have_good and not got_good:
        conn.execute("UPDATE si_evidence SET attempts=?, last_attempt_at=?, last_error=?, updated_at=updated_at WHERE article_id=?",
                     (attempts, _iso(now), fetch.error_class or (extracted or {}).get("status") or fetch.status, article_id))
        conn.commit()
        return "kept_previous"
    ex = extracted or {}
    text = ex.get("text") if got_good else None
    chash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24] if text else None
    conn.execute(
        "INSERT OR REPLACE INTO si_evidence (article_id, url, canonical_url, final_url, status, extraction_status, http_status, title, text, "
        "content_hash, extractor_version, fetched_at, expires_at, error_class, attempts, last_attempt_at, last_error, nbytes, updated_at, "
        "url_source, original_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (article_id, url, ex.get("canonical_url"), fetch.final_url, fetch.status, ex.get("status") if fetch.status == "ok" else None,
         fetch.http_status, (ex.get("title") or None) if got_good else None, text, chash, EXTRACTOR_VERSION,
         _iso(now) if fetch.status == "ok" else None, _iso(now + fetch.ttl), fetch.error_class or (None if got_good else ex.get("status")),
         attempts, _iso(now), None, fetch.nbytes, _iso(now), url_source, original_url))
    conn.commit()
    return "stored" if got_good else "stored_failure"


# =====================================================================================
# Budget + the one entry point
# =====================================================================================

@dataclass
class FetchBudget:
    max_fetches: int = 30            # network page fetches this run (robots.txt requests are not counted but are cached per origin)
    max_seconds: float = 150.0
    max_bytes: int = 20_000_000
    per_story: int = 6
    started: float = field(default_factory=time.time)
    fetches: int = 0
    bytes: int = 0
    requests: int = 0
    per_story_counts: dict = field(default_factory=dict)

    def allows(self, story_id=None):
        if self.fetches >= self.max_fetches:
            return False, "budget_fetches"
        if time.time() - self.started > self.max_seconds:
            return False, "budget_seconds"
        if self.bytes >= self.max_bytes:
            return False, "budget_bytes"
        if story_id is not None and self.per_story_counts.get(story_id, 0) >= self.per_story:
            return False, "budget_per_story"
        return True, None

    def charge(self, fetch, story_id=None):
        self.fetches += 1
        self.bytes += fetch.nbytes
        self.requests += fetch.requests_made
        if story_id is not None:
            self.per_story_counts[story_id] = self.per_story_counts.get(story_id, 0) + 1


def get_evidence(conn, article, budget=None, story_id=None, session=None, allow_fetch=True):
    """article: dict with id, url and optionally publisher_url (a VERIFIED real publisher URL recovered by publisher_url.py for a
    news.google.com wrapper article). The stored url is used when it is fetchable; otherwise the verified publisher_url, recorded as
    url_source='PUBLISHER_URL' with the original url kept. A wrapper URL is never fetched.
    -> (row_or_None, action) where action is one of
    CACHE_HIT | CACHED_FAILURE | FETCHED_OK | FETCHED_FAILED | NO_FETCH:<reason>.  Never raises; never fetches the same
    url twice inside its TTL; a failed re-fetch keeps the previous good text."""
    try:
        init_evidence_schema(conn)
        aid, url = article["id"], article.get("url")
        original, url_source = url, "ORIGINAL"
        ok, why = is_eligible_url(url)
        if not ok and article.get("publisher_url"):
            ok2, _ = is_eligible_url(article["publisher_url"])
            if ok2:
                url, url_source, ok = article["publisher_url"], "PUBLISHER_URL", True
        if not ok:
            return None, f"NO_FETCH:{why}"
        row = cache_get(conn, aid)
        st = cache_state(row)
        if st == "FRESH":
            return row, "CACHE_HIT"
        if st == "FAILED_FRESH":
            return None, "CACHED_FAILURE"
        if not allow_fetch:
            return (row if st == "STALE" else None), "NO_FETCH:fetching_disabled"
        if budget is not None:
            okb, why = budget.allows(story_id)
            if not okb:
                return (row if st == "STALE" else None), f"NO_FETCH:{why}"
        res = fetch_page(url, session=session)
        if budget is not None:
            budget.charge(res, story_id)
        ex = extract_article(res.html, url) if res.status == "ok" else None
        store(conn, aid, url, res, ex, url_source=url_source, original_url=original)
        row = cache_get(conn, aid)
        return (row if usable_text(row) else None), ("FETCHED_OK" if usable_text(row) and res.status == "ok" else "FETCHED_FAILED")
    except Exception as e:                                        # noqa: BLE001
        return None, f"NO_FETCH:error:{type(e).__name__}"


def cache_stats(conn):
    try:
        init_evidence_schema(conn)
        r = conn.execute("SELECT COUNT(*), SUM(status='ok'), SUM(extraction_status='ok'), COALESCE(SUM(LENGTH(text)),0) FROM si_evidence").fetchone()
        by = {x[0]: x[1] for x in conn.execute("SELECT COALESCE(error_class,'-'), COUNT(*) FROM si_evidence GROUP BY 1")}
        return {"rows": r[0], "fetched_ok": r[1] or 0, "extracted_ok": r[2] or 0, "text_bytes": r[3], "by_error": by}
    except Exception:
        return {"rows": 0}
