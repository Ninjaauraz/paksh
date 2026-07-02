"""
reframe.py - targeted re-analysis for the framing fixes.

Finds existing events where a lean HAS coverage but its framing text is empty - the
"missing side" case - and re-runs the LLM summary + framing on just those events, using
the now-fixed, lean-balanced build_prompt (so no covered side is dropped) and the
collective-side framing prompt. It does NOT re-analyse the whole catalogue, and it
preserves each event's original created_at, so the feed order does not reshuffle.

Safety: it only overwrites an event when the fresh analysis actually fills at least one
of the previously-missing sides. If the LLM backend is down (analysis falls back to an
extractive brief with no framing), the event is skipped rather than degraded.

Requires the LLM backend running, exactly like analyze.py:
    - Ollama running (for local), and/or Gemini configured
    - set PAKSH_LLM_BACKEND=hybrid  (else slow all-local cycles)

Usage (Windows PowerShell, from the project folder):
    py reframe.py                      # dry run - list affected events, change nothing
    py reframe.py --apply              # re-analyse them all
    py reframe.py --apply --limit 50   # do 50 at a time (safe to run in batches)
    py reframe.py --apply --ids 812,905  # force specific event ids

After --apply, rebuild and deploy as usual:
    py export_static.py   ->  push via GitHub Desktop
"""

import argparse

from database import (
    init_db, get_all_events, get_event, get_event_articles, update_event,
)
from analyze import analyze_event

SIDES = ("left", "center", "right")


def _missing_sides(ev):
    """Leans that HAVE coverage but NO framing text - the sides to rescue."""
    cov = ev.get("coverage") or {}
    fr = ev.get("framing") or {}
    return [s for s in SIDES
            if (cov.get(s) or {}).get("count", 0) > 0
            and not (fr.get(s) or "").strip()]


def _collect(ids):
    """Full events that need re-framing (or the explicit --ids set)."""
    if ids:
        out = []
        for i in ids:
            ev = get_event(i)
            if ev:
                out.append(ev)
        return out
    out = []
    for row in get_all_events():
        ev = get_event(row["id"])
        if ev and _missing_sides(ev):
            out.append(ev)
    return out


def main():
    ap = argparse.ArgumentParser(description="Re-frame events with a covered-but-unframed side.")
    ap.add_argument("--apply", action="store_true", help="actually re-analyse (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="process at most N events (batching)")
    ap.add_argument("--ids", default="", help="comma-separated event ids to force")
    args = ap.parse_args()

    init_db()

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    targets = _collect(ids)
    if args.limit:
        targets = targets[:args.limit]

    print(f"{len(targets)} event(s) to re-frame" + ("" if args.apply else "  (dry run)"))
    for ev in targets:
        miss = _missing_sides(ev) or ["(forced)"]
        print(f"  #{ev['id']:>5}  missing: {','.join(miss):<22}  {(ev.get('title') or '')[:58]}")

    if not targets:
        print("Nothing to do - every covered side already has framing.")
        return
    if not args.apply:
        print("\nDry run only. Re-run with --apply once the LLM backend is running "
              "(Ollama up, PAKSH_LLM_BACKEND=hybrid).")
        return

    done = skipped = 0
    for ev in targets:
        eid = ev["id"]
        want = set(_missing_sides(ev)) or set(SIDES)
        rows = get_event_articles(eid)
        if not rows:
            skipped += 1
            continue
        analysis = analyze_event(rows)             # fixed build_prompt + framing prompt
        new_fr = analysis.get("framing") or {}
        filled = [s for s in want if (new_fr.get(s) or "").strip()]
        if not filled:
            # LLM produced no framing for the missing side(s) - do NOT overwrite a good
            # brief with an empty/extractive one. Most common cause: backend not running.
            print(f"  skip  #{eid}  (no framing produced - is the LLM backend up?)")
            skipped += 1
            continue
        update_event(eid, analysis, bump_created=False)   # keep original timestamp
        done += 1
        print(f"  ok    #{eid}  filled: {','.join(filled)}")

    print(f"\nDone. re-framed {done}, skipped {skipped}.")
    if done:
        print("Next: py export_static.py   then push via GitHub Desktop.")


if __name__ == "__main__":
    main()