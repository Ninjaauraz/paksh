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
import os
import random
import socket
import ssl
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

import gdelt_gate
from database import init_db, insert_article, ArticleWriter
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

# International / world-news queries. These feed Paksh's (already-live) World
# section: each pulls a major global English wire's latest, and clustering plus
# the >=2-rated-outlet gate in analyze.py surface the big shared world stories
# (covered by two or more of these) as events with balanced framing. Anchored on
# the reputable global wires we curate as the non-voting "international" tier, so
# world events are built from credible sources. English-only by design - GDELT
# items GDELT tags non-en/hi are dropped at ingest and would never display.
# Bounded on purpose (cost); tune freely, or disable with `--no-intl`.
INTL_QUERIES = [
    'domain:reuters.com',
    'domain:apnews.com',
    'domain:bbc.com',
    'domain:theguardian.com',
    'domain:aljazeera.com',
    'domain:cnn.com',
    'domain:nytimes.com',
    'domain:washingtonpost.com',
    'domain:bloomberg.com',
    'domain:dw.com',
    'domain:france24.com',
    'domain:scmp.com',
    'domain:channelnewsasia.com',
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
    # Same family, missed by the list above. Found by measuring the DB (docs/SOURCE_UTILIZATION_AUDIT.md):
    # 42 unrated domains that republished >=15 identical headlines shared with >=2 other unrated
    # domains over 45 days (~3,100 articles, ~19% of the unrated GDELT flow, all fake breadth).
    # Deliberately NOT added: aninews.in (ANI, a real wire agency the copies come FROM) and
    # webindia123.com (aggregator) - whether those count is Sameer's editorial call.
    "argentinastar.com", "austinglobe.com", "australiannews.net", "batonrougepost.com",
    "bignewsnetwork.com", "brazilsun.com", "britainnews.net", "cambodiantimes.com",
    "caribbeanherald.com", "greekherald.com", "hongkongherald.com", "iranherald.com", "iraqsun.com",
    "irishsun.com", "jamaicantimes.com", "laosnews.net", "mainemirror.com", "malaysiasun.com",
    "mexicostar.com", "milwaukeesun.com", "nepalnational.com", "newyorkstatesman.com",
    "newyorktelegraph.com", "newzealandstar.com", "nigeriasun.com", "northkoreatimes.com",
    "ohiostandard.com", "oklahomacitysun.com", "pakistantelegraph.com", "sanantoniopost.com",
    "shanghainews.net", "shanghaisun.com", "sierraleonetimes.com", "singaporestar.com",
    "srilankasource.com", "sydneysun.com", "taiwansun.com", "thailandnews.net", "trinidadtimes.com",
    "tucsonpost.com", "vietnamtribune.com", "zimbabwestar.com",
}
TIMESPAN = "1d"        # last 24 hours
MAXRECORDS = 250       # GDELT hard cap per call
# Phase 21C: inter-query spacing used to be a plain time.sleep(SLEEP) here between
# queries. That is now superseded by gdelt_gate's cross-process minimum-interval
# gate (called inside _fetch(), before every attempt) - it is the one authoritative
# pacing mechanism, so a redundant fixed sleep on top of it would just double the
# wait for no reason. SLEEP is kept (unused for pacing) only because a test sets it.
SLEEP = 6
MAX_CONSECUTIVE_FAILURES = 3   # circuit breaker: stop the stage after this many failed queries in a row

