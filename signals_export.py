"""
signals_export.py
-----------------
Redstocks market-signal export (INTERNAL - never published to the site).

The thesis (see the tracking plan): aggregate NEWS ATTENTION + coverage divergence is a
real-time sentiment/attention dataset that can feed market-prediction models - and it lives
in the CORPUS Paksh already generates, needing ZERO user tracking. This script turns the
event store into a clean, model-ready dataset:

  signals/events.csv       one row per event: day, topic, region, L/C/R/intl/unrated outlet
                           counts, breadth (attention), polarisation, gap (blindspot) score.
  signals/daily.csv        per DAY x TOPIC: event_count, breadth (total distinct-outlet
                           attention), lean shares, one-sided count - the time series you
                           model against prices.
  signals/signals.json     both of the above + a run summary, as one JSON blob.

Attention proxy = BREADTH = distinct rated + international outlets covering an event (the same
number the bias bar rests on). Polarisation = |L-R| / (L+C+R). Gap = (L-R)^2 / (L+R). None of
this reads a single user event - it is entirely the coverage corpus.

Usage:
    py signals_export.py                 # last 30 days
    py signals_export.py --days 90
    py signals_export.py --out signals   # output dir (default: signals/)

This directory is INTERNAL. Do not add it to _site/ or commit large dumps.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from database import get_all_events


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _day(e):
    """The event's real-world day: newest source article's publish date, else pipeline date."""
    stamp = (e.get("published_at") or e.get("created_at") or "")[:19].replace("Z", "")
    try:
        return datetime.fromisoformat(stamp).date().isoformat()
    except ValueError:
        return None


def build(days: int):
    cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    events = get_all_events()

    rows = []
    for e in events:
        day = _day(e)
        if not day or day < cutoff:
            continue
        lc = e.get("lean_counts") or {}
        L, C, R = lc.get("left", 0), lc.get("center", 0), lc.get("right", 0)
        intl = e.get("international", 0) or 0
        unrated = max(0, (e.get("source_count", 0) or 0) - (L + C + R) - intl)
        rated = L + C + R
        breadth = rated + intl                    # attention = distinct covering outlets
        polar = round(abs(L - R) / rated, 4) if rated else 0.0   # coverage divergence
        gap = round((L - R) ** 2 / (L + R), 4) if (L + R) else 0.0
        bs = e.get("blindspot") or {}
        rows.append({
            "day": day, "event_id": e["id"], "topic": e.get("topic", "General"),
            "region": e.get("region", "India"),
            "left": L, "center": C, "right": R, "intl": intl, "unrated": unrated,
            "breadth": breadth, "polarisation": polar, "gap_score": gap,
            "blindspot_side": (bs.get("side") if isinstance(bs, dict) else None) or "",
            "title": (e.get("title") or "")[:140],
        })

    # per DAY x TOPIC time series
    agg = defaultdict(lambda: {"events": 0, "breadth": 0, "left": 0, "center": 0,
                               "right": 0, "one_sided": 0})
    for r in rows:
        k = (r["day"], r["topic"])
        a = agg[k]
        a["events"] += 1
        a["breadth"] += r["breadth"]
        a["left"] += r["left"]; a["center"] += r["center"]; a["right"] += r["right"]
        if r["blindspot_side"]:
            a["one_sided"] += 1
    daily = []
    for (day, topic), a in sorted(agg.items()):
        tot = a["left"] + a["center"] + a["right"]
        daily.append({
            "day": day, "topic": topic, "events": a["events"], "breadth": a["breadth"],
            "left": a["left"], "center": a["center"], "right": a["right"],
            "left_share": round(a["left"] / tot, 4) if tot else 0,
            "center_share": round(a["center"] / tot, 4) if tot else 0,
            "right_share": round(a["right"] / tot, 4) if tot else 0,
            "one_sided": a["one_sided"],
        })
    return rows, daily


def _write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    days = int(_arg("--days", "30"))
    out = Path(_arg("--out", "signals"))
    out.mkdir(parents=True, exist_ok=True)

    rows, daily = build(days)
    _write_csv(out / "events.csv", rows)
    _write_csv(out / "daily.csv", daily)
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "window_days": days,
        "event_rows": len(rows),
        "daily_rows": len(daily),
        "topics": sorted({r["topic"] for r in rows}),
        "days_covered": len({r["day"] for r in rows}),
    }
    (out / "signals.json").write_text(
        json.dumps({"summary": summary, "events": rows, "daily": daily},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Signals export -> {out}/")
    print(f"  window: last {days} days · {summary['days_covered']} days with coverage")
    print(f"  events.csv: {len(rows):,} rows   daily.csv: {len(daily):,} rows")
    print(f"  topics: {', '.join(summary['topics'])}")


if __name__ == "__main__":
    main()
