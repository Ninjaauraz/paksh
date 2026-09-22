"""
test_source_utilization.py - the clustering window, the prompt's source picker and GDELT's
failure handling (docs/SOURCE_UTILIZATION_AUDIT.md).

What is pinned here:
  A. database._fair_take / select_unclustered_window: every outlet gets an EQUAL share of the
     window when the cap binds (the old 'newest N' cut-off starved the outlets ingested first),
     rated outlets still claim before the long tail, vetted registry outlets get a bounded
     reserve, nothing is dropped when the cap does not bind, newest-first order is preserved.
  B. source_selection.select_sources: copies of one report collapse to one, a side is never
     dropped, cross-lean copies are kept (each side keeps its voice), the richest copy
     represents its report, a new home region is preferred, output is deterministic and only
     ever contains the event's own articles.
  C. analyze.build_prompt still tells the model the per-side owner counts from ALL articles
     (the bias arithmetic is not computed from the picked subset) and keeps every covered side;
     on a retry (region known) outlets are labelled with the lean the arithmetic will COUNT, and
     analyze_event keeps the region the retry was prompted with (C5-C11).
  D. gdelt_source: a non-JSON (overload) reply is a FAILED query, and 3 failed queries in a row
     stop the stage; a success resets the counter; the measured farm domains are blocked.
Offline: no network and no LLM (the model call is faked). The only database used is an ISOLATED temp
file (A20-A22 exercise the real sqlite3.Row query path); the real paksh.db is never opened.

Run:  py test_source_utilization.py
"""
import inspect
import os
import tempfile
import urllib.error
from collections import Counter

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


import database as d
import source_selection as ss
import sources
import analyze

# ---------------------------------------------------------------- A. the clustering window
print("=== A: fair clustering window ===")


def newest_first(spec):
    """spec = [(outlet, n_rows)], listed newest-first exactly like ORDER BY fetched_at DESC."""
    rows, i = [], 0
    for src, n in spec:
        for _ in range(n):
            rows.append({"source": src, "id": i, "title": f"t{i}", "summary": "", "language": "en"})
            i += 1
    return rows


def legacy_take(rows, cap, per):
    by, out = {}, []
    for r in rows:
        if len(out) >= cap:
            break
        if by.get(r["source"], 0) >= per:
            continue
        by[r["source"]] = by.get(r["source"], 0) + 1
        out.append(r)
    return out


rows = newest_first([("Late", 80), ("Mid", 80), ("Early", 80)])      # 'Late' was ingested last -> newest
check("A1: the LEGACY take starves the outlet ingested first (Early gets 0) - the bug this fixes",
      Counter(r["source"] for r in legacy_take(rows, 90, 60)).get("Early", 0) == 0)
fair = d._fair_take(rows, 90, 60)
check("A2: the fair take gives every outlet an equal share when the cap binds",
      Counter(r["source"] for r in fair) == Counter({"Late": 30, "Mid": 30, "Early": 30}))
check("A3: the cap is respected", len(d._fair_take(rows, 50, 60)) == 50 and len(fair) == 90)
check("A4: per_source is respected", max(Counter(r["source"] for r in d._fair_take(rows, 500, 10)).values()) == 10)
check("A5: when the cap does not bind, nothing is dropped (up to per_source)",
      len(d._fair_take(newest_first([("a", 5), ("b", 3)]), 100, 60)) == 8)
check("A6: output stays newest-first (input order) so downstream clustering sees the same order semantics",
      [r["id"] for r in fair] == sorted(r["id"] for r in fair))
check("A7: each outlet's own picks are its NEWEST rows",
      all(r["id"] < 30 or r["source"] != "Late" for r in fair if r["source"] == "Late") and
      sorted(r["id"] for r in fair if r["source"] == "Mid") == list(range(80, 110)))
check("A8: uneven outlets - a small outlet keeps all its rows and the rest share the remainder fairly",
      Counter(r["source"] for r in d._fair_take(newest_first([("big", 100), ("small", 4), ("mid", 100)]), 24, 60)) ==
      Counter({"small": 4, "big": 10, "mid": 10}))
