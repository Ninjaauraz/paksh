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
import datetime as _dt
from collections import Counter

from database import (
    init_db, get_all_events, get_events_by_ids, get_event_articles, update_event,
    get_reframe_meta, record_reframe_attempt,
)
from analyze import (
    analyze_event, has_framing, postprocess, MIN_SIDE_OWNERS, reset_retry_stats, get_retry_stats,
)

SIDES = ("left", "center", "right")

# Phase 40D-A: explicit failure classification for every attempted candidate, so a
# skip's cause is diagnosable from the log without grepping raw exception text (Phase
# 40C's audit had to reconstruct these by hand from 32 runs of raw log output).
# UNKNOWN_FAILURE is the deliberate fallback for a signature that matches none of
# these - never a guess at a more specific cause.
FAILURE_BILLING_PERMISSION_DENIED = "BILLING_PERMISSION_DENIED"
FAILURE_BILLING_CREDITS_EXHAUSTED = "BILLING_CREDITS_EXHAUSTED"
FAILURE_PROVIDER_RESOURCE_EXHAUSTED = "PROVIDER_RESOURCE_EXHAUSTED"
FAILURE_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
FAILURE_DNS_NETWORK = "DNS_NETWORK_FAILURE"
FAILURE_MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
FAILURE_EMPTY_RESPONSE = "EMPTY_RESPONSE"
FAILURE_UNUSABLE_FRAMING = "UNUSABLE_FRAMING"
FAILURE_PLACEHOLDER_SOURCE = "PLACEHOLDER_SOURCE_CONTENT"
FAILURE_NO_ARTICLES = "NO_ARTICLES"
FAILURE_UNKNOWN = "UNKNOWN_FAILURE"

# Classes an external/account fix is needed for - retrying tomorrow won't help, so
# these get a LONGER ranking cooldown than a likely-transient network blip (see
# _recently_failed / PERMANENT_COOLDOWN_HOURS below). Never excluded, only deprioritized.
PERMANENT_FAILURE_CLASSES = {FAILURE_BILLING_PERMISSION_DENIED, FAILURE_BILLING_CREDITS_EXHAUSTED}


def _classify_failure(exc):
    """Map a caught exception (from analyze_event's on_failure hook) to one of this
    module's failure categories, using the exact signatures Phase 40C's log audit
    found: Gemini billing (PERMISSION_DENIED / "dunning", RESOURCE_EXHAUSTED +
    "prepayment credits"), plain rate-limit RESOURCE_EXHAUSTED/429, provider
    UNAVAILABLE/503/"high demand", DNS/socket failures, generic-placeholder source
    titles, and empty/malformed model output. Never raises."""
    s = str(exc)
    sl = s.lower()
    if "PERMISSION_DENIED" in s or "dunning" in sl:
        return FAILURE_BILLING_PERMISSION_DENIED
    if "RESOURCE_EXHAUSTED" in s and ("prepayment" in sl or "credits" in sl or "billing" in sl):
        return FAILURE_BILLING_CREDITS_EXHAUSTED
    if "RESOURCE_EXHAUSTED" in s or "429" in s:
        return FAILURE_PROVIDER_RESOURCE_EXHAUSTED
    if "UNAVAILABLE" in s or "503" in s or "high demand" in sl:
        return FAILURE_PROVIDER_UNAVAILABLE
    if "getaddrinfo failed" in s or "WinError" in s or "Server disconnected" in s or "connection" in sl:
        return FAILURE_DNS_NETWORK
    if "generic placeholder title" in sl:
        return FAILURE_PLACEHOLDER_SOURCE
    if "empty" in sl:
        return FAILURE_EMPTY_RESPONSE
    if "json" in sl:
        return FAILURE_MALFORMED_RESPONSE
    return FAILURE_UNKNOWN


