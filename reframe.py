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
    py reframe.py --top-tier           # dry run of ONLY the high-value tier
    py reframe.py --apply              # re-analyse them all (ranked, highest value first)
    py reframe.py --apply --top-tier   # re-frame ONLY the high-value tier
    py reframe.py --apply --limit 50   # do 50 at a time (safe to run in batches)
    py reframe.py --apply --ids 812,905  # force specific event ids

Ranking: events are ordered highest-value first, so a capped or quota-limited pass
fixes what visitors actually see. The TOP TIER is an event that is visible on the site
(>=2 rated outlets vote) AND has genuine L/C/R spread (2+ different leans cover it) AND
still has a covered side with no framing. Everything else ranks below it.

After --apply, rebuild and deploy as usual:
    py export_static.py   ->  push via GitHub Desktop
"""

import argparse

from database import (
    init_db, get_all_events, get_events_by_ids, get_event_articles, update_event,
)
from analyze import (
    analyze_event, has_framing, MIN_SIDE_OWNERS, reset_retry_stats, get_retry_stats,
)

SIDES = ("left", "center", "right")

# Paksh 7B: of a capped run's --limit, this many slots are reserved for single-lane
# events (only one side covered) regardless of rank. _rank_key() always sorts
# multi-lean/top-tier events first, so without this reservation a single-lane event
# is NEVER reached by any realistic cap - the local backlog audit found 7,504
# multi-lean gap events ahead of every single-lane one in the sort order, versus a
# 300/event daily cap. Bounded and small on purpose: repairs the existing ~1,602
# single-lane backlog in ~32 daily runs at this rate while leaving the bulk of the
# cap for the higher-value multi-lean/top-tier backlog, which was already
# comfortably keeping pace with new gaps at the full 300/day.
SINGLE_LANE_RESERVE = 50


def _missing_sides(ev):
    """Leans with ENOUGH unique coverage (>= MIN_SIDE_OWNERS distinct owners) but no
    framing - the sides worth rescuing. A side below that threshold is EXPECTED to be
    blank (the UI shows 'not enough unique coverage'), so it is not counted as missing -
    otherwise reframe would loop forever on lone-outlet sides it can never fill."""
    cov = ev.get("coverage") or {}
    fr = ev.get("framing") or {}
    return [s for s in SIDES
            if (cov.get(s) or {}).get("count", 0) >= MIN_SIDE_OWNERS
            and not has_framing(fr.get(s))]


def _lean_counts(ev):
    cov = ev.get("coverage") or {}
    return {s: (cov.get(s) or {}).get("count", 0) for s in SIDES}


def _leans_present(ev):
    """Distinct voting leans (L/C/R) with at least one outlet covering the story."""
    c = _lean_counts(ev)
    return [s for s in SIDES if c[s] > 0]


def _is_top_tier(ev):
    """Highest value: VISIBLE on the site (>=2 voting-lean outlets total) AND genuine
    spread (2+ DIFFERENT leans cover it) AND a covered side still unframed."""
    c = _lean_counts(ev)
    visible = sum(c.values()) >= 2
    spread = len(_leans_present(ev)) >= 2
    return visible and spread and bool(_missing_sides(ev))


def _rank_key(ev):
    """Sort key (used with reverse=True): top tier first, then more leans covered,
    then newest - so a capped/quota-limited pass fixes what matters most, first."""
    return (_is_top_tier(ev), len(_leans_present(ev)), ev.get("created_at") or "")


def _collect(ids):
    """Full events that need re-framing (or the explicit --ids set).

    Paksh 7B (F3): batches the id->full-event lookup via get_events_by_ids() instead
    of calling get_event() once per candidate (measured at ~30ms/call across the
    whole catalog - see the Phase 7B F3 investigation). Iteration order and the
    missing-vs-found/missing-sides filtering are unchanged from the previous
    per-id-get_event() version - only how the rows are fetched changed, not which
    ones are returned or in what order."""
    if ids:
        by_id = get_events_by_ids(ids)
        return [by_id[i] for i in ids if by_id.get(i)]
    # Paksh 7B: include_incomplete=True - reframe's whole job is to find and repair
    # events the publication gate is currently hiding, so it must see them, unlike
    # every public-facing caller of get_all_events().
    rows = get_all_events(include_incomplete=True)
    by_id = get_events_by_ids([row["id"] for row in rows])
    out = []
    for row in rows:
        ev = by_id.get(row["id"])
        if ev and _missing_sides(ev):
            out.append(ev)
    return out


def main():
    ap = argparse.ArgumentParser(description="Re-frame events with a covered-but-unframed side.")
    ap.add_argument("--apply", action="store_true", help="actually re-analyse (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="process at most N events (batching)")
    ap.add_argument("--ids", default="", help="comma-separated event ids to force")
    ap.add_argument("--top-tier", action="store_true",
                    help="process ONLY high-value events: visible + genuine L/C/R spread "
                         "(2+ different leans) + a covered-but-unframed side")
    args = ap.parse_args()

    reset_retry_stats()   # Paksh 7B (F2): fresh counters for this run, not a prior one
    init_db()

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    targets = _collect(ids)

    # Rank highest-value first so a capped or quota-limited pass fixes what visitors
    # actually see; optionally keep ONLY the top tier.
    targets.sort(key=_rank_key, reverse=True)
    top = [ev for ev in targets if _is_top_tier(ev)]
    if args.top_tier:
        targets = top
    if args.limit:
        if args.top_tier or ids:
            # --top-tier already excludes every single-lane event by definition, so
            # there's nothing to reserve for; an explicit --ids run is a forced,
            # manual selection and should not be reshuffled.
            targets = targets[:args.limit]
        else:
            # Paksh 7B: guarantee single-lane events a bounded slice of the cap - see
            # SINGLE_LANE_RESERVE above for why this is necessary, not optional.
            single_lane = [ev for ev in targets if not _is_top_tier(ev)]
            multi = [ev for ev in targets if _is_top_tier(ev)]
            reserve = min(SINGLE_LANE_RESERVE, args.limit, len(single_lane))
            targets = multi[:args.limit - reserve] + single_lane[:reserve]

    tag = "" if args.apply else "  (dry run)"
    print(f"{len(targets)} event(s) to re-frame{tag}   |  "
          f"top-tier (visible + 2+ leans + unframed side): {len(top)}")
    for ev in targets:
        miss = _missing_sides(ev) or ["(forced)"]
        star = "*" if _is_top_tier(ev) else " "
        print(f" {star}#{ev['id']:>5}  missing: {','.join(miss):<22}  {(ev.get('title') or '')[:56]}")

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
        filled = [s for s in want if has_framing(new_fr.get(s))]
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
    # Paksh 7B (F2): retry-observability summary - see analyze._RETRY_STATS.
    stats = get_retry_stats()
    llm_calls = stats["first_pass_complete"] + stats["retry_attempted"]
    if llm_calls:
        print(f"Retry: {stats['first_pass_complete']}/{llm_calls} first-pass complete, "
              f"{stats['retry_attempted']} retried "
              f"({stats['retry_rescued']} rescued, {stats['retry_not_rescued']} not rescued, "
              f"{stats['retry_failed']} failed).")
    if done:
        print("Next: py export_static.py   then push via GitHub Desktop.")


if __name__ == "__main__":
    main()