check("A9: empty input", d._fair_take([], 100, 60) == [])

is_rated = lambda s: s.startswith("R")
is_vetted = lambda s: s.startswith("V")
mix = newest_first([("U1", 200), ("V1", 200), ("V2", 200), ("R1", 200), ("R2", 200)])
win = d.select_unclustered_window(mix, limit=100, per_source=60, is_rated=is_rated, is_vetted=is_vetted, tail_share=0.10)
cnt = Counter(r["source"] for r in win)
check("A10: rated outlets claim first: 90 of 100 slots (45 each)", cnt["R1"] == 45 and cnt["R2"] == 45)
check("A11: vetted outlets get exactly the bounded reserve (10), shared fairly", cnt["V1"] + cnt["V2"] == 10 and cnt["V1"] == 5)
check("A12: unknown long-tail domains get nothing while rated + vetted fill the window", cnt.get("U1", 0) == 0)
slack = d.select_unclustered_window(newest_first([("R1", 10), ("V1", 200), ("U1", 200)]), limit=100, per_source=60,
                                    is_rated=is_rated, is_vetted=is_vetted)
sc = Counter(r["source"] for r in slack)
check("A13: unused rated capacity flows to vetted first (up to per_source), then to unknown domains",
      sc["R1"] == 10 and sc["V1"] == 60 and sc["U1"] == 30)
check("A14: rated_first=False is a single fair pool",
      Counter(r["source"] for r in d.select_unclustered_window(rows, limit=90, per_source=60, rated_first=False)) ==
      Counter({"Late": 30, "Mid": 30, "Early": 30}))
check("A15: get_unclustered_articles keeps its public signature",
      list(inspect.signature(d.get_unclustered_articles).parameters) == ["limit", "per_source", "rated_first"])

from datetime import datetime, timedelta
NOW = datetime(2026, 9, 21, 12, 0, 0)
fresh_ts, stale_ts = (NOW - timedelta(hours=5)).isoformat(), (NOW - timedelta(hours=100)).isoformat()
aged = [{"source": "R1", "id": 1, "fetched_at": fresh_ts}, {"source": "R1", "id": 2, "fetched_at": stale_ts},
        {"source": "R2", "id": 3, "fetched_at": stale_ts}, {"source": "R3", "id": 4}]
w16 = d.select_unclustered_window(aged, limit=10, is_rated=is_rated, now=NOW)
check("A16: rows older than 72h never enter the window (fair sharing must not hand an outlet stale rows)",
      sorted(r["id"] for r in w16) == [1, 4])
check("A17: a row with no fetched_at is kept (nothing to judge it by)", 4 in {r["id"] for r in w16})
check("A18: max_age_hours=0 turns the bound off",
      len(d.select_unclustered_window(aged, limit=10, is_rated=is_rated, now=NOW, max_age_hours=0)) == 4)
check("A19: the bound is 72 hours by default", d.WINDOW_MAX_AGE_HOURS == 72)

# The production path returns sqlite3.Row objects, not dicts. A dict-only version of this test once let
# `r.get("fetched_at")` ship and crash cluster.py in the nightly run - so exercise the REAL query on an isolated DB.
import shutil
import sqlite3
import tempfile
from pathlib import Path
_orig_path, _orig_init = d.DB_PATH, d._db_initialized
_tmp = tempfile.mkdtemp()
d.DB_PATH, d._db_initialized = Path(_tmp) / "window_test.db", False
try:
    d.init_db()
    for i in range(6):
        d.insert_article("The Hindu" if i % 2 == 0 else "The Indian Express", "en", f"Story number {i} about topic{i}",
                         f"https://x.test/{i}", "an excerpt", "", "2026-09-20T00:00:00+00:00")
    _c = sqlite3.connect(d.DB_PATH)
    _c.execute("UPDATE articles SET fetched_at='2020-01-01T00:00:00' WHERE id=1")     # one stale row
    _c.commit(); _c.close()
    _rc = None
    try:
        got = d.get_unclustered_articles(limit=100, per_source=60)
        _rc = True
    except Exception as e:                                                          # noqa: BLE001
        print("   raised:", type(e).__name__, e)
        got = []
    check("A20: get_unclustered_articles runs on the real sqlite3.Row query path (no exception)", _rc is True)
    check("A21: it returns plain dicts carrying fetched_at, and drops the stale row (5 of 6)",
          len(got) == 5 and all(type(r) is dict and "fetched_at" in r for r in got) and 1 not in {r["id"] for r in got})
    _cn = sqlite3.connect(d.DB_PATH); _cn.row_factory = sqlite3.Row
    _rows = _cn.execute("SELECT id, source, fetched_at FROM articles ORDER BY fetched_at DESC").fetchall()
    _cn.close()
    check("A22: real sqlite3.Row rows go through the recency filter and the fair take",
          {r["id"] for r in d.select_unclustered_window(_rows, limit=10, is_rated=lambda s: True)} == {2, 3, 4, 5, 6})