# Phase 40D-A: a candidate whose last attempt failed for a PERMANENT reason (billing)
# is deprioritized for longer than one that failed for a likely-transient reason
# (DNS/provider) - both remain fully eligible forever, never excluded, so recovery is
# still possible the moment the underlying cause clears. This only changes what fills
# a capped run's front-of-queue TODAY, so the same candidates don't get re-selected
# and re-failed on every single run while (for example) a billing account is down -
# Phase 40C found 18/18 sampled failures from ~4 weeks earlier were still unrepaired,
# having been re-selected on every run since (candidate starvation, confirmed).
PERMANENT_COOLDOWN_HOURS = 72
TRANSIENT_COOLDOWN_HOURS = 18


def _recently_failed(meta):
    """True if this candidate's last attempt is still within its failure class's
    cooldown window - i.e. it should sort BEHIND fresher/never-attempted candidates
    in today's ranking, not be excluded."""
    cls = meta.get("last_failure_class")
    ts = meta.get("last_attempt_at")
    if not cls or not ts:
        return False
    try:
        t = _dt.datetime.fromisoformat(ts.replace("Z", ""))
    except ValueError:
        return False
    age_h = (_dt.datetime.utcnow() - t).total_seconds() / 3600.0
    cooldown = PERMANENT_COOLDOWN_HOURS if cls in PERMANENT_FAILURE_CLASSES else TRANSIENT_COOLDOWN_HOURS
    return age_h < cooldown

# Paksh 20D: analyze_event() is the SAME full-fresh-analysis pipeline used for a
# brand-new cluster - it always re-derives title/summary/summary_points/topic/region
# from the model's own fresh output, and _clean_framing() rebuilds EVERY covered
# side's framing from that fresh output, not just the ones that were missing. Left
# unguarded, a "fill the gaps" reframe call can silently rewrite an already-complete
# event's region (which cascades into lean_of() -> coverage -> the published bias
# bar - see the Phase 20C regression on event #11940) and can silently replace
# already-good framing on sides that were never missing. PRESERVE_FIELDS is exactly
# recount_migrate.py's own _PRESERVE set (Paksh 3.x) - the already-established "these
# fields are not this operation's to touch" list - reused here rather than inventing
# a second, subtly different one.
PRESERVE_FIELDS = ("title", "summary", "summary_points", "title_hi", "summary_hi",
                    "summary_points_hi", "topic", "region", "summary_method")


