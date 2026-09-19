#!/usr/bin/env python3
"""
site_watch.py - external "is the PUBLISHED site alive and fresh?" check. Stdlib only, read-only.

Why this exists: every other alert (verify_fresh.py, check_scheduled_health.py) runs ON the
publisher PC. If that PC is off, asleep or offline, nothing there can notice - the site would just
quietly stop updating. This script looks at what readers actually get, from anywhere:

    py site_watch.py                 # check https://paksh.news, exit 0 healthy / 1 unhealthy
    py site_watch.py --url https://paksh.news --max-build-age-hours 26

It is run every few hours by .github/workflows/site-watch.yml (a failed run emails the repo owner).

What it checks (each failure is printed, exit code 1 if any):
  1. GET /                        -> 200 and mentions Paksh
  2. GET /data/freshness.json     -> built_at (last deployed build) no older than --max-build-age-hours
                                     newest_event_at no older than --max-news-age-hours
                                     event_count >= --min-events
  3. GET /data/events.json        -> valid JSON with >= 500 events (the homepage feed)
  4. GET /sitemap.xml             -> 200 and lists >= 1000 URLs
  5. GET /api/topics              -> still 404 (the static-mode probe; a 200 here would mean an API
                                     appeared that the app did not expect)

Defaults tolerate the normal schedule (jobs at 00:30, 05:30, 07:30 IST leave a 17h quiet gap).
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "PakshSiteWatch/1.0 (+https://paksh.news)"


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:                       # DNS, TLS, timeout...
        return 0, str(e).encode()


def age_hours(iso):
    """Age of a naive-UTC ISO timestamp (freshness.json is written with utcnow())."""
    t = datetime.fromisoformat(str(iso).replace("Z", ""))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def run(base, max_build, max_news, min_events):
    problems, notes = [], []
    base = base.rstrip("/")

    st, body = get(base + "/")
    if st != 200 or b"Paksh" not in body:
        problems.append("home page: status %s (expected 200 containing 'Paksh')" % st)
    else:
        notes.append("home page OK")

    st, body = get(base + "/data/freshness.json")
    try:
        fr = json.loads(body.decode("utf-8"))
        b, n, c = age_hours(fr["built_at"]), age_hours(fr["newest_event_at"]), int(fr["event_count"])
        notes.append("build age %.1fh, newest story %.1fh old, %d events" % (b, n, c))
        if b > max_build:
            problems.append("STALE BUILD: last deployed build is %.1fh old (limit %.0fh) - publisher PC/pipeline/push may be down" % (b, max_build))
        if n > max_news:
            problems.append("STALE NEWS: newest story is %.1fh old (limit %.0fh) - ingest may be failing" % (n, max_news))
        if c < min_events:
            problems.append("event_count %d < %d - catalogue unexpectedly small" % (c, min_events))
    except Exception as e:
        problems.append("freshness.json unreadable (status %s): %s" % (st, str(e)[:80]))

    st, body = get(base + "/data/events.json", timeout=60)
    try:
        n = len(json.loads(body.decode("utf-8")).get("events", []))
        (problems if n < 500 else notes).append("events.json has %d events" % n)
    except Exception as e:
        problems.append("events.json unreadable (status %s): %s" % (st, str(e)[:80]))

    st, body = get(base + "/sitemap.xml", timeout=60)
    urls = len(re.findall(rb"<loc>", body))
    if st != 200 or urls < 1000:
        problems.append("sitemap: status %s, %d urls (expected 200 and >= 1000)" % (st, urls))
    else:
        notes.append("sitemap %d urls" % urls)

    st, _ = get(base + "/api/topics")
    if st == 200:
        problems.append("/api/topics returned 200 - an API appeared that the static-mode app does not expect")

    return problems, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://paksh.news")
    ap.add_argument("--max-build-age-hours", type=float, default=26.0)
    ap.add_argument("--max-news-age-hours", type=float, default=30.0)
    ap.add_argument("--min-events", type=int, default=1000)
    a = ap.parse_args()
    problems, notes = run(a.url, a.max_build_age_hours, a.max_news_age_hours, a.min_events)
    for n in notes:
        print("ok   ", n)
    for p in problems:
        print("FAIL ", p)
    print("HEALTHY" if not problems else "UNHEALTHY (%d problem(s))" % len(problems))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