finally:
    d.DB_PATH, d._db_initialized = _orig_path, _orig_init
    shutil.rmtree(_tmp, ignore_errors=True)

# ---------------------------------------------------------------- B. source selection
print("\n=== B: prompt source selection ===")
OWN = lambda n: {"TOI": "Times", "NBT": "Times", "HT": "HT", "Mint": "HT"}.get(n, n)
LEAN = lambda n: {"Wire A": "center", "Wire B": "center", "Wire C": "center", "TOI": "center", "NBT": "center", "HT": "center", "Mint": "center",
                  "LeftOne": "left", "RightOne": "right", "Reuters": "international", "GDELTblog.com": "unrated"}.get(n, "center")


class Info:                                       # deterministic stand-in for the registry
    def region(self, n):
        return {"Reuters": "UK", "LeftOne": "India", "RightOne": "India", "GDELTblog.com": None}.get(n, "India")

    def credibility(self, n):
        return 0.3 if n == "GDELTblog.com" else 1.0

    def underlying_lean(self, n):
        return None


def art(i, src, title, summary="", pub="2026-09-20T10:00:00+00:00"):
    return {"id": i, "source": src, "title": title, "summary": summary, "published": pub, "language": "en", "url": f"https://x/{i}"}


wire = "Cabinet approves new metro line for Pune city"
arts = [art(1, "Wire A", wire), art(2, "Wire B", wire + " - Wire B"), art(3, "Wire C", wire.lower()),
        art(4, "LeftOne", "Opposition slams metro plan"), art(5, "RightOne", "Government hails metro plan")]
groups = ss.report_groups(arts, LEAN, OWN)
check("B1: three mastheads republishing one wire headline (same lean) are ONE independent report", len(groups) == 3)
check("B2: cross-lean articles never merge (each side keeps its own voice)",
      any(len(g) == 3 for g in groups) and all(len({LEAN(a['source']) for a in g}) == 1 for g in groups))
co = [art(10, "TOI", "Pune metro approved by cabinet today"), art(11, "NBT", "पुणे मेट्रो को मंज़ूरी")]
check("B3: two mastheads of ONE owner collapse to one report even with different headlines",
      len(ss.report_groups(co, LEAN, OWN)) == 1)

pick = ss.select_sources(arts, LEAN, OWN, k=12, min_per_lean=2, info=Info())
check("B4: one representative per report (5 articles -> 3 reports picked)", len(pick) == 3)
check("B5: every covered side is present", {LEAN(a["source"]) for a in pick} == {"center", "left", "right"})
rich = [art(20, "Wire A", wire, summary=""), art(21, "Wire B", wire, summary="x" * 280)]
check("B6: the richest copy represents its report", ss.select_sources(rich, LEAN, OWN, info=Info())[0]["id"] == 21)

many = [art(100 + i, f"Center{i}", f"Distinct story number {i} about topic{i} alpha{i}") for i in range(20)] + \
       [art(200, "LeftOne", "Left take on the story"), art(201, "RightOne", "Right take on the story")]
p2 = ss.select_sources(many, LEAN, OWN, k=12, min_per_lean=2, info=Info())
check("B7: never more than k picks and no duplicates", len(p2) == 12 and len({a["id"] for a in p2}) == 12)
check("B8: a lean with few articles is NOT crowded out by a lean with many (guarantee kept)",
      {200, 201} <= {a["id"] for a in p2})