def _merge_reframe_result(ev, fresh, want, articles):
    """Combine the EXISTING event (ev) with a fresh analyze_event() result, keeping
    everything except the specific `want` sides' framing exactly as it was. Returns
    the same shape update_event() already expects (a postprocess() output), so the
    caller's write path is unchanged.

    - title/summary/summary_points/topic/region/summary_method (+Hindi) come from the
      EXISTING event, never the fresh call - see PRESERVE_FIELDS above.
    - framing/framing_hi start from the EXISTING event's values; only a side in `want`
      whose fresh value actually has_framing() gets replaced. A side that was already
      complete, or a side the fresh call didn't manage to fill, is untouched.
    - Passing the preserved region back through postprocess() (the SAME function
      recount_migrate.py already trusts for this exact purpose) is what keeps
      coverage/lean_counts/sources correctly stable: same (region, articles) in ->
      same deterministic arithmetic out, every time. `articles` must be the SAME
      member-article rows the caller fetched for this event (get_event_articles(eid)).
    """
    raw = {k: ev.get(k) for k in PRESERVE_FIELDS}
    fresh_fr = fresh.get("framing") or {}
    fresh_fr_hi = fresh.get("framing_hi") or {}
    merged_fr = dict(ev.get("framing") or {})
    merged_fr_hi = dict(ev.get("framing_hi") or {})
    for s in want:
        if has_framing(fresh_fr.get(s)):
            merged_fr[s] = fresh_fr[s]
        if has_framing(fresh_fr_hi.get(s)):
            merged_fr_hi[s] = fresh_fr_hi[s]
    raw["framing"] = merged_fr
    raw["framing_hi"] = merged_fr_hi
    return postprocess(raw, articles)

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
    """Sort key (used with reverse=True): top tier first, THEN not-recently-failed
    first (Phase 40D-A - see _recently_failed; existing editorial priority otherwise
    unchanged), then more leans covered, then newest - so a capped/quota-limited pass
    fixes what matters most, first, without the same handful of failing candidates
    permanently occupying every run's front-of-queue."""
    return (_is_top_tier(ev), not _recently_failed(ev.get("_reframe_meta") or {}),
            len(_leans_present(ev)), ev.get("created_at") or "")


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
        out = [by_id[i] for i in ids if by_id.get(i)]
    else:
        # Paksh 7B: include_incomplete=True - reframe's whole job is to find and repair
        # events the publication gate is currently hiding, so it must see them, unlike
        # every public-facing caller of get_all_events().
        rows = get_all_events(include_incomplete=True)
        by_id = get_events_by_ids([row["id"] for row in rows])
        out = []
        for row in rows:
            ev = by_id.get(row["id"])
            if ev and ev.get("content_complete") is False and _missing_sides(ev):
                out.append(ev)
    # Phase 40D-A: attach each candidate's reframe attempt/failure history for
    # _rank_key()'s starvation check - a transient, in-memory-only key (never written
    # back; _merge_reframe_result()/update_event() only ever read PRESERVE_FIELDS +
    # framing/framing_hi off `ev`, so this can't leak into a saved event).
    meta = get_reframe_meta([ev["id"] for ev in out])
    for ev in out:
        ev["_reframe_meta"] = meta.get(ev["id"], {})
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
    failure_counts = Counter()   # Phase 40D-A: per-category tally for the run summary
    for ev in targets:
        eid = ev["id"]
        want = set(_missing_sides(ev)) or set(SIDES)
        rows = get_event_articles(eid)
        if not rows:
            skipped += 1
            failure_counts[FAILURE_NO_ARTICLES] += 1
            record_reframe_attempt(eid, FAILURE_NO_ARTICLES)
            continue
        # Phase 40D-A: on_failure captures the exception analyze_event() itself caught
        # (existing hook, Phase 30C-P - see analyze.py's analyze_event docstring) so a
        # skip can be classified from the REAL cause, not just "no framing produced".
        caught = []
        fresh = analyze_event(rows, on_failure=caught.append)   # fixed build_prompt + framing prompt
        fresh_fr = fresh.get("framing") or {}
        filled = [s for s in want if has_framing(fresh_fr.get(s))]
        if not filled:
            # LLM produced no framing for the missing side(s) - do NOT overwrite a good
            # brief with an empty/extractive one. caught[0] is set when analyze_event's
            # OWN first attempt raised (the event became extractive); if it's empty, the
            # model responded but the specific missing side(s) still came back unframed
            # (a genuine UNUSABLE_FRAMING case, distinct from an outright failure).
            failure_class = _classify_failure(caught[0]) if caught else FAILURE_UNUSABLE_FRAMING
            failure_counts[failure_class] += 1
            record_reframe_attempt(eid, failure_class)
            print(f"  skip  #{eid}  [{failure_class}]  (no framing produced - is the LLM backend up?)")
            skipped += 1
            continue
        # Paksh 20D: write only the merged result (existing title/summary/topic/region/
        # already-complete framing preserved, only `filled` sides' framing replaced) -
        # never the raw fresh analysis, which would silently reclassify region/topic
        # and rewrite every side's framing, not just the missing ones.
        analysis = _merge_reframe_result(ev, fresh, want, rows)
        update_event(eid, analysis, bump_created=False)   # keep original timestamp
        record_reframe_attempt(eid, None)   # Phase 40D-A: clear any prior failure record
        done += 1
        print(f"  ok    #{eid}  filled: {','.join(filled)}")

    print(f"\nDone. re-framed {done}, skipped {skipped}.")
    if failure_counts:
        print("Failure classes: " + ", ".join(f"{k}={v}" for k, v in failure_counts.most_common()))
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
