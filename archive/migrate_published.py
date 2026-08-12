"""
migrate_published.py
--------------------
One-time backfill: stamp every existing event with `published_at` -- the real publish
time of its NEWEST member article -- inside analysis_json, so the feed can show
"x ago" as when the NEWS happened instead of when the pipeline last touched it.

New/continuing events already get published_at from analyze.postprocess(); this only
fills the events that were analysed before that field existed. It is ADDITIVE: it writes
one new JSON key and changes nothing else -- not created_at, not the summary, not a single
bias/coverage count. Events whose member articles carry no parseable date are left as-is
(the UI falls back to created_at for them).

Usage:
    py migrate_published.py            # DRY RUN: report only, writes nothing
    py migrate_published.py --apply    # write published_at into analysis_json

Back up paksh.db before --apply, per the project's clean-rebuild habit.
"""

import json
import re
import sys
from datetime import datetime, timezone

from database import get_connection


def _newest_published(published_values):
    """Newest parseable publish time among an event's member articles, as a naive-UTC ISO
    string; None if nothing parses. Same rules the pipeline uses: ISO-8601 (RSS) and
    YYYYMMDD (GDELT), clamped to now so a bad future date can't win. Inlined here so this
    one-time script stays independent of the heavy pipeline import chain."""
    best = None
    now = datetime.now(timezone.utc)
    for raw in published_values:
        raw = (raw or "").strip()
        if not raw:
            continue
        dt = None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            if re.fullmatch(r"\d{8}", raw):
                try:
                    dt = datetime(int(raw[:4]), int(raw[4:6]), int(raw[6:8]), tzinfo=timezone.utc)
                except ValueError:
                    dt = None
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > now:
            dt = now
        if best is None or dt > best:
            best = dt
    if best is None:
        return None
    return best.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def main(apply: bool) -> None:
    conn = get_connection()
    # One pass over the articles table (event_id isn't indexed, so per-event queries would
    # each scan all ~48k rows). Group published dates by event in memory instead.
    pub_by_event = {}
    for a in conn.execute(
        "SELECT event_id, published FROM articles WHERE event_id IS NOT NULL"
    ):
        pub_by_event.setdefault(a["event_id"], []).append(a["published"])

    rows = conn.execute("SELECT id, analysis_json FROM events").fetchall()
    total = len(rows)
    would_set = skipped_has = skipped_nodate = 0

    for r in rows:
        try:
            data = json.loads(r["analysis_json"])
        except (ValueError, TypeError):
            continue
        if data.get("published_at"):          # already stamped -> leave it
            skipped_has += 1
            continue
        pub = _newest_published(pub_by_event.get(r["id"], []))
        if not pub:                            # no parseable date -> UI falls back
            skipped_nodate += 1
            continue
        would_set += 1
        if apply:
            data["published_at"] = pub
            conn.execute(
                "UPDATE events SET analysis_json = ? WHERE id = ?",
                (json.dumps(data, ensure_ascii=False), r["id"]),
            )

    if apply:
        conn.commit()
    conn.close()

    verb = "Set" if apply else "Would set"
    print(f"Events scanned:            {total}")
    print(f"Already had published_at:  {skipped_has}")
    print(f"No parseable article date: {skipped_nodate}")
    print(f"{verb} published_at on:      {would_set}")
    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply to save.")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