# GDELT's DOC API returns HTTP 429 for non-browser User-Agents, so we must send
# a browser-like UA (see github.com/alex9smith/gdelt-doc-api issue #22).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Phase 21D: durable per-stage metrics (one JSON line per _run() call), independent
# of which caller's stdout gets captured - live.py's own GDELT stages don't reach
# live_log.txt today (see gdelt_source.py's callers), so a print-only summary would
# be invisible for most real-world runs. Overridable so tests never touch the real
# file. Bounded/rotated the same way live.py rotates live_log.txt.
METRICS_PATH = os.environ.get("PAKSH_GDELT_METRICS_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "gdelt_metrics.jsonl")
METRICS_MAX_BYTES = 5 * 1024 * 1024


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _classify_exc(e):
    """Observation only (Phase 21D) - never used for retry/control-flow decisions,
    only to label an outcome for metrics. Mirrors the categories used in the Phase
    21B/21C audit reports (DNS/connection/TLS/429/other), so future log analysis
    doesn't need to re-derive them from raw exception text."""
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 429:
            return "HTTP_429"
        if 500 <= e.code < 600:
            return "HTTP_5XX"
        return "HTTP_4XX"
    if isinstance(e, urllib.error.URLError):
        reason = e.reason
        if isinstance(reason, socket.gaierror):
            return "DNS_FAILURE"
        if isinstance(reason, ssl.SSLError):
            return "TLS_FAILURE"
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "TIMEOUT"
        if isinstance(reason, (ConnectionRefusedError, ConnectionResetError,
                                ConnectionAbortedError, OSError)):
            return "CONNECTION_FAILURE"
        return "OTHER_NETWORK"
    if isinstance(e, TimeoutError):
        return "TIMEOUT"
    return "OTHER"


def _fetch(query, timespan=TIMESPAN, maxrecords=MAXRECORDS, retries=4, metrics=None):
    """Call the GDELT DOC API and return its ArtList. Retries on 429/503 with
    exponential backoff + jitter, honouring any Retry-After header. Every attempt -
    the first try and every retry - passes through gdelt_gate.wait_for_slot() first:
    that is the one cross-process minimum-interval gate authoritative for pacing
    (Phase 21C); this function's own backoff still governs how long to wait after a
    429 specifically, but the gate is what stops any two attempts, from any process,
    from firing closer together than GDELT_MIN_INTERVAL_SECONDS apart.

    `metrics`, if given a dict, is filled in with Phase 21D timing/outcome details
    (start/end, attempts, per-attempt classification, gate wait, articles). It is
    purely observational - every existing caller passes nothing, and behavior is
    byte-for-byte identical to before this phase either way."""
    params = {
        "query": query, "mode": "ArtList", "format": "json",
        "timespan": timespan, "maxrecords": str(maxrecords), "sort": "DateDesc",
    }
    url = GDELT_URL + "?" + urllib.parse.urlencode(params)
    delay = 8
    if metrics is not None:
        metrics["query"] = query
        metrics["start_utc"] = _now_iso()
        metrics["attempts"] = 0
        metrics["attempt_starts_utc"] = []
        metrics["gate_wait_s"] = 0.0
        metrics["max_gate_wait_s"] = 0.0
        metrics["classifications"] = []
    for attempt in range(retries):
        waited = gdelt_gate.wait_for_slot(context=query[:40])
        if metrics is not None:
            metrics["attempts"] += 1
            metrics["attempt_starts_utc"].append(_now_iso())
            metrics["gate_wait_s"] += waited
            metrics["max_gate_wait_s"] = max(metrics["max_gate_wait_s"], waited)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            try:
                arts = json.loads(body).get("articles", [])
                print(f"    GDELT: pid={os.getpid()} status=200 articles={len(arts)} "
                      f"elapsed={time.monotonic() - t0:.1f}s attempt={attempt + 1}/{retries}")
                if metrics is not None:
                    metrics["classifications"].append("SUCCESS")
                    metrics["end_utc"] = _now_iso()
                    metrics["outcome"] = "SUCCESS"
                    metrics["articles"] = len(arts)
                    metrics["attempts_exhausted"] = False
                return arts
            except json.JSONDecodeError:
                # GDELT returns an HTML notice (not JSON) when overloaded. That is a FAILED
                # query, not an empty one: it used to return [] silently, which made an
                # overloaded stage look like "GDELT had nothing new" (audit: 8 days at zero).
                if metrics is not None:
                    metrics["classifications"].append("OVERLOADED_NON_JSON")
                if attempt < retries - 1:
                    time.sleep(delay + random.uniform(0, 3))
                    delay *= 2
                    continue
                if metrics is not None:
                    metrics["end_utc"] = _now_iso()
                    metrics["outcome"] = "OVERLOADED_NON_JSON"
                    metrics["attempts_exhausted"] = True
                raise urllib.error.URLError("GDELT returned a non-JSON (overload) page")
        except urllib.error.HTTPError as e:
            if metrics is not None:
                metrics["classifications"].append(_classify_exc(e))
            if e.code in (429, 503) and attempt < retries - 1:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                wait = int(retry_after or 0) or delay
                wait += random.uniform(0, 3)
                print(f"    GDELT {e.code}: pid={os.getpid()} attempt={attempt + 1}/{retries} "
                      f"retry_after={retry_after or 'none'} backoff={wait:.0f}s")
                time.sleep(wait)
                delay *= 2
                continue
            if metrics is not None:
                metrics["end_utc"] = _now_iso()
                metrics["outcome"] = _classify_exc(e)
                metrics["attempts_exhausted"] = metrics["attempts"] >= retries
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if metrics is not None:
                metrics["classifications"].append(_classify_exc(e))
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            if metrics is not None:
                metrics["end_utc"] = _now_iso()
                metrics["outcome"] = _classify_exc(e)
                metrics["attempts_exhausted"] = metrics["attempts"] >= retries
            raise
    if metrics is not None:
        metrics["end_utc"] = _now_iso()
        metrics.setdefault("outcome", "RETRY_EXHAUSTED")
        metrics["articles"] = 0
        metrics["attempts_exhausted"] = True
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


_CLASS_TO_TOTAL_KEY = {
    "HTTP_429": "count_429", "HTTP_5XX": "count_5xx", "HTTP_4XX": "count_4xx",
    "DNS_FAILURE": "count_dns", "CONNECTION_FAILURE": "count_connection",
    "TLS_FAILURE": "count_tls", "TIMEOUT": "count_timeout",
    "OTHER_NETWORK": "count_other_network", "OVERLOADED_NON_JSON": "count_overloaded_nonjson",
    "SUCCESS": "count_success",
}


def _build_stage_metrics(query_metrics, stage_start_utc, stage_duration_s,
                          ok_q, failed_q, total_q, added):
    """Phase 21D: aggregate the per-query metrics dicts _run() collected into one
    stage-level summary. Pure aggregation - does not affect what _run() does."""
    totals = {k: 0 for k in _CLASS_TO_TOTAL_KEY.values()}
    total_attempts = 0
    gate_total_wait = 0.0
    gate_max_wait = 0.0
    all_starts = []
    for qm in query_metrics:
        total_attempts += qm.get("attempts", 0)
        gate_total_wait += qm.get("gate_wait_s", 0.0)
        gate_max_wait = max(gate_max_wait, qm.get("max_gate_wait_s", 0.0))
        all_starts.extend(qm.get("attempt_starts_utc", []))
        for c in qm.get("classifications", []):
            key = _CLASS_TO_TOTAL_KEY.get(c)
            if key:
                totals[key] += 1
    min_interval = None
    if len(all_starts) >= 2:
        ts = sorted(datetime.fromisoformat(s) for s in all_starts)
        gaps = [(ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1)]
        if gaps:
            min_interval = min(gaps)
    return {
        "run_id": f"{os.getpid()}-{stage_start_utc}",
        "start_utc": stage_start_utc,
        "end_utc": _now_iso(),
        "duration_s": round(stage_duration_s, 1),
        "queries_total": total_q,
        "queries_attempted": ok_q + failed_q,
        "queries_succeeded": ok_q,
        "queries_failed": failed_q,
        "total_http_attempts": total_attempts,
        "articles_added": added,
        "gate_total_wait_s": round(gate_total_wait, 1),
        "gate_max_wait_s": round(gate_max_wait, 1),
        "min_inter_request_interval_s": round(min_interval, 2) if min_interval is not None else None,
        **totals,
        "queries": query_metrics,
    }


def _emit_stage_metrics(stage_metrics):
    """Phase 21D: print a concise, greppable one-line summary (distinct
    'GDELT_STAGE_METRICS' prefix - never collides with the existing 'GDELT query
    failed' / '-> N articles' / 'GDELT added' lines refresh_log.txt tooling already
    parses), AND append the full record to METRICS_PATH so a run whose stdout isn't
    captured (live.py's own GDELT stage today) still leaves a durable, comparable
    record. A metrics-write failure must never fail the GDELT stage itself."""
    summary = {k: v for k, v in stage_metrics.items() if k != "queries"}
    print("GDELT_STAGE_METRICS " + json.dumps(summary, ensure_ascii=False))
    try:
        if os.path.exists(METRICS_PATH) and os.path.getsize(METRICS_PATH) > METRICS_MAX_BYTES:
            with open(METRICS_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(METRICS_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-500:])
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(stage_metrics, ensure_ascii=False) + "\n")
    except OSError:
        pass   # metrics must never be the reason a GDELT stage fails


