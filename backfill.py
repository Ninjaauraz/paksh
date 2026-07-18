"""
backfill.py - ripen extractive events into full LLM briefs using spare local
compute.

The two-tier pipeline publishes the most-covered events with a real neutral LLM
summary and the long tail with an instant extractive one (a covering outlet's
own headline). This script upgrades those extractive events to full briefs in
the background, most-covered first, via the active LLM backend (Ollama by
default). It is:

  - NON-BLOCKING: run it (or schedule it) whenever the machine is idle; it never
    touches a live `refresh.py` run.
  - SAFE TO STOP: each event is committed as it finishes, so Ctrl-C loses at most
    one in-flight summary.
  - SELF-HEALING: an upgraded event flips summary_method to "llm", so its
    "Auto-summary" badge disappears on the next `export_static.py`. If the LLM is
    unavailable the event is simply left extractive and retried next time.
  - PLACE-PRESERVING: created_at is untouched, so upgrades don't reorder the feed.

    py backfill.py                 # upgrade up to BACKFILL_CAP events
    py backfill.py --cap 50        # custom per-run cap
    py backfill.py --all           # grind through every extractive event

Run `python export_static.py` afterwards to publish the upgraded briefs.
"""

import json
import sys

from database import get_connection, init_db
from analyze import analyze_event

BACKFILL_CAP = 20      # events upgraded per run by default (each ~ one LLM call)


def _extractive_events(conn):
    """Ids of stored extractive events, NEWEST first (created_at desc), then
    most-covered. Front-page stubs (today's events, at the top of the created_at-DESC
    homepage) get ripened before older buried ones, so a capped/interrupted run fixes
    what visitors actually see first."""
    rows = conn.execute(
        "SELECT id, analysis_json, created_at FROM events WHERE is_demo = 0"
    ).fetchall()
    pending = []
    for r in rows:
        try:
            data = json.loads(r["analysis_json"])
        except (ValueError, TypeError):
            continue
        if data.get("summary_method") == "extractive":
            pending.append((r["id"], r["created_at"] or "", len(data.get("sources", []))))
    # newest first; within the same timestamp, most-covered first
    pending.sort(key=lambda t: (t[1], t[2]), reverse=True)
    return [eid for eid, _, _ in pending]


def _event_articles(conn, event_id):
    rows = conn.execute(
        """SELECT id, source, language, title, summary, url, image_url
           FROM articles WHERE event_id = ?""",
        (event_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _update_event(conn, event_id, analysis):
    """Write the upgraded brief in place. Updates the table's title/summary
    columns (used by the list feed) AND analysis_json (used by the detail page);
    leaves created_at alone so the event keeps its place in the feed."""
    conn.execute(
        "UPDATE events SET title = ?, summary = ?, analysis_json = ? WHERE id = ?",
        (
            analysis.get("title", "Untitled event"),
            analysis.get("summary", ""),
            json.dumps(analysis, ensure_ascii=False),
            event_id,
        ),
    )
    conn.commit()


def run(cap=BACKFILL_CAP, do_all=False, verbose=True):
    init_db()
    conn = get_connection()
    ids = _extractive_events(conn)
    total = len(ids)
    todo = ids if do_all else ids[:cap]
    if verbose:
        print(f"{total} extractive event(s) pending; upgrading {len(todo)} this run "
              f"(most-covered first).")

    upgraded = left = 0
    for i, eid in enumerate(todo, 1):
        arts = _event_articles(conn, eid)
        if len(arts) < 2:                              # event lost its articles
            left += 1
            continue
        try:
            analysis = analyze_event(arts)
        except Exception as e:
            if verbose:
                print(f"  [{i}/{len(todo)}] event {eid}: skipped ({e})")
            left += 1
            continue
        if analysis.get("summary_method") != "llm":    # LLM was unavailable
            if verbose:
                print(f"  [{i}/{len(todo)}] event {eid}: LLM unavailable, left extractive")
            left += 1
            continue
        _update_event(conn, eid, analysis)
        upgraded += 1
        if verbose:
            print(f"  [{i}/{len(todo)}] event {eid} -> {analysis['title'][:56]}")

    conn.close()
    if verbose:
        print(f"\nUpgraded {upgraded}, left {left}. "
              f"{total - upgraded} extractive event(s) remain.")
        if upgraded:
            print("Next:  python export_static.py   (to publish the upgraded briefs)")
    return upgraded


if __name__ == "__main__":
    cap, do_all = BACKFILL_CAP, ("--all" in sys.argv)
    if "--cap" in sys.argv:
        j = sys.argv.index("--cap")
        if j + 1 < len(sys.argv):
            cap = int(sys.argv[j + 1])
    run(cap=cap, do_all=do_all)