check("B9: only the event's own articles are ever returned", {a["id"] for a in p2} <= {a["id"] for a in many})
check("B10: deterministic - same input, same output, whatever the input order",
      [a["id"] for a in p2] == [a["id"] for a in ss.select_sources(list(reversed(many)), LEAN, OWN, k=12, min_per_lean=2, info=Info())])
reg = [art(30 + i, f"Center{i}", f"Different report {i} zeta{i} omega{i}") for i in range(3)] + [art(40, "Reuters", "Overseas view of the matter")]
r1 = ss.select_sources(reg, LEAN, OWN, k=2, min_per_lean=1, info=Info())
check("B11: with limited slots the pick spreads across home regions (India + UK, not two India outlets)",
      {Info().region(a["source"]) for a in r1} == {"India", "UK"})
check("B12: a single article passes straight through", ss.select_sources([arts[0]], LEAN, OWN, info=Info()) == [arts[0]])
check("B13: the unrated long tail ranks below a rated outlet when slots are scarce",
      ss.select_sources([art(50, "GDELTblog.com", "Blog post on the metro", "x" * 300), art(51, "Center1", "Center report on metro line")],
                        LEAN, OWN, k=1, min_per_lean=0, info=Info())[0]["source"] == "Center1")
check("B14: every curated INTERNATIONAL outlet has a home region (so region can be judged)",
      all(s["name"] in ss.HOME_REGION_INTL for s in sources.SOURCES if s.get("region") == "International"))
info = ss.SourceInfo()
check("B15: registry-derived facts are sane (curated India -> India; reviewed > provisional credibility)",
      info.region("The Hindu") == "India" and info.region("Reuters") == "UK" and info.region("no-such-outlet.com") is None
      and info.credibility("The Hindu") >= 0.8 and info.credibility("no-such-outlet.com") == 0.3)

# A REAL World story (event 22107, Folkestone hotel fire): at prompt time all four UK outlets read
# "international", but they vote left (Daily Mirror, The Independent) and centre (Sky News, Metro) once the
# story is classified World. The picker must still hear BOTH sides, or a covered side would get no framing input.
real = ss.SourceInfo()
world = [art(1, "Sky News", "Dozens moved from homes due to safety concerns after Folkestone hotel fire - as police treat blaze as suspicious", "x" * 121),
         art(2, "Sky News", "Fire at Folkestone's Grand Burstin Hotel being treated as suspicious, police say", "x" * 89),
         art(3, "The Independent", "Folkestone hotel fire: Major blaze at Grand Burstin Hotel being treated as suspicious, police say", "x" * 113),
         art(4, "The Independent", "Dozens of people living next to fire-hit hotel moved over safety fears", "x" * 86),
         art(5, "Daily Mirror", "Folkestone hotel fire being treated as suspicious, say police", "x" * 74),
         art(6, "Metro (UK)", "Locals forced to flee as Folkestone hotel 'deliberately set on fire'", "x" * 80)]
wl = lambda n: analyze.lean_of(n)
wown = lambda n: sources.OWNER_BY_SOURCE.get(n, n)
wp = ss.select_sources(world, wl, wown, k=12, min_per_lean=2, info=real)
under = {real.underlying_lean(a["source"]) for a in wp}
check("B16: World story - international outlets that vote on DIFFERENT leans are never merged into one report",
      len(ss.report_groups(world, lambda n: (wl(n), real.underlying_lean(n)), wown)) >= 3)
check("B17: World story - the pick still contains a left-lean AND a centre-lean outlet (both sides get framing input)",
      {"left", "center"} <= under)
check("B18: World story - copies within one underlying lean still collapse (fewer picks than articles)",
      len(wp) < len(world))
check("B19: underlying_lean reads the registry (Sky News centre, Daily Mirror left, unknown None)",
      real.underlying_lean("Sky News") == "center" and real.underlying_lean("Daily Mirror") == "left" and real.underlying_lean("nope.com") is None)