def run(queries=QUERIES, timespan=TIMESPAN, verbose=True):
    init_db()
    writer = ArticleWriter()          # batched commits (see database.ArticleWriter); connects lazily, closes + flushes below
    try:
        return _run(queries, timespan, verbose, writer)
    finally:
        writer.close()


def _run(queries, timespan, verbose, writer):
    seen = set()
    added = rated_n = unrated_n = 0
    unrated_domains = set()
    ok_q = failed_q = consec_fail = 0
    stage_start_utc = _now_iso()
    stage_t0 = time.monotonic()
    query_metrics = []
    for q in queries:
        qm = {}
        try:
            arts = _fetch(q, timespan, metrics=qm)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            failed_q += 1
            consec_fail += 1
            query_metrics.append(qm)
            if verbose:
                print(f"  ! GDELT query failed ({q[:42]}...): {e}")
            if consec_fail >= MAX_CONSECUTIVE_FAILURES:
                # Rate-limited (429) or offline: every further query only adds retry back-offs
                # (one failing stage measured 34 minutes) and keeps the limiter angry. Give up
                # for this cycle; the next one starts clean. Nothing already fetched is lost.
                if verbose:
                    print(f"  ! GDELT: {consec_fail} queries in a row failed - stopping this stage "
                          f"({len(queries) - ok_q - failed_q} query(ies) not attempted).")
                break
            continue    # gdelt_gate paces the next _fetch() call; no extra sleep needed here
        query_metrics.append(qm)
        ok_q += 1
        consec_fail = 0
        if verbose:
            print(f"  > GDELT [{q[:48]}] -> {len(arts)} articles")
        for art in arts:
            norm = normalize_gdelt(art)
            if not norm or norm["url"] in seen:
                continue
            seen.add(norm["url"])
            rowid = writer.insert(
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
        writer.flush()                 # commit after every query, right away - gdelt_gate paces the next _fetch() call

    stage_metrics = _build_stage_metrics(query_metrics, stage_start_utc, time.monotonic() - stage_t0,
                                          ok_q, failed_q, len(queries), added)
    _emit_stage_metrics(stage_metrics)

    if verbose:
        print(f"\nGDELT queries: {ok_q} ok, {failed_q} failed, of {len(queries)}.")
        print(f"GDELT added {added} new articles "
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
    # Default: India queries + international world-news queries (strengthens the
    # World section). `--no-intl` restricts to India-only; `--intl-only` pulls
    # just world news (handy for a one-off international backfill).
    if "--no-intl" in sys.argv:
        queries = QUERIES
    elif "--intl-only" in sys.argv:
        queries = INTL_QUERIES
    else:
        queries = QUERIES + INTL_QUERIES
    run(queries=queries, timespan=span)