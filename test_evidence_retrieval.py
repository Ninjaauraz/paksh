"""
test_evidence_retrieval.py - bounded, polite, fail-closed evidence retrieval (fetch policy, extraction, cache, budget).
No network: a fake session stands in for requests. Temp SQLite only. Run:  py test_evidence_retrieval.py
"""
import ipaddress
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

import requests

import evidence_retrieval as ev

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


class Resp:
    def __init__(self, status=200, body=b"", headers=None, chunks=None):
        self.status_code = status
        self.headers = headers if headers is not None else {"Content-Type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"
        self._chunks = chunks if chunks is not None else [body]

    def iter_content(self, n):
        for c in self._chunks:
            yield c

    def close(self):
        pass


class Session:
    """Routes by exact url; records every request."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.routes.get(url)
        if isinstance(r, Exception):
            raise r
        if r is None:
            return Resp(404)
        return r() if callable(r) else r


ev._host_is_public = lambda host: host not in ("127.0.0.1", "localhost", "10.0.0.5")
ev.DOMAIN_DELAY_S = 0
ARTICLE = ("<html><head><title>Fire at plant - The Daily</title><meta property='og:title' content='Fire at plant'>"
           "<meta property='og:site_name' content='The Daily'><link rel='canonical' href='https://daily.test/a/1'></head><body>"
           "<nav><p>Home | India | World | Sports and lots of navigation text to be dropped entirely</p></nav>"
           "<div class='cookie-banner'><p>We use cookies to improve your experience on our website, accept them all.</p></div>"
           "<article><p>NEW DELHI (PTI) A fire broke out at a chemical plant on the outskirts of the city on Monday, killing at least "
           "twelve workers and injuring dozens more, officials said.</p>"
           "<p>Rescue teams pulled several people from the debris through the night while the district administration announced "
           "compensation for the families of those who died in the blaze.</p>"
           "<p>Read more: five other stories you may like</p>"
           "<div class='related-stories'><p>Another headline that must never be part of the extracted article text at all.</p></div>"
           "</article><footer><p>Copyright The Daily. All rights reserved by the publisher of this website.</p></footer>"
           "<script>var x = 'not text';</script></body></html>").encode()

print("TEST 1: URL policy")
for u, why in [("javascript:alert(1)", "scheme_not_http"), ("data:text/html,<p>x", "scheme_not_http"), ("file:///etc/passwd", "scheme_not_http"),
               ("ftp://x.test/a", "scheme_not_http"), ("https://user:pw@x.test/a", "bad_host_or_userinfo"), ("", "no_url"), (None, "no_url"),
               ("https://news.google.com/rss/articles/CBMi123", "google_news_redirect_url"), ("https:///nohost", "bad_host_or_userinfo")]:
    got = ev.is_eligible_url(u)
    check(f"1: {str(u)[:40]!r} rejected as {why}", got == (False, why), str(got))
check("1: a normal https article url is eligible", ev.is_eligible_url("https://daily.test/a/1") == (True, None))
r = ev.fetch_page("javascript:alert(1)", session=Session({}))
check("1: fetch_page never touches the network for a rejected url", r.status == "skipped" and not r.html)

print("\nTEST 2: fetch policy")
ROB = "https://daily.test/robots.txt"
ok_routes = {ROB: Resp(404), "https://daily.test/a/1": Resp(200, ARTICLE)}
s = Session(ok_routes)
r = ev.fetch_page("https://daily.test/a/1", session=s)
check("2a: a normal page is fetched (robots.txt 404 = nothing forbidden)", r.status == "ok" and r.http_status == 200 and b"fire broke out" in r.html.encode())
ev._robots.clear()
s = Session({ROB: Resp(200, b"User-agent: *\nDisallow: /a/\n"), "https://daily.test/a/1": Resp(200, ARTICLE)})
r = ev.fetch_page("https://daily.test/a/1", session=s)
check("2b: robots.txt Disallow -> blocked and the page itself is never requested", r.status == "blocked" and r.error_class == "robots_disallowed" and "https://daily.test/a/1" not in s.calls)
ev._robots.clear()
s = Session({ROB: Resp(503), "https://daily.test/a/1": Resp(200, ARTICLE)})
r = ev.fetch_page("https://daily.test/a/1", session=s)
check("2c: unreadable robots.txt (5xx) -> do not fetch now", r.status == "failed" and r.error_class == "robots_unreadable" and "https://daily.test/a/1" not in s.calls)
for code, status, cls in ((403, "blocked", "http_403"), (401, "blocked", "http_401"), (429, "failed", "http_429"), (404, "failed", "http_404"), (500, "failed", "http_500")):
    ev._robots.clear()
    r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(code)}))
    check(f"2d: HTTP {code} -> {status}/{cls}, no retry", (r.status, r.error_class) == (status, cls) and r.requests_made == 1)
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(200, b"{}", {"Content-Type": "application/json"})}))
check("2e: a non-HTML response is rejected", r.status == "failed" and r.error_class == "not_html")
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": requests.exceptions.Timeout("slow")}))
check("2f: a timeout is a cached-able failure, not an exception", r.status == "failed" and r.error_class == "Timeout")
ev._robots.clear()
big = [b"x" * 100_000] * 30
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(200, chunks=big)}))
check("2g: the response-size cap stops an oversized body", r.status == "failed" and r.error_class == "response_too_large" and r.nbytes <= ev.MAX_BYTES + 100_000)
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(200, b"<html><title>Just a moment...</title>cf-chl</html>")}))
check("2h: a bot-protection interstitial is 'blocked', never treated as an article", r.status == "blocked" and r.error_class == "bot_protection_or_interstitial")

print("\nTEST 3: redirect safety")
ev._robots.clear()
s = Session({ROB: Resp(404), "https://daily.test/a/1": Resp(301, headers={"Location": "/a/2"}), "https://daily.test/a/2": Resp(200, ARTICLE)})
r = ev.fetch_page("https://daily.test/a/1", session=s)
check("3a: a relative redirect is followed and validated", r.status == "ok" and r.final_url == "https://daily.test/a/2")
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(302, headers={"Location": "http://127.0.0.1/admin"})}))
check("3b: a redirect to a loopback address is refused", r.status == "skipped" and r.error_class in ("non_public_address", "https_downgrade_redirect"))
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(302, headers={"Location": "https://10.0.0.5/x"})}))
check("3c: a redirect to a private address is refused", r.status == "skipped" and r.error_class == "non_public_address")
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(302, headers={"Location": "javascript:alert(1)"})}))
check("3d: a redirect to a javascript: url is refused", r.status == "skipped" and r.error_class == "unsafe_redirect_target")
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(302, headers={"Location": "http://other.test/x"})}))
check("3e: an https -> http downgrade redirect is refused", r.status == "skipped" and r.error_class == "https_downgrade_redirect")
ev._robots.clear()
loop = {ROB: Resp(404)}
for i in range(8):
    loop[f"https://daily.test/l{i}"] = Resp(302, headers={"Location": f"/l{i + 1}"})
r = ev.fetch_page("https://daily.test/l0", session=Session(loop))
check("3f: a redirect chain is limited", r.status == "failed" and r.error_class == "too_many_redirects")

print("\nTEST 4: extraction")
x = ev.extract_article(ARTICLE.decode(), "https://daily.test/a/1")
check("4a: main text extracted, lede first", x["status"] == "ok" and x["text"].startswith("NEW DELHI (PTI) A fire broke out"))
check("4b: navigation, cookie banner, related links, footer, scripts dropped",
      all(t not in x["text"] for t in ("navigation", "cookies", "Another headline", "Copyright", "not text", "Read more")))
check("4c: title / canonical / publisher metadata kept", x["title"] == "Fire at plant" and x["canonical_url"] == "https://daily.test/a/1" and x["publisher"] == "The Daily")
check("4d: text is capped", len(ev.extract_article("<article>" + "<p>" + ("word " * 60) + "</p>" * 1 + ("<p>" + "more words here " * 40 + "</p>") * 10 + "</article>")["text"]) <= ev.MAX_TEXT)
jl = ("<html><head><script type='application/ld+json'>{\"@type\":\"NewsArticle\",\"headline\":\"H\",\"datePublished\":\"2026-09-20\","
      "\"publisher\":{\"name\":\"Pub\"},\"articleBody\":\"" + "The minister announced a new scheme on Sunday. " * 12 + "\"}</script></head><body></body></html>")
xj = ev.extract_article(jl)
check("4e: JSON-LD articleBody is preferred when present", xj["status"] == "ok" and xj["method"] == "json-ld:articleBody" and xj["publisher"] == "Pub" and xj["published"] == "2026-09-20")
hi = "<article><p>" + "दिल्ली में एक रासायनिक संयंत्र में आग लगने से कम से कम बारह मजदूरों की मौत हो गई। " * 4 + "</p></article>"
check("4f: Hindi text is extracted", ev.extract_article(hi)["status"] == "ok")
check("4g: too little text is 'short', nothing is 'empty', garbage never raises",
      ev.extract_article("<article><p>" + "a short lede that is still forty characters long yes" + "</p></article>")["status"] == "short"
      and ev.extract_article("<html><body>nothing</body></html>")["status"] == "empty" and ev.extract_article("<<<not html>>>")["status"] in ("empty", "short", "failed"))

print("\nTEST 5: cache, failure retention, no duplicate fetches, budget")
tmp = Path(tempfile.mkdtemp(prefix="ev_test_")) / "t.db"
conn = sqlite3.connect(tmp)
conn.row_factory = sqlite3.Row
art = {"id": 1, "url": "https://daily.test/a/1"}
ev._robots.clear()
s = Session({ROB: Resp(404), "https://daily.test/a/1": Resp(200, ARTICLE)})
row, act = ev.get_evidence(conn, art, budget=ev.FetchBudget(), session=s)
check("5a: first call fetches and caches", act == "FETCHED_OK" and ev.usable_text(row) and s.calls.count("https://daily.test/a/1") == 1)
row, act = ev.get_evidence(conn, art, budget=ev.FetchBudget(), session=s)
check("5b: second call is a cache hit with no new request", act == "CACHE_HIT" and s.calls.count("https://daily.test/a/1") == 1)
conn.execute("UPDATE si_evidence SET expires_at='2000-01-01T00:00:00' WHERE article_id=1")
conn.commit()
check("5c: an expired good row is STALE (still usable) rather than lost", ev.cache_state(ev.cache_get(conn, 1)) == "STALE" and ev.usable_text(ev.cache_get(conn, 1)))
s2 = Session({ROB: Resp(404), "https://daily.test/a/1": Resp(500)})
row, act = ev.get_evidence(conn, art, budget=ev.FetchBudget(), session=s2)
check("5d: a FAILED re-fetch keeps the previous good text (never overwritten by a failure)", ev.usable_text(row) is not None and act == "FETCHED_FAILED"
      and ev.usable_text(ev.cache_get(conn, 1)) and ev.cache_get(conn, 1)["attempts"] == 2)
conn.execute("UPDATE si_evidence SET extractor_version='old-extractor' WHERE article_id=1")
conn.commit()
check("5e: an old extractor version makes the row STALE", ev.cache_state(ev.cache_get(conn, 1)) == "STALE")
art2 = {"id": 2, "url": "https://daily.test/a/2"}
ev._robots.clear()
s3 = Session({ROB: Resp(404), "https://daily.test/a/2": Resp(500)})
row, act = ev.get_evidence(conn, art2, budget=ev.FetchBudget(), session=s3)
row, act2 = ev.get_evidence(conn, art2, budget=ev.FetchBudget(), session=s3)
check("5f: a failure is cached: the url is not fetched again inside its TTL", act == "FETCHED_FAILED" and act2 == "CACHED_FAILURE" and s3.calls.count("https://daily.test/a/2") == 1)
conn.execute("UPDATE si_evidence SET expires_at='2000-01-01T00:00:00' WHERE article_id=2")
conn.commit()
check("5g: after the failure TTL passes it may be retried", ev.cache_state(ev.cache_get(conn, 2)) == "FAILED_EXPIRED")
b = ev.FetchBudget(max_fetches=1)
ev._robots.clear()
s4 = Session({ROB: Resp(404), "https://daily.test/a/3": Resp(200, ARTICLE), "https://daily.test/a/4": Resp(200, ARTICLE)})
_, a3 = ev.get_evidence(conn, {"id": 3, "url": "https://daily.test/a/3"}, budget=b, session=s4)
_, a4 = ev.get_evidence(conn, {"id": 4, "url": "https://daily.test/a/4"}, budget=b, session=s4)
check("5h: the per-run fetch budget stops further fetching", a3 == "FETCHED_OK" and a4 == "NO_FETCH:budget_fetches" and "https://daily.test/a/4" not in s4.calls)
b = ev.FetchBudget(per_story=1)
_, x1 = ev.get_evidence(conn, {"id": 5, "url": "https://daily.test/a/3"}, budget=b, story_id=9, session=s4)
_, x2 = ev.get_evidence(conn, {"id": 6, "url": "https://daily.test/a/4"}, budget=b, story_id=9, session=s4)
check("5i: the per-story budget stops a story hogging the run", x1 == "FETCHED_OK" and x2 == "NO_FETCH:budget_per_story")
_, x3 = ev.get_evidence(conn, {"id": 7, "url": "https://news.google.com/rss/articles/CBMi"}, budget=ev.FetchBudget(), session=s4)
check("5j: a Google News link is never fetched", x3 == "NO_FETCH:google_news_redirect_url")
_, x4 = ev.get_evidence(conn, {"id": 8, "url": "https://daily.test/a/9"}, budget=ev.FetchBudget(), session=s4, allow_fetch=False)
check("5k: allow_fetch=False never touches the network", x4 == "NO_FETCH:fetching_disabled" and "https://daily.test/a/9" not in s4.calls)
st = ev.cache_stats(conn)
check("5l: cache statistics are available", st["rows"] >= 4 and st["extracted_ok"] >= 1)
conn.close()

print("\nTEST 6: address guard (public / private / NAT64)")
ip = ipaddress.ip_address
check("6a: ordinary public IPv4 / IPv6 are allowed", ev._ip_is_public(ip("151.101.208.81")) and ev._ip_is_public(ip("2606:4700::1111")))
check("6b: private, loopback, link-local, metadata-service addresses are refused",
      not any(ev._ip_is_public(ip(x)) for x in ("10.0.0.5", "192.168.1.1", "172.16.0.9", "127.0.0.1", "169.254.169.254", "::1", "fe80::1", "fc00::1", "0.0.0.0")))
check("6c: NAT64 (64:ff9b::/96) of a PUBLIC IPv4 is allowed (this network resolves everything that way)", ev._ip_is_public(ip("64:ff9b::9765:d051")))
check("6d: NAT64 / IPv4-mapped forms of a PRIVATE IPv4 are still refused", not ev._ip_is_public(ip("64:ff9b::a00:5")) and not ev._ip_is_public(ip("64:ff9b::7f00:1")) and not ev._ip_is_public(ip("::ffff:10.0.0.5")))

print("\nTEST 7: extraction hygiene")
LIVE = "<html><head><title>India News Live Updates: today's top stories</title></head><body><article>" + "<p>" + ("Ten different things happened across the country today and each of them gets a paragraph here. " * 5) + "</p></article></body></html>"
check("7a: a live blog / ticker page is 'not_article' (never evidence for one story)", ev.extract_article(LIVE, "https://x.test/live-updates/today")["status"] == "not_article")
MARK = ("<html><head><script type='application/ld+json'>{\"@type\":\"NewsArticle\",\"articleBody\":\"<p>The minister <a href='x'>announced</a> a new scheme on Sunday. " + "It will cover every district. " * 12 + "</p>\"}</script></head></html>")
xm = ev.extract_article(MARK)
check("7b: markup inside a JSON-LD articleBody is stripped", xm["status"] == "ok" and "<" not in xm["text"] and "announced a new scheme" in xm["text"])
check("7c: the extractor version is bumped when extraction changes", ev.EXTRACTOR_VERSION == "ev-extract-3")

print("\nTEST 8: encoding and paywall boilerplate")
UTF = "<html><article><p>" + ("The president said the country’s ‘new’ plan would cover every district and every village by the end of the year. " * 4) + "</p></article></html>"
ev._robots.clear()
r = ev.fetch_page("https://daily.test/a/1", session=Session({ROB: Resp(404), "https://daily.test/a/1": Resp(200, UTF.encode("utf-8"), {"Content-Type": "text/html"})}))
check("8a: UTF-8 without a charset header is decoded as UTF-8 (no mojibake)", r.status == "ok" and "’" in r.html and "â" not in r.html)
PAY = "<html><article><p>Save now on essential digital access to trusted journalism on any device. Savings based on annual price plans.</p><p>" + ("Real reporting about the fund and what it plans to sell in the coming months, according to the manager. " * 4) + "</p></article></html>"
xp = ev.extract_article(PAY)
check("8b: subscription / paywall promo lines are dropped, the real paragraph stays", "Save now" not in xp["text"] and "Real reporting" in xp["text"])
check("8c: a page that is ONLY a paywall promo is not usable evidence", ev.extract_article("<html><article><p>Save now on essential digital access to trusted journalism. Discover all the plans currently available in your country today.</p></article></html>")["status"] in ("empty", "short"))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL evidence_retrieval CHECKS PASSED")