# ---------------------------------------------------------------- C. build_prompt keeps the arithmetic + the sides
print("\n=== C: build_prompt integration ===")
c_arts = ([art(300 + i, "The Hindu", "Same wire story headline about floods in Assam today") for i in range(1)] +
          [art(310, "The Indian Express", "Same wire story headline about floods in Assam today"),
           art(311, "Republic World", "Republic covers floods differently in Assam region"),
           art(312, "OpIndia", "OpIndia on the Assam floods and relief work"),
           art(313, "Hindustan Times", "HT reports Assam flood relief numbers rising")] +
          [art(320 + i, f"Unrated{i}.com", f"Filler unrated article {i} about unrelated things{i}") for i in range(20)])
for a in c_arts:
    a["url"] = a.get("url") or "https://x/" + str(a["id"])
prompt = analyze.build_prompt(c_arts)
expected_counts = {side: len({sources.OWNER_BY_SOURCE.get(a["source"], a["source"]) for a in c_arts if analyze.lean_of(a["source"]) == side})
                   for side in analyze.LEAN_ORDER}
line = f"LEFT: {expected_counts['left']} owner(s) - CENTRE: {expected_counts['center']} owner(s) - RIGHT: {expected_counts['right']} owner(s)"
check("C1: the per-side owner counts in the prompt come from ALL articles, not from the picked subset", line in prompt)
check("C2: outlets of every covered side reach the prompt",
      all(n in prompt for n in ("OUTLET: The Hindu", "OUTLET: Republic World", "OUTLET: OpIndia")) or
      sum(1 for n in ("The Hindu", "Republic World", "OpIndia", "The Indian Express", "Hindustan Times") if f"OUTLET: {n}" in prompt) >= 4)
check("C3: no more than MAX_ARTICLES_PER_EVENT outlets are in the prompt", prompt.count("OUTLET:") <= analyze.MAX_ARTICLES_PER_EVENT)
check("C4: a duplicated wire headline is shown once", prompt.count("HEADLINE: Same wire story headline about floods in Assam today") == 1 or
      analyze.lean_of("The Hindu") != analyze.lean_of("The Indian Express"))

# The label the model sees must be the lean the arithmetic will COUNT. On a World story (region known only on the retry) an
# international outlet with a known underlying lean votes on it; labelling it "international wire" left a covered side with no
# attributable outlet, no framing was written and the completeness gate hid the story (40% of such sides).
import re as _re
import source_enrichment as _se
_se.get_combined_summary_for_article = lambda a: a.get("summary") or ""                # no network / no DB cache writes
lab_arts = [art(900, "Sky News", "Fire at hotel treated as suspicious", "x" * 90), art(901, "Daily Mirror", "Locals flee hotel blaze", "x" * 90),
            art(902, "The Hindu", "Hindu view of the hotel fire", "x" * 90)]
def _labels(region):
    return dict(_re.findall(r"OUTLET: ([A-Za-z ]+?)  \[lean: ([^,]+),", analyze.build_prompt(lab_arts, region=region)))
check("C5: first attempt (region unknown) still labels international outlets 'international wire' (unchanged)",
      _labels(None)["Sky News"] == "international wire" and _labels(None)["Daily Mirror"] == "international wire")
check("C6: an India story keeps international outlets non-voting: 'international wire' (unchanged)",
      _labels("India")["Sky News"] == "international wire")
check("C7: a World story labels them with the underlying lean the arithmetic counts (Sky centrist, Mirror left-leaning)",
      _labels("World")["Sky News"] == "centrist" and _labels("World")["Daily Mirror"] == "left-leaning")
check("C8: labels of India outlets never depend on region", _labels(None)["The Hindu"] == _labels("India")["The Hindu"] == _labels("World")["The Hindu"])

# analyze_event's retry must keep the region it was PROMPTED with (labels + owner counts were built for it).
_calls = []
def _fake_call(prompt, retries=1, backend=None):
    _calls.append(prompt)
    base = {"title": "Hotel fire treated as suspicious", "summary": "Police say the blaze is suspicious.", "topic": "Crime & Law",
            "framing": {"left": [], "center": ["Centre framing text."], "right": []}, "region": "World"}
    if len(_calls) == 1:
        return dict(base)                                                          # first pass: World, left side has no framing -> incomplete
    return dict(base, region="India", framing={"left": ["Left framing."], "center": ["Centre framing."], "right": []})   # retry flips to India
