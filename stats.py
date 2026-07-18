#!/usr/bin/env python3
"""
stats.py
--------
READ-ONLY health report for the Paksh catalogue. Answers "what shape is the
database in right now" without opening paksh.db by hand: how many events,
how fresh, how many are actually multi-outlet with a real left/right spread,
how big the reframe/extractive backlogs are, plus the topic/region spread and
the source-roster balance from sources.py.

Touches nothing - only SELECT queries and a read of the sources.py registry.
Safe to run any time, including while ingest / analyze / live are running.

Usage:
    py stats.py            human-readable report
    py stats.py --json     same numbers as JSON (for scripts/monitoring)
"""

import argparse
import json as _json
from datetime import datetime, timedelta

from database import init_db, get_connection, LEAN_ORDER
from sources import coverage_summary

SIDES = LEAN_ORDER  # ["left", "center", "right"] - the sides that vote in the bias bar


def _lean_counts(data):
    cov = data.get("coverage") or {}
    return {s: (cov.get(s) or {}).get("count", 0) for s in SIDES}


def _has_empty_framing(data):
    """A side the event actually covers, but whose framing text is blank -
    exactly what reframe.py looks for."""
    cov = data.get("coverage") or {}
    fr = data.get("framing") or {}
    return any((cov.get(s) or {}).get("count", 0) > 0 and not (fr.get(s) or "").strip()
               for s in SIDES)


def collect():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, analysis_json, created_at, is_demo FROM events "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    now = datetime.utcnow()
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()

    total = len(rows)
    demo = 0
    created_24h = created_7d = 0
    single_outlet = multi_outlet = 0
    bias_spread = 0
    empty_framing_backlog = 0
    extractive = 0
    unparseable = 0
    by_topic, by_region = {}, {}

    for r in rows:
        try:
            data = _json.loads(r["analysis_json"])
        except Exception:
            unparseable += 1
            continue

        if r["is_demo"]:
            demo += 1

        created = r["created_at"] or ""
        if created >= cutoff_24h:
            created_24h += 1
        if created >= cutoff_7d:
            created_7d += 1

        total_sources = data.get("total_sources")
        if total_sources is None:
            total_sources = len(data.get("sources") or [])
        if total_sources <= 1:
            single_outlet += 1
        else:
            multi_outlet += 1

        counts = _lean_counts(data)
        if sum(1 for s in SIDES if counts.get(s, 0) > 0) >= 2:
            bias_spread += 1

        if _has_empty_framing(data):
            empty_framing_backlog += 1

        if data.get("summary_method") == "extractive":
            extractive += 1

        topic = data.get("topic") or "(none)"
        by_topic[topic] = by_topic.get(topic, 0) + 1
        region = data.get("region") or "(none)"
        by_region[region] = by_region.get(region, 0) + 1

    # How many of these events the site actually shows: get_all_events() hides
    # anything with fewer than 2 rated (left/center/right) outlets voting, so
    # the site total can legitimately be lower than the raw row count above.
    from database import get_all_events
    visible_on_site = len(get_all_events())

    roster = coverage_summary()

    return {
        "total_events": total,
        "demo_events": demo,
        "unparseable_rows": unparseable,
        "created_last_24h": created_24h,
        "created_last_7d": created_7d,
        "single_outlet_events": single_outlet,
        "multi_outlet_events": multi_outlet,
        "genuine_bias_spread_events": bias_spread,
        "empty_framing_backlog": empty_framing_backlog,
        "extractive_summaries": extractive,
        "llm_summaries": total - unparseable - extractive,
        "visible_on_site": visible_on_site,
        "by_topic": dict(sorted(by_topic.items(), key=lambda kv: -kv[1])),
        "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
        "source_roster": roster,
    }


def print_report(s):
    print("Paksh catalogue health")
    print("=" * 40)
    print(f"Total events in database:        {s['total_events']}")
    if s["demo_events"]:
        print(f"  (of which demo/seed events:    {s['demo_events']})")
    if s["unparseable_rows"]:
        print(f"  (of which unreadable rows:     {s['unparseable_rows']})")
    print(f"Created in last 24h:              {s['created_last_24h']}")
    print(f"Created in last 7d:               {s['created_last_7d']}")
    print()
    print(f"Single-outlet events:             {s['single_outlet_events']}")
    print(f"Multi-outlet events:              {s['multi_outlet_events']}")
    print(f"Genuine bias spread (2+ leans):   {s['genuine_bias_spread_events']}")
    print(f"Visible on site (passes gate):    {s['visible_on_site']}")
    print()
    print(f"Empty-framing backlog (reframe):  {s['empty_framing_backlog']}")
    print(f"Extractive/fallback summaries:    {s['extractive_summaries']}")
    print(f"Proper LLM summaries:             {s['llm_summaries']}")
    print()
    print("By topic:")
    for k, v in s["by_topic"].items():
        print(f"  {k:<20} {v}")
    print()
    print("By region:")
    for k, v in s["by_region"].items():
        print(f"  {k:<20} {v}")
    print()
    roster = s["source_roster"]
    print(f"Source roster ({roster['total']} outlets total):")
    for lean in ("left", "center", "right"):
        print(f"  {lean:<10} {roster['by_lean'].get(lean, 0)}")
    other = {k: v for k, v in roster["by_lean"].items() if k not in ("left", "center", "right")}
    for k, v in other.items():
        print(f"  {k:<10} {v}")
    print(f"  contested  {roster['contested']}")


def main():
    ap = argparse.ArgumentParser(description="Read-only health report for the Paksh catalogue.")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON instead")
    args = ap.parse_args()

    stats = collect()
    if args.json:
        print(_json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print_report(stats)


if __name__ == "__main__":
    main()