_real_call = analyze._call_json
analyze._call_json = _fake_call
try:
    res_flip = analyze.analyze_event([dict(a) for a in world], backend="test")
finally:
    analyze._call_json = _real_call
check("C9: the retry prompt was built for the first attempt's region (World labels)", len(_calls) == 2 and "centrist" in _calls[1] and "left-leaning" in _calls[1])
check("C10: a retry that re-classifies the story keeps the region it was prompted with (World stays World)", res_flip["region"] == "World")
check("C11: so the international outlets still vote (the story is not left with zero voting sides)",
      sum(res_flip["coverage"][s]["count"] for s in ("left", "center", "right")) >= 2)

# ---------------------------------------------------------------- D. GDELT failure handling
print("\n=== D: GDELT failure handling ===")
import gdelt_source as g
import time as _time

_sleeps = []
g.time.sleep = lambda s: _sleeps.append(s)                     # never really sleep in a test
g.random.uniform = lambda a, b: 0.0
g.gdelt_gate.wait_for_slot = lambda *a, **k: 0.0                # Phase 21C: gate has its own real-time/real-lock
                                                                 # path; a unit test must never touch either
g.METRICS_PATH = os.path.join(tempfile.mkdtemp(), "test_gdelt_metrics.jsonl")  # Phase 21D: never touch the real file


class FakeResp:
    def __init__(self, body): self._b = body
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


_real_urlopen = g.urllib.request.urlopen
g.urllib.request.urlopen = lambda req, timeout=60: FakeResp(b"<html>Please limit requests to one every 5 seconds</html>")
try:
    g._fetch("q", retries=3)
    raised = False
except urllib.error.URLError:
    raised = True
check("D1: a non-JSON (overload) reply is a FAILED query (it used to return [] silently)", raised)
check("D2: it is retried with back-off before giving up", len(_sleeps) == 2)
g.urllib.request.urlopen = lambda req, timeout=60: FakeResp(b'{"articles": [{"url": "https://a/1", "title": "t"}]}')
check("D3: a JSON reply still works", g._fetch("q", retries=1) == [{"url": "https://a/1", "title": "t"}])
g.urllib.request.urlopen = _real_urlopen

calls = []
g.init_db = lambda: None
g.insert_article = lambda *a, **k: None
g._fetch = lambda q, timespan=None, **k: (calls.append(q), (_ for _ in ()).throw(urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)))[1]
g.run(queries=[f"q{i}" for i in range(16)], verbose=False)
check("D4: 3 failed queries in a row stop the stage (3 of 16 attempted, not 16 x retries)", len(calls) == 3)

seq = iter([False, False, True, False, False, True, False, False, False, True, True])
calls2 = []


def flaky(q, timespan=None, **k):
    calls2.append(q)
    if next(seq):
        return []
    raise urllib.error.URLError("dns")


g._fetch = flaky
g.run(queries=[f"q{i}" for i in range(11)], verbose=False)
check("D5: a success resets the consecutive-failure counter (stopped only at the 3rd straight failure, query 9)", len(calls2) == 9)

_farm = {"title": "Asian Games 2026 : Elavenil leads India Day 1 charge", "url": "https://laosnews.net/a", "language": "English", "domain": "laosnews.net"}
_ani = dict(_farm, url="https://aninews.in/a", domain="aninews.in")
check("D6: the newly measured syndication-farm family is dropped at ingest (laosnews.net, shanghaisun.com, bignewsnetwork.com, ...)",
      g.normalize_gdelt(_farm) is None and all(x in g._BLOCKLIST for x in ("shanghaisun.com", "bignewsnetwork.com", "iranherald.com", "singaporestar.com")))
check("D7: ANI (a real wire agency) is NOT blocked - that is an editorial call, not a measurement", g.normalize_gdelt(_ani) is not None)